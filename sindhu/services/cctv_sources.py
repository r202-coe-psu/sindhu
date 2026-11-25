"""Request-time facade over the public CCTV providers.

The per-source logic lives in ``sindhu.services.cctv_providers``; this class
keeps the shared client, clock and base-URL configuration and routes each call
to the provider registered for that source.  Upstream objects are never
returned, logged, or placed in a cache; only the allowlisted public DTO shape
crosses this module.
"""

from __future__ import annotations

import asyncio
import datetime as dt
from collections.abc import Callable
from typing import Any

import httpx

from sindhu.config.provider_urls import validate_allowed_api_base_url
from sindhu.services.cctv_catalog import DWR_SOURCE, HATYAI_SOURCE, RID_SOURCE
from sindhu.services.cctv_providers import (
    SourceError,
    Transport,
    build_providers,
)
from sindhu.services.cctv_providers.base import join_provider_url
from sindhu.services.cctv_providers.dwr import (
    DWR_CCTV_BASE_URL,
    DWR_IMAGE_PATH,
    DWR_LIST_PATH,
    DWR_SNAPSHOT_PATH,
)
from sindhu.services.cctv_providers.hatyai import (
    HATYAI_CATALOG_PATH,
    HATYAI_CCTV_BASE_URL,
    HATYAI_HISTORY_PATH,
)
from sindhu.services.cctv_providers.rid import RID_CCTV_BASE_URL
from sindhu.services.cctv_providers.transport import (
    BANGKOK,
    MAX_HISTORY_FRAMES,
    SOURCE_DEADLINE_SECONDS,
    STALE_AFTER,
    UTC,
    utc,
)

# Backwards compatibility aliases
HATYAI_CCTV_API_BASE_URL = HATYAI_CCTV_BASE_URL
DWR_CCTV_API_BASE_URL = DWR_CCTV_BASE_URL
RID_CCTV_API_BASE_URL = RID_CCTV_BASE_URL

normalize_provider_base_url = validate_allowed_api_base_url

HATYAI_CATALOG_URL = join_provider_url(HATYAI_CCTV_API_BASE_URL, HATYAI_CATALOG_PATH)
HATYAI_HISTORY_URL = join_provider_url(HATYAI_CCTV_API_BASE_URL, HATYAI_HISTORY_PATH)
DWR_LIST_URL = join_provider_url(DWR_CCTV_API_BASE_URL, DWR_LIST_PATH)
DWR_SNAPSHOT_URL = join_provider_url(DWR_CCTV_API_BASE_URL, DWR_SNAPSHOT_PATH)
DWR_IMAGE_URL = join_provider_url(DWR_CCTV_API_BASE_URL, DWR_IMAGE_PATH)


class CctvSources:
    """Fetch and normalize Hatyai, DWR and RID CCTV data using a shared client."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        clock: Callable[[], dt.datetime] | None = None,
        deadline_seconds: float = SOURCE_DEADLINE_SECONDS,
        hatyai_base_url: str | None = None,
        dwr_base_url: str | None = None,
        rid_base_url: str | None = None,
        hatyai_api_base_url: str | None = None,
        dwr_api_base_url: str | None = None,
        rid_api_base_url: str | None = None,
    ) -> None:
        self.client = client
        self.clock = clock or (lambda: dt.datetime.now(UTC))
        self.deadline_seconds = max(0.1, float(deadline_seconds))
        if hatyai_base_url is not None and hatyai_api_base_url is not None:
            raise ValueError("configure only one Hatyai provider base URL")
        if dwr_base_url is not None and dwr_api_base_url is not None:
            raise ValueError("configure only one DWR provider base URL")
        if rid_base_url is not None and rid_api_base_url is not None:
            raise ValueError("configure only one RID provider base URL")
        self.hatyai_base_url = normalize_provider_base_url(
            hatyai_base_url or hatyai_api_base_url or HATYAI_CCTV_API_BASE_URL
        )
        self.dwr_base_url = normalize_provider_base_url(
            dwr_base_url or dwr_api_base_url or DWR_CCTV_API_BASE_URL
        )
        self.rid_base_url = normalize_provider_base_url(
            rid_base_url or rid_api_base_url or RID_CCTV_API_BASE_URL
        )
        self.transport = Transport(client, self.deadline_seconds)
        self.providers = build_providers(
            self.transport,
            self._now,
            {
                HATYAI_SOURCE: self.hatyai_base_url,
                DWR_SOURCE: self.dwr_base_url,
                RID_SOURCE: self.rid_base_url,
            },
        )

    def _now(self) -> dt.datetime:
        try:
            value = self.clock()
        except Exception:
            return dt.datetime.now(UTC)
        if not isinstance(value, dt.datetime):
            return dt.datetime.now(UTC)
        return utc(value)

    def _provider(self, source: str):
        provider = self.providers.get(source)
        if provider is None:
            raise SourceError("unknown_source")
        return provider

    async def latest(self, source: str) -> list[dict[str, Any]]:
        """Return one normalized latest record per registered camera."""

        provider = self._provider(source)
        try:
            async with asyncio.timeout(self.deadline_seconds):
                return await provider.latest()
        except SourceError:
            raise
        except asyncio.TimeoutError:
            raise SourceError("timeout") from None
        except Exception:
            raise SourceError("source_error") from None

    async def history(self, source: str, upstream_id: str) -> dict[str, Any]:
        """Return the provider's latest photos in chronological UTC order."""

        return await self._provider(source).history(upstream_id)

    async def snapshot_token(self, upstream_id: str) -> str | None:
        """Current dated DWR image path, usable as an ETag source."""

        return await self.providers[DWR_SOURCE].snapshot_token(upstream_id)

    async def snapshot(self, upstream_id: str, token: str | None = None) -> bytes:
        """Fetch one DWR JPEG through its official public image proxy."""

        body, _media_type = await self.providers[DWR_SOURCE].snapshot(
            upstream_id, token
        )
        return body

    async def rid_snapshot(self, upstream_id: str) -> tuple[bytes, str]:
        """Fetch a RID CGI image without exposing its legacy HTTP URL."""

        return await self.providers[RID_SOURCE].snapshot(upstream_id)


__all__ = [
    "BANGKOK",
    "CctvSources",
    "DWR_IMAGE_URL",
    "DWR_LIST_URL",
    "DWR_SNAPSHOT_URL",
    "HATYAI_CATALOG_URL",
    "HATYAI_HISTORY_URL",
    "MAX_HISTORY_FRAMES",
    "STALE_AFTER",
    "SourceError",
]
