"""RID (กรมชลประทาน): curated CGI cameras served through our same-origin proxy."""

from __future__ import annotations

import asyncio
import datetime as dt
from collections.abc import Mapping
from email.utils import parsedate_to_datetime
from typing import Any

from sindhu.services.cctv_catalog import (
    RID_CAMERAS,
    RID_PUBLIC_SOURCE_URL,
    RID_REGISTRY_VERSION,
    RID_SOURCE,
    get_camera,
)
from sindhu.services.cctv_providers.base import CctvProvider
from sindhu.services.cctv_providers.transport import SourceError, iso
from sindhu.config.provider_urls import DEFAULT_RID_CCTV_BASE_URL

RID_CCTV_BASE_URL = DEFAULT_RID_CCTV_BASE_URL
RID_IMAGE_PATH = "/CCTV/{station_code}/image.cgi"
# A hung camera host must cost only its own capture time, never the RID catalog.
LAST_MODIFIED_TIMEOUT_SECONDS = 3.0


class RidProvider(CctvProvider):
    source = RID_SOURCE
    provider_name = "กรมชลประทาน (RID)"
    registry_version = RID_REGISTRY_VERSION
    cameras = RID_CAMERAS

    def source_url(self) -> str:
        return RID_PUBLIC_SOURCE_URL

    def detail_url(self, camera: Mapping[str, Any]) -> str:
        return RID_PUBLIC_SOURCE_URL

    async def latest(self) -> list[dict[str, Any]]:
        """Expose curated RID CGI cameras through our same-origin proxy.

        The CGI image carries no timestamp of its own, but the camera server's
        ``Last-Modified`` header is when the camera last wrote it.
        """
        fetched_at = iso(self.now())
        captured = await asyncio.gather(
            *(self._last_modified(camera) for camera in RID_CAMERAS)
        )
        return [
            self.base_record(
                camera,
                fetched_at=fetched_at,
                image_url=f"/v1/visual-feeds/rid/{camera['upstream_id']}/snapshot",
                provider_status=(
                    "last_modified" if captured_at else "capture_time_unavailable"
                ),
                captured_at=captured_at,
            )
            for camera, captured_at in zip(RID_CAMERAS, captured)
        ]

    async def _last_modified(self, camera: Mapping[str, Any]) -> dt.datetime | None:
        try:
            async with asyncio.timeout(LAST_MODIFIED_TIMEOUT_SECONDS):
                response = await self.transport.request(
                    "HEAD", self._image_url(camera)
                )
        except (SourceError, TimeoutError):
            return None
        value = next(
            (v for k, v in response.headers.items() if k.lower() == "last-modified"),
            None,
        )
        try:
            return parsedate_to_datetime(value) if value else None
        except (TypeError, ValueError):
            return None

    def _image_url(self, camera: Mapping[str, Any]) -> str:
        return self.url(RID_IMAGE_PATH.format(station_code=camera["code"]))

    async def snapshot(
        self, upstream_id: str, token: str | None = None
    ) -> tuple[bytes, str]:
        """Fetch a RID CGI image without exposing its legacy HTTP URL."""
        camera = get_camera(RID_SOURCE, upstream_id)
        if camera is None:
            raise SourceError("unknown_camera")
        response = await self.transport.request("GET", self._image_url(camera))
        body = response.content
        if body.startswith(b"\xff\xd8\xff"):
            return body, "image/jpeg"
        if body.startswith((b"GIF87a", b"GIF89a")):
            return body, "image/gif"
        raise SourceError("invalid_image")
