"""Hatyai City Climate: catalog of latest photos plus a per-camera photo history."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit

from sindhu.config.provider_urls import DEFAULT_HATYAI_CCTV_BASE_URL
from sindhu.services.cctv_catalog import (
    HATYAI_CAMERAS,
    HATYAI_REGISTRY_VERSION,
    HATYAI_SOURCE,
    get_camera,
)
from sindhu.services.cctv_providers.base import CctvProvider
from sindhu.services.cctv_providers.transport import (
    BANGKOK,
    MAX_HISTORY_FRAMES,
    STALE_AFTER,
    SourceError,
    iso,
    parse_provider_time,
    provider_bool,
    safe_upstream_url,
)

HATYAI_HOSTS = frozenset(
    {
        "hatyaicityclimate.org",
        "www.hatyaicityclimate.org",
        "photo.hatyaicityclimate.org",
    }
)
HATYAI_CCTV_BASE_URL = DEFAULT_HATYAI_CCTV_BASE_URL
HATYAI_CATALOG_PATH = "/api/flood/cams"
HATYAI_HISTORY_PATH = "/api/flood/cam"
HATYAI_SOURCE_PATH = "/flood/map/camera"
HATYAI_DETAIL_PATH = "/flood/cam"


class HatyaiProvider(CctvProvider):
    source = HATYAI_SOURCE
    provider_name = "Hatyai City Climate"
    registry_version = HATYAI_REGISTRY_VERSION
    cameras = HATYAI_CAMERAS
    history_supported = True

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        try:
            configured_host = urlsplit(self.base_url).hostname
            configured_port = urlsplit(self.base_url).port
        except ValueError:
            configured_host = None
            configured_port = None
        self.hatyai_image_hosts = HATYAI_HOSTS | (
            frozenset({configured_host}) if configured_host else frozenset()
        )
        self.hatyai_image_ports = frozenset({None, 443, configured_port})

    def source_url(self) -> str:
        return self.url(HATYAI_SOURCE_PATH)

    def detail_url(self, camera: Mapping[str, Any]) -> str:
        return self.url(f"{HATYAI_DETAIL_PATH}/{camera['slug']}")

    async def latest(self) -> list[dict[str, Any]]:
        slugs = ",".join(str(camera["slug"]) for camera in HATYAI_CAMERAS)
        payload = await self.transport.json(
            "GET",
            self.url(HATYAI_CATALOG_PATH),
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

        now = self.now()
        fetched_at = iso(now)
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
                    self.base_record(
                        camera,
                        fetched_at=fetched_at,
                        provider_status="missing",
                    )
                )
                continue

            captured_at = parse_provider_time(item.get("atDate"))
            image_url = safe_upstream_url(
                item.get("photo"),
                self.hatyai_image_hosts,
                default_host=urlsplit(self.base_url).netloc,
                allowed_ports=self.hatyai_image_ports,
            )
            enabled_value = item.get("enable")
            enabled = provider_bool(enabled_value)
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
                self.base_record(
                    camera,
                    fetched_at=fetched_at,
                    availability=availability,
                    provider_status=provider_status,
                    image_url=image_url,
                    captured_at=captured_at,
                )
            )

        return records

    async def history(self, upstream_id: str) -> dict[str, Any]:
        """Return the provider's latest Hatyai photos in chronological UTC order."""

        camera = get_camera(self.source, upstream_id)
        if camera is None:
            raise SourceError("unknown_camera")
        try:
            async with asyncio.timeout(self.transport.deadline_seconds):
                # The provider sends its latest photos and ignores date filters.
                payload = await self.transport.json(
                    "GET",
                    self.url(HATYAI_HISTORY_PATH),
                    params={"camId": str(camera["upstream_id"])},
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
        available_dates: set[str] = set()
        valid_photo_count = 0
        for photo in selected:
            if not isinstance(photo, Mapping):
                continue
            captured_at = parse_provider_time(photo.get("atDate"))
            image_url = safe_upstream_url(
                photo.get("photoUrl"),
                self.hatyai_image_hosts,
                default_host=urlsplit(self.base_url).netloc,
                allowed_ports=self.hatyai_image_ports,
            )
            if captured_at is None or image_url is None:
                continue
            valid_photo_count += 1
            available_dates.add(captured_at.astimezone(BANGKOK).date().isoformat())
            thumbnail_url = safe_upstream_url(
                photo.get("thumbUrl"),
                self.hatyai_image_hosts,
                default_host=urlsplit(self.base_url).netloc,
                allowed_ports=self.hatyai_image_ports,
            )
            frames.append(
                {
                    "captured_at": iso(captured_at),
                    "image_url": image_url,
                    "thumbnail_url": thumbnail_url,
                }
            )

        frames.sort(key=lambda frame: (frame["captured_at"], frame["image_url"]))
        if photos and not valid_photo_count:
            raise SourceError("invalid_history")
        return {
            "frames": frames,
            "available_dates": sorted(available_dates),
            "possibly_truncated": possibly_truncated,
        }
