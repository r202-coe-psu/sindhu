"""Request-time adapters for the two public CCTV providers.

The adapters deliberately normalize at the provider boundary.  Upstream
objects are never returned, logged, or placed in a cache; only the small
allowlisted public DTO shape crosses this module.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json as json_module
import re
from collections.abc import Callable, Mapping
from copy import deepcopy
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit, urlunsplit
from zoneinfo import ZoneInfo

import httpx

from sindhu.services.cctv_catalog import (
    DWR_CAMERAS,
    DWR_REGISTRY_VERSION,
    DWR_SOURCE,
    DWR_SOURCE_URL,
    HATYAI_CAMERAS,
    HATYAI_REGISTRY_VERSION,
    HATYAI_SOURCE,
    get_camera,
)

UTC = dt.timezone.utc
BANGKOK = ZoneInfo("Asia/Bangkok")

HATYAI_HOSTS = frozenset(
    {
        "hatyaicityclimate.org",
        "www.hatyaicityclimate.org",
        "photo.hatyaicityclimate.org",
    }
)
HATYAI_CCTV_API_BASE_URL = "https://hatyaicityclimate.org"
DWR_CCTV_API_BASE_URL = DWR_SOURCE_URL

HATYAI_CATALOG_PATH = "/api/flood/cams"
HATYAI_HISTORY_PATH = "/api/flood/cam"
HATYAI_SOURCE_PATH = "/flood/map/camera"
HATYAI_DETAIL_PATH = "/flood/cam"
DWR_LIST_PATH = "/public/reportCctv/listPaginate"
DWR_SNAPSHOT_PATH = "/public/reportCctv/snapshot"
DWR_IMAGE_PATH = "/file/image/cctv"


def normalize_provider_base_url(value: str) -> str:
    """Validate and normalize an upstream provider base URL.

    Provider bases are configuration, not user input, but rejecting
    credentials and URL-delimiting components here prevents accidental
    credential/query leakage when endpoint paths are joined at request time.
    HTTP remains accepted for local proxies; public defaults are HTTPS.
    """

    if not isinstance(value, str):
        raise ValueError("provider base URL must be a string")
    raw = value.strip()
    if not raw or len(raw) > 2048:
        raise ValueError("provider base URL must be a non-empty URL")
    if any(ord(char) < 33 for char in raw) or "\\" in raw:
        raise ValueError("provider base URL contains invalid characters")
    try:
        parsed = urlsplit(raw)
        hostname = parsed.hostname
        parsed.port
    except ValueError as error:
        raise ValueError("provider base URL is malformed") from error
    if (
        parsed.scheme.lower() not in {"http", "https"}
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(
            "provider base URL must be an absolute http(s) URL without credentials, query, or fragment"
        )
    return urlunsplit(
        (parsed.scheme.lower(), parsed.netloc.lower(), parsed.path.rstrip("/"), "", "")
    )


def _join_provider_url(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


HATYAI_CATALOG_URL = _join_provider_url(HATYAI_CCTV_API_BASE_URL, HATYAI_CATALOG_PATH)
HATYAI_HISTORY_URL = _join_provider_url(HATYAI_CCTV_API_BASE_URL, HATYAI_HISTORY_PATH)
DWR_LIST_URL = _join_provider_url(DWR_CCTV_API_BASE_URL, DWR_LIST_PATH)
DWR_SNAPSHOT_URL = _join_provider_url(DWR_CCTV_API_BASE_URL, DWR_SNAPSHOT_PATH)
DWR_IMAGE_URL = _join_provider_url(DWR_CCTV_API_BASE_URL, DWR_IMAGE_PATH)

MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_HISTORY_FRAMES = 144
SOURCE_DEADLINE_SECONDS = 10.0
STALE_AFTER = dt.timedelta(minutes=30)

_SNAPSHOT_PATH = re.compile(
    r"^/(?P<station>[A-Za-z0-9_-]{1,64})/"
    r"(?P<year>[0-9]{4})/(?P<month>[0-9]{1,2})/(?P<day>[0-9]{1,2})/"
    r"(?P<hour>[0-9]{1,2})_(?P<minute>[0-9]{1,2})\.jpg$"
)


class SourceError(RuntimeError):
    """Safe, stable source failure.

    The exception intentionally contains only a machine-readable code.  In
    particular, provider URLs, query strings, response bodies, and transport
    exception strings must not become observable application output.
    """

    def __init__(self, code: str):
        safe_code = code if re.fullmatch(r"[a-z0-9_]+", str(code)) else "source_error"
        self.code = safe_code
        super().__init__(safe_code)


def _raise(code: str) -> None:
    raise SourceError(code)


def _utc(value: dt.datetime) -> dt.datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _iso(value: dt.datetime | None) -> str | None:
    if value is None:
        return None
    return _utc(value).isoformat().replace("+00:00", "Z")


def _parse_provider_time(value: Any) -> dt.datetime | None:
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


def _parse_date(value: Any) -> dt.date | None:
    if isinstance(value, dt.datetime):
        return None
    if isinstance(value, dt.date):
        return value
    if not isinstance(value, str) or not re.fullmatch(
        r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value
    ):
        return None
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        return None


HISTORY_DAYS = 7


def _is_in_history_window(value: dt.date, now: dt.datetime) -> bool:
    bangkok_today = _utc(now).astimezone(BANGKOK).date()
    return bangkok_today - dt.timedelta(days=HISTORY_DAYS - 1) <= value <= bangkok_today


def _provider_bool(value: Any) -> bool | None:
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


def _safe_upstream_url(
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


def _dwr_proxy_url(upstream_id: str, captured_at: dt.datetime) -> str:
    return (
        f"/v1/visual-feeds/dwr/{upstream_id}/snapshot"
        f"?v={int(_utc(captured_at).timestamp())}"
    )


@dataclass(frozen=True)
class _BufferedResponse:
    """The bounded public part of an HTTP response after its stream closes."""

    status_code: int
    headers: Mapping[str, str]
    content: bytes
    history: tuple[object, ...] = ()

    def json(self) -> Any:
        return json_module.loads(self.content)


class CctvSources:
    """Fetch and normalize Hatyai and DWR CCTV data using a shared client."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        clock: Callable[[], dt.datetime] | None = None,
        deadline_seconds: float = SOURCE_DEADLINE_SECONDS,
        hatyai_base_url: str | None = None,
        dwr_base_url: str | None = None,
        hatyai_api_base_url: str | None = None,
        dwr_api_base_url: str | None = None,
    ) -> None:
        self.client = client
        self.clock = clock or (lambda: dt.datetime.now(UTC))
        self.deadline_seconds = max(0.1, float(deadline_seconds))
        if hatyai_base_url is not None and hatyai_api_base_url is not None:
            raise ValueError("configure only one Hatyai provider base URL")
        if dwr_base_url is not None and dwr_api_base_url is not None:
            raise ValueError("configure only one DWR provider base URL")
        self.hatyai_base_url = normalize_provider_base_url(
            hatyai_base_url or hatyai_api_base_url or HATYAI_CCTV_API_BASE_URL
        )
        self.dwr_base_url = normalize_provider_base_url(
            dwr_base_url or dwr_api_base_url or DWR_CCTV_API_BASE_URL
        )
        try:
            configured_hatyai_host = urlsplit(self.hatyai_base_url).hostname
            configured_hatyai_port = urlsplit(self.hatyai_base_url).port
        except ValueError:
            configured_hatyai_host = None
            configured_hatyai_port = None
        self.hatyai_image_hosts = HATYAI_HOSTS | (
            frozenset({configured_hatyai_host})
            if configured_hatyai_host
            else frozenset()
        )
        self.hatyai_image_ports = frozenset({None, 443, configured_hatyai_port})

    def _provider_url(self, source: str, path: str) -> str:
        if source == HATYAI_SOURCE:
            return _join_provider_url(self.hatyai_base_url, path)
        if source == DWR_SOURCE:
            return _join_provider_url(self.dwr_base_url, path)
        raise SourceError("unknown_source")

    def _now(self) -> dt.datetime:
        try:
            value = self.clock()
        except Exception:
            return dt.datetime.now(UTC)
        if not isinstance(value, dt.datetime):
            return dt.datetime.now(UTC)
        return _utc(value)

    async def _request(
        self,
        method: str,
        url: str,
        *,
        params: Mapping[str, Any] | None = None,
        json: Mapping[str, Any] | None = None,
    ) -> _BufferedResponse:
        """Stream one non-redirecting response with a hard body bound."""

        stream_method = getattr(self.client, "stream", None)
        if stream_method is None:
            _raise("transport_error")
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
                    return _BufferedResponse(
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

    async def _json(
        self,
        method: str,
        url: str,
        *,
        params: Mapping[str, Any] | None = None,
        json: Mapping[str, Any] | None = None,
    ) -> Any:
        response = await self._request(method, url, params=params, json=json)
        try:
            decoded = response.json()
        except (TypeError, ValueError, UnicodeDecodeError):
            raise SourceError("invalid_json") from None
        if not isinstance(decoded, (dict, list)):
            raise SourceError("invalid_response")
        return decoded

    def _base_record(
        self,
        source: str,
        camera: Mapping[str, Any],
        *,
        fetched_at: str,
        availability: str = "unknown",
        provider_status: str = "unknown",
        image_url: str | None = None,
        captured_at: dt.datetime | None = None,
    ) -> dict[str, Any]:
        """Build exactly the fields accepted by PublicVisualFeed."""

        if source == HATYAI_SOURCE:
            registry_version = HATYAI_REGISTRY_VERSION
            source_url = self._provider_url(HATYAI_SOURCE, HATYAI_SOURCE_PATH)
            detail_url = self._provider_url(
                HATYAI_SOURCE, f"{HATYAI_DETAIL_PATH}/{camera['slug']}"
            )
            history_supported = True
        else:
            registry_version = DWR_REGISTRY_VERSION
            source_url = self._provider_url(DWR_SOURCE, "/")
            detail_url = self._provider_url(
                DWR_SOURCE, f"/public/station/getByCode/{camera['station_code']}"
            )
            history_supported = False

        return {
            "source": source,
            "upstream_id": str(camera["upstream_id"]),
            "slug": str(camera["slug"]),
            "title_th": str(camera["title_th"]),
            "code": str(camera["code"]),
            "coverage_group": str(camera["coverage_group"]),
            "media_type": "cctv",
            "coordinate_status": str(camera.get("coordinate_status", "unverified")),
            "coordinates": deepcopy(camera.get("coordinates")),
            "coordinate_provenance": deepcopy(camera.get("coordinate_provenance")),
            "registry_version": registry_version,
            "availability": availability,
            "provider_status": provider_status,
            "image_url": image_url,
            "detail_url": detail_url,
            "captured_at": _iso(captured_at),
            "fetched_at": fetched_at,
            "history_supported": history_supported,
            "attribution": {
                "provider": (
                    "Hatyai City Climate"
                    if source == HATYAI_SOURCE
                    else "กรมทรัพยากรน้ำ"
                ),
                "source_url": source_url,
            },
        }

    async def latest(self, source: str) -> list[dict[str, Any]]:
        """Return one normalized latest record per registered camera."""

        if source not in {HATYAI_SOURCE, DWR_SOURCE}:
            raise SourceError("unknown_source")
        try:
            async with asyncio.timeout(self.deadline_seconds):
                if source == HATYAI_SOURCE:
                    return await self._latest_hatyai()
                return await self._latest_dwr()
        except SourceError:
            raise
        except asyncio.TimeoutError:
            raise SourceError("timeout") from None
        except Exception:
            raise SourceError("source_error") from None

    async def _latest_hatyai(self) -> list[dict[str, Any]]:
        slugs = ",".join(str(camera["slug"]) for camera in HATYAI_CAMERAS)
        payload = await self._json(
            "GET",
            self._provider_url(HATYAI_SOURCE, HATYAI_CATALOG_PATH),
            params={"name": slugs},
        )
        if not isinstance(payload, Mapping):
            raise SourceError("invalid_catalog")
        items = payload.get("items")
        count = payload.get("count")
        if not isinstance(items, list) or not items:
            raise SourceError("invalid_catalog")
        if isinstance(count, bool) or not isinstance(count, int) or count != len(items):
            raise SourceError("invalid_catalog")

        now = self._now()
        fetched_at = _iso(now)
        by_identity: dict[tuple[str, str], Mapping[str, Any]] = {}
        for item in items:
            if not isinstance(item, Mapping):
                raise SourceError("invalid_catalog")
            name = str(item.get("name") or "").strip()
            if not name:
                raise SourceError("invalid_catalog")
            camera_id = item.get("cameraId")
            camera = get_camera(HATYAI_SOURCE, camera_id)
            # The upstream catalog can contain non-CCTV records when its
            # filter is ignored.  Unknown records are deliberately dropped.
            if camera is None or camera["slug"] != name:
                continue
            identity = (str(camera["upstream_id"]), name)
            by_identity.setdefault(identity, item)

        records: list[dict[str, Any]] = []
        for camera in HATYAI_CAMERAS:
            item = by_identity.get((str(camera["upstream_id"]), str(camera["slug"])))
            if item is None:
                records.append(
                    self._base_record(
                        HATYAI_SOURCE,
                        camera,
                        fetched_at=fetched_at,
                        provider_status="missing",
                    )
                )
                continue

            captured_at = _parse_provider_time(item.get("atDate"))
            image_url = _safe_upstream_url(
                item.get("photo"),
                self.hatyai_image_hosts,
                default_host=urlsplit(self.hatyai_base_url).netloc,
                allowed_ports=self.hatyai_image_ports,
            )
            enabled_value = item.get("enable")
            enabled = _provider_bool(enabled_value)
            status_message = item.get("statusMsg")
            has_status_message = isinstance(status_message, str) and bool(
                status_message.strip()
            )

            # Missing or malformed provider fields are unknown, never inferred
            # from a truthy fallback.  A present disabled flag is authoritative.
            if enabled is False:
                availability = "offline"
                provider_status = "offline"
            elif enabled is None or captured_at is None or image_url is None:
                availability = "unknown"
                provider_status = "unknown"
            elif has_status_message:
                availability = "degraded"
                provider_status = "degraded"
            elif now - captured_at > STALE_AFTER:
                availability = "stale"
                provider_status = "stale"
            else:
                availability = "online"
                provider_status = "online"

            records.append(
                self._base_record(
                    HATYAI_SOURCE,
                    camera,
                    fetched_at=fetched_at,
                    availability=availability,
                    provider_status=provider_status,
                    image_url=image_url,
                    captured_at=captured_at,
                )
            )
        return records

    @staticmethod
    def _dwr_result_entity(result: Mapping[str, Any]) -> Mapping[str, Any] | None:
        entity = result.get("entity")
        return entity if isinstance(entity, Mapping) else None

    @staticmethod
    def _matches_dwr(camera: Mapping[str, Any], entity: Mapping[str, Any]) -> bool:
        entity_id = str(entity.get("id") or "").strip().lower()
        station_code = str(entity.get("stationCode") or "").strip()
        return entity_id == str(camera["upstream_id"]).lower() and station_code == str(
            camera["station_code"]
        )

    async def _latest_dwr(self) -> list[dict[str, Any]]:
        payload = await self._json(
            "POST",
            self._provider_url(DWR_SOURCE, DWR_LIST_PATH),
            json={
                "paginate": {"page": 1, "pageSize": 500, "orders": []},
                "search": {},
            },
        )
        if not isinstance(payload, Mapping):
            raise SourceError("invalid_catalog")
        value = payload.get("value")
        results = value.get("results") if isinstance(value, Mapping) else None
        if not isinstance(results, list):
            raise SourceError("invalid_catalog")

        by_id: dict[str, Mapping[str, Any]] = {}
        for result in results:
            if (
                not isinstance(result, Mapping)
                or str(result.get("provinceNameTh") or "").strip() != "สงขลา"
            ):
                continue
            entity = self._dwr_result_entity(result)
            if entity is None:
                continue
            for camera in DWR_CAMERAS:
                if self._matches_dwr(camera, entity):
                    by_id.setdefault(str(camera["upstream_id"]), entity)
                    break

        now = self._now()
        fetched_at = _iso(now)
        records: list[dict[str, Any]] = []
        for camera in DWR_CAMERAS:
            entity = by_id.get(str(camera["upstream_id"]))
            if entity is None:
                records.append(
                    self._base_record(
                        DWR_SOURCE,
                        camera,
                        fetched_at=fetched_at,
                        provider_status="missing",
                    )
                )
                continue

            online = _provider_bool(entity.get("cctvOnline"))
            captured_at: dt.datetime | None = None
            image_url: str | None = None
            snapshot_ok = False
            snapshot_error_code: str | None = None
            if online is True:
                try:
                    path = await self._snapshot_path(camera)
                    captured_at = self._parse_snapshot_path(camera, path)
                    image_url = _dwr_proxy_url(str(camera["upstream_id"]), captured_at)
                    snapshot_ok = True
                except SourceError as error:
                    # The provider status remains separate from the image
                    # retrieval status; a camera can be online while its
                    # current public snapshot is temporarily unavailable.
                    snapshot_ok = False
                    snapshot_error_code = error.code

            if online is None:
                availability = "unknown"
                provider_status = "unknown"
            elif online is False:
                availability = "offline"
                provider_status = "offline"
            elif snapshot_error_code == "invalid_snapshot_path":
                availability = "unknown"
                provider_status = "unknown"
            elif not snapshot_ok or captured_at is None or image_url is None:
                availability = "degraded"
                provider_status = "snapshot_unavailable"
            elif now - captured_at > STALE_AFTER:
                availability = "stale"
                provider_status = "stale"
            else:
                availability = "online"
                provider_status = "online"

            records.append(
                self._base_record(
                    DWR_SOURCE,
                    camera,
                    fetched_at=fetched_at,
                    availability=availability,
                    provider_status=provider_status,
                    image_url=image_url,
                    captured_at=captured_at,
                )
            )
        return records

    async def history(
        self,
        source: str,
        upstream_id: str,
        date: dt.date | str,
    ) -> dict[str, Any]:
        """Return bounded Hatyai history in chronological UTC order."""

        if source not in {HATYAI_SOURCE, DWR_SOURCE}:
            raise SourceError("unknown_source")
        if source != HATYAI_SOURCE:
            raise SourceError("history_unsupported")
        camera = get_camera(source, upstream_id)
        if camera is None:
            raise SourceError("unknown_camera")
        date_value = _parse_date(date)
        if date_value is None:
            raise SourceError("invalid_history_date")
        if not _is_in_history_window(date_value, self._now()):
            raise SourceError("history_date_out_of_window")

        try:
            async with asyncio.timeout(self.deadline_seconds):
                payload = await self._json(
                    "GET",
                    self._provider_url(HATYAI_SOURCE, HATYAI_HISTORY_PATH),
                    params={
                        "id": str(camera["upstream_id"]),
                        "date": date_value.isoformat(),
                        "items": MAX_HISTORY_FRAMES,
                        "show": MAX_HISTORY_FRAMES,
                    },
                )
        except SourceError:
            raise
        except asyncio.TimeoutError:
            raise SourceError("timeout") from None
        except Exception:
            raise SourceError("source_error") from None

        if not isinstance(payload, Mapping) or not isinstance(
            payload.get("photos"), list
        ):
            raise SourceError("invalid_history")
        photos = payload["photos"]
        possibly_truncated = len(photos) >= MAX_HISTORY_FRAMES
        selected = photos[:MAX_HISTORY_FRAMES]
        frames: list[dict[str, Any]] = []
        wrong_day_count = 0
        for photo in selected:
            if not isinstance(photo, Mapping):
                continue
            captured_at = _parse_provider_time(photo.get("atDate"))
            image_url = _safe_upstream_url(
                photo.get("photoUrl"),
                self.hatyai_image_hosts,
                default_host=urlsplit(self.hatyai_base_url).netloc,
                allowed_ports=self.hatyai_image_ports,
            )
            if captured_at is None or image_url is None:
                continue
            if captured_at.astimezone(BANGKOK).date() != date_value:
                wrong_day_count += 1
                continue
            thumbnail_url = _safe_upstream_url(
                photo.get("thumbUrl"),
                self.hatyai_image_hosts,
                default_host=urlsplit(self.hatyai_base_url).netloc,
                allowed_ports=self.hatyai_image_ports,
            )
            frames.append(
                {
                    "captured_at": _iso(captured_at),
                    "image_url": image_url,
                    "thumbnail_url": thumbnail_url,
                }
            )

        frames.sort(key=lambda frame: (frame["captured_at"], frame["image_url"]))
        if photos and not frames:
            raise SourceError(
                "history_wrong_day" if wrong_day_count else "invalid_history"
            )
        return {"frames": frames, "possibly_truncated": possibly_truncated}

    async def _snapshot_path(self, camera: Mapping[str, Any]) -> str:
        payload = await self._json(
            "GET",
            self._provider_url(
                DWR_SOURCE, f"{DWR_SNAPSHOT_PATH}/{camera['upstream_id']}"
            ),
        )
        if not isinstance(payload, Mapping):
            raise SourceError("invalid_snapshot_path")
        value = payload.get("value")
        if isinstance(value, Mapping):
            value = value.get("path")
        if not isinstance(value, str):
            raise SourceError("invalid_snapshot_path")
        self._parse_snapshot_path(camera, value)
        return value

    @staticmethod
    def _parse_snapshot_path(camera: Mapping[str, Any], path: str) -> dt.datetime:
        match = _SNAPSHOT_PATH.fullmatch(path)
        if match is None or match.group("station") != str(camera["station_code"]):
            raise SourceError("invalid_snapshot_path")
        try:
            local = dt.datetime(
                int(match.group("year")),
                int(match.group("month")),
                int(match.group("day")),
                int(match.group("hour")),
                int(match.group("minute")),
                tzinfo=BANGKOK,
            )
        except ValueError:
            raise SourceError("invalid_snapshot_path") from None
        return local.astimezone(UTC)

    async def snapshot(self, upstream_id: str) -> bytes:
        """Fetch one DWR JPEG through its official public image proxy."""

        camera = get_camera(DWR_SOURCE, upstream_id)
        if camera is None:
            raise SourceError("unknown_camera")
        try:
            async with asyncio.timeout(self.deadline_seconds):
                path = await self._snapshot_path(camera)
                # Validate again immediately before using the proxy path.  It
                # must be source-derived and cannot contain a user URL/query.
                self._parse_snapshot_path(camera, path)
                response = await self._request(
                    "POST",
                    self._provider_url(DWR_SOURCE, DWR_IMAGE_PATH),
                    json={"path": path},
                )
        except SourceError:
            raise
        except asyncio.TimeoutError:
            raise SourceError("timeout") from None
        except Exception:
            raise SourceError("source_error") from None

        content_type = response.headers.get("content-type", "")
        if content_type.split(";", 1)[0].strip().lower() != "image/jpeg":
            raise SourceError("invalid_jpeg")
        body = response.content
        if (
            len(body) > MAX_RESPONSE_BYTES
            or len(body) < 3
            or body[:3] != b"\xff\xd8\xff"
        ):
            raise SourceError("invalid_jpeg")
        return body


__all__ = ["CctvSources", "SourceError"]
