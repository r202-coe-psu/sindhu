"""Transport, error type and normalization helpers shared by the CCTV providers.

Upstream objects are never returned, logged, or placed in a cache; only the
small allowlisted public DTO shape crosses the provider boundary.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json as json_module
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit, urlunsplit
from zoneinfo import ZoneInfo

import httpx

from sindhu.schemas.visual_feeds import MAX_HISTORY_FRAMES  # noqa: F401  (re-exported)
from sindhu.services.cctv_errors import SourceError  # noqa: F401  (re-exported)

UTC = dt.timezone.utc
BANGKOK = ZoneInfo("Asia/Bangkok")

MAX_RESPONSE_BYTES = 2 * 1024 * 1024
SOURCE_DEADLINE_SECONDS = 10.0
STALE_AFTER = dt.timedelta(hours=24)


def raise_source_error(code: str) -> None:
    raise SourceError(code)


def utc(value: dt.datetime) -> dt.datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def iso(value: dt.datetime | None) -> str | None:
    if value is None:
        return None
    return utc(value).isoformat().replace("+00:00", "Z")


def parse_provider_time(value: Any) -> dt.datetime | None:
    """Parse provider timestamps; naive values are Asia/Bangkok."""

    if isinstance(value, dt.datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=BANGKOK).astimezone(UTC)
        return value.astimezone(UTC)
    if not isinstance(value, str) or not value.strip():
        return None

    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = dt.datetime.fromisoformat(raw)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        parsed = parsed.replace(tzinfo=BANGKOK)
    return parsed.astimezone(UTC)


def provider_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        if value in (0, 1):
            return bool(value)
        return None
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on", "online", "y"}:
            return True
        if normalized in {"0", "false", "no", "off", "offline", "n"}:
            return False
    return None


def safe_upstream_url(
    value: Any,
    allowed_hosts: frozenset[str],
    default_host: str | None = None,
    allowed_ports: frozenset[int | None] = frozenset({None, 443}),
) -> str | None:
    """Return a fixed-host HTTPS URL with all query data removed.

    Provider image URLs are not followed by this adapter.  Removing the full
    query, instead of trying to guess which query keys are harmless, keeps
    credentials and cache tokens from crossing into the public DTO.  DWR's
    version query is constructed locally from a parsed provider timestamp.
    """

    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip()
    if len(raw) > 2048 or any(ord(char) < 33 for char in raw) or "\\" in raw:
        return None
    if default_host and raw.startswith("/") and not raw.startswith("//"):
        # ``default_host`` may include a configured proxy port.  Compare the
        # parsed hostname to the allowlist, then preserve the full authority
        # while resolving the relative provider path.
        try:
            default_hostname = urlsplit(f"//{default_host}").hostname
        except ValueError:
            default_hostname = None
        if default_hostname and default_hostname.lower().rstrip(".") in allowed_hosts:
            raw = f"https://{default_host}{raw}"
    try:
        parsed = urlsplit(raw)
        hostname = (parsed.hostname or "").lower().rstrip(".")
        port = parsed.port
    except ValueError:
        return None
    if (
        parsed.scheme.lower() != "https"
        or hostname not in allowed_hosts
        or port not in allowed_ports
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or not parsed.path
    ):
        return None
    # Keep a non-default configured proxy port in the sanitized URL.  The
    # default HTTPS port is intentionally canonicalized away for stable DTOs.
    authority_host = f"[{hostname}]" if ":" in hostname else hostname
    authority = (
        f"{authority_host}:{port}" if port not in (None, 443) else authority_host
    )
    return urlunsplit(("https", authority, parsed.path, "", ""))


def dwr_proxy_url(upstream_id: str, captured_at: dt.datetime) -> str:
    return (
        f"/v1/visual-feeds/dwr/{upstream_id}/snapshot"
        f"?v={int(utc(captured_at).timestamp())}"
    )


@dataclass(frozen=True)
class BufferedResponse:
    """The bounded public part of an HTTP response after its stream closes."""

    status_code: int
    headers: Mapping[str, str]
    content: bytes
    history: tuple[object, ...] = ()

    def json(self) -> Any:
        return json_module.loads(self.content)


class Transport:
    """One shared HTTP client with a hard deadline and a bounded, non-redirecting read."""

    def __init__(self, client: httpx.AsyncClient, deadline_seconds: float):
        self.client = client
        self.deadline_seconds = deadline_seconds

    async def request(
        self,
        method: str,
        url: str,
        *,
        params: Mapping[str, Any] | None = None,
        json: Mapping[str, Any] | None = None,
    ) -> BufferedResponse:
        """Stream one non-redirecting response with a hard body bound."""

        stream_method = getattr(self.client, "stream", None)
        if stream_method is None:
            raise_source_error("transport_error")
        request_kwargs: dict[str, Any] = {
            "params": params,
            "follow_redirects": False,
        }
        # httpx.AsyncClient.get does not accept json; stream/request do, but
        # omitting it for GET also keeps the wire request unambiguous.
        if json is not None:
            request_kwargs["json"] = json
        try:
            async with asyncio.timeout(self.deadline_seconds):
                async with stream_method(
                    method,
                    url,
                    **request_kwargs,
                ) as response:
                    if response.history or 300 <= response.status_code < 400:
                        raise SourceError("redirect_rejected")
                    if response.status_code < 200 or response.status_code >= 300:
                        raise SourceError("upstream_http_error")

                    content_length = response.headers.get("content-length")
                    try:
                        declared_length = int(content_length) if content_length else 0
                    except ValueError:
                        declared_length = 0
                    if declared_length > MAX_RESPONSE_BYTES:
                        raise SourceError("response_too_large")

                    body = bytearray()
                    async for chunk in response.aiter_bytes():
                        if not isinstance(chunk, bytes):
                            raise SourceError("invalid_response")
                        if len(body) + len(chunk) > MAX_RESPONSE_BYTES:
                            raise SourceError("response_too_large")
                        body.extend(chunk)
                    return BufferedResponse(
                        status_code=response.status_code,
                        headers=dict(response.headers),
                        content=bytes(body),
                        history=tuple(response.history),
                    )
        except SourceError:
            raise
        except asyncio.TimeoutError:
            raise SourceError("timeout") from None
        except (httpx.HTTPError, OSError, TimeoutError):
            raise SourceError("transport_error") from None
        except Exception:
            raise SourceError("transport_error") from None

    async def json(
        self,
        method: str,
        url: str,
        *,
        params: Mapping[str, Any] | None = None,
        json: Mapping[str, Any] | None = None,
    ) -> Any:
        response = await self.request(method, url, params=params, json=json)
        try:
            decoded = response.json()
        except (TypeError, ValueError, UnicodeDecodeError):
            raise SourceError("invalid_json") from None
        if not isinstance(decoded, (dict, list)):
            raise SourceError("invalid_response")
        return decoded
