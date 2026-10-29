"""The one interface every CCTV provider implements.

Services, routers and the UI ask a provider what it can do
(``history_supported``) instead of branching on its name, so adding a source
means writing one subclass and registering it in ``registry.py``.  Every
provider reports ``captured_at``: image freshness is derived from it alone.
"""

from __future__ import annotations

import datetime as dt
from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping
from copy import deepcopy
from typing import Any, ClassVar

from sindhu.services.cctv_providers.transport import (
    SourceError,
    Transport,
    iso,
)


def join_provider_url(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


class CctvProvider(ABC):
    # Identity and capabilities: plain class attributes so they can be read
    # without constructing (or mocking) a provider.
    source: ClassVar[str]
    provider_name: ClassVar[str]
    registry_version: ClassVar[str]
    cameras: ClassVar[tuple[Mapping[str, Any], ...]]
    history_supported: ClassVar[bool] = False

    def __init__(
        self,
        transport: Transport,
        *,
        base_url: str,
        now: Callable[[], dt.datetime],
    ) -> None:
        self.transport = transport
        self.base_url = base_url
        self.now = now

    def url(self, path: str) -> str:
        return join_provider_url(self.base_url, path)

    @abstractmethod
    def source_url(self) -> str:
        """Public page of the provider, shown as attribution."""

    @abstractmethod
    def detail_url(self, camera: Mapping[str, Any]) -> str:
        """Public page of one camera."""

    def base_record(
        self,
        camera: Mapping[str, Any],
        *,
        fetched_at: str,
        availability: str = "unknown",
        provider_status: str = "unknown",
        image_url: str | None = None,
        captured_at: dt.datetime | None = None,
    ) -> dict[str, Any]:
        """Build exactly the fields accepted by PublicVisualFeed."""

        return {
            "source": self.source,
            "upstream_id": str(camera["upstream_id"]),
            "slug": str(camera["slug"]),
            "title_th": str(camera["title_th"]),
            "code": str(camera["code"]),
            "coverage_group": str(camera["coverage_group"]),
            "media_type": "cctv",
            "coordinate_status": str(camera.get("coordinate_status", "unverified")),
            "coordinates": deepcopy(camera.get("coordinates")),
            "coordinate_provenance": deepcopy(camera.get("coordinate_provenance")),
            "registry_version": self.registry_version,
            "availability": availability,
            "provider_status": provider_status,
            "image_url": image_url,
            "detail_url": self.detail_url(camera),
            "captured_at": iso(captured_at),
            "fetched_at": fetched_at,
            "history_supported": self.history_supported,
            "attribution": {
                "provider": self.provider_name,
                "source_url": self.source_url(),
            },
        }

    @abstractmethod
    async def latest(self) -> list[dict[str, Any]]:
        """One normalized record per registered camera."""

    async def history(self, upstream_id: str) -> dict[str, Any]:
        raise SourceError("history_unsupported")

    async def snapshot_token(self, upstream_id: str) -> str | None:
        """Identity of the image that ``snapshot`` would return, without fetching it.

        Providers whose image changes under a stable token (DWR: the dated file
        path) return it so callers can answer ``If-None-Match`` cheaply.  ``None``
        means the provider has no such token.
        """
        return None

    async def snapshot(
        self, upstream_id: str, token: str | None = None
    ) -> tuple[bytes, str]:
        """Fetch one image through our proxy; returns ``(bytes, media_type)``.

        ``token`` is a value previously returned by ``snapshot_token``; passing it
        avoids resolving it a second time.
        """
        raise SourceError("snapshot_unsupported")
