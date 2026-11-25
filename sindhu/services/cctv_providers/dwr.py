"""DWR (กรมทรัพยากรน้ำ): station list with CCTV flags and a snapshot path per camera."""

from __future__ import annotations

import asyncio
import datetime as dt
import re
from collections.abc import Mapping
from typing import Any

from sindhu.config.provider_urls import DEFAULT_DWR_CCTV_BASE_URL
from sindhu.services.cctv_catalog import (
    DWR_CAMERAS,
    DWR_REGISTRY_VERSION,
    DWR_SOURCE,
    get_camera,
)
from sindhu.services.cctv_providers.base import CctvProvider
from sindhu.services.cctv_providers.transport import (
    BANGKOK,
    MAX_RESPONSE_BYTES,
    STALE_AFTER,
    UTC,
    SourceError,
    dwr_proxy_url,
    iso,
    provider_bool,
)

DWR_CCTV_BASE_URL = DEFAULT_DWR_CCTV_BASE_URL
DWR_LIST_PATH = "/public/reportCctv/listPaginate"
DWR_SNAPSHOT_PATH = "/public/reportCctv/snapshot"
DWR_IMAGE_PATH = "/file/image/cctv"

# The snapshot-path endpoint occasionally answers with an empty 404 and succeeds
# on the next call, so transient failures are retried a couple of times.
SNAPSHOT_PATH_ATTEMPTS = 3
SNAPSHOT_PATH_RETRY_DELAY = 0.2
# Each camera's retries must fit well inside the source's refresh deadline, so a
# flaky camera degrades only itself, never the whole DWR catalog.
CAMERA_SNAPSHOT_BUDGET_SECONDS = 5.0
_RETRYABLE_PATH_ERRORS = frozenset(
    {"transport_error", "upstream_http_error", "invalid_json", "invalid_response"}
)

_SNAPSHOT_PATH = re.compile(
    r"^/(?P<station>[A-Za-z0-9_-]{1,64})/"
    r"(?P<year>[0-9]{4})/(?P<month>[0-9]{1,2})/(?P<day>[0-9]{1,2})/"
    r"(?P<hour>[0-9]{1,2})_(?P<minute>[0-9]{1,2})\.jpg$"
)


class DwrProvider(CctvProvider):
    source = DWR_SOURCE
    provider_name = "กรมทรัพยากรน้ำ"
    registry_version = DWR_REGISTRY_VERSION
    cameras = DWR_CAMERAS

    def source_url(self) -> str:
        return self.url("/")

    def detail_url(self, camera: Mapping[str, Any]) -> str:
        return self.url(f"/public/station/getByCode/{camera['station_code']}")

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

    async def latest(self) -> list[dict[str, Any]]:
        payload = await self.transport.json(
            "POST",
            self.url(DWR_LIST_PATH),
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

        online_cameras = [
            camera
            for camera in DWR_CAMERAS
            if str(camera["upstream_id"]) in by_id
            and provider_bool(by_id[str(camera["upstream_id"])].get("cctvOnline"))
            is True
        ]
        captures = dict(
            zip(
                (str(camera["upstream_id"]) for camera in online_cameras),
                await asyncio.gather(
                    *(self._capture(camera) for camera in online_cameras)
                ),
            )
        )

        now = self.now()
        fetched_at = iso(now)
        records: list[dict[str, Any]] = []
        for camera in DWR_CAMERAS:
            entity = by_id.get(str(camera["upstream_id"]))
            if entity is None:
                records.append(
                    self.base_record(
                        camera,
                        fetched_at=fetched_at,
                        provider_status="missing",
                    )
                )
                continue

            online = provider_bool(entity.get("cctvOnline"))
            # The provider status remains separate from the image retrieval
            # status; a camera can be online while its current public snapshot
            # is temporarily unavailable.
            captured_at, snapshot_error_code = captures.get(
                str(camera["upstream_id"]), (None, None)
            )
            snapshot_ok = captured_at is not None
            image_url = (
                dwr_proxy_url(str(camera["upstream_id"]), captured_at)
                if captured_at is not None
                else None
            )

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

    async def _capture(
        self, camera: Mapping[str, Any]
    ) -> tuple[dt.datetime | None, str | None]:
        """Capture time of one camera's current image, or why it is missing."""
        try:
            async with asyncio.timeout(CAMERA_SNAPSHOT_BUDGET_SECONDS):
                path = await self._snapshot_path(camera)
            return self._parse_snapshot_path(camera, path), None
        except SourceError as error:
            return None, error.code
        except TimeoutError:
            return None, "timeout"

    async def _snapshot_path(self, camera: Mapping[str, Any]) -> str:
        for attempt in range(1, SNAPSHOT_PATH_ATTEMPTS + 1):
            try:
                return await self._fetch_snapshot_path(camera)
            except SourceError as error:
                if (
                    error.code not in _RETRYABLE_PATH_ERRORS
                    or attempt == SNAPSHOT_PATH_ATTEMPTS
                ):
                    raise
                await asyncio.sleep(SNAPSHOT_PATH_RETRY_DELAY)
        raise SourceError("source_error")  # unreachable: the loop returns or raises

    async def _fetch_snapshot_path(self, camera: Mapping[str, Any]) -> str:
        payload = await self.transport.json(
            "GET",
            self.url(f"{DWR_SNAPSHOT_PATH}/{camera['upstream_id']}"),
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

    async def snapshot_token(self, upstream_id: str) -> str | None:
        """The current dated image path: it changes whenever the image does."""

        camera = get_camera(DWR_SOURCE, upstream_id)
        if camera is None:
            raise SourceError("unknown_camera")
        try:
            async with asyncio.timeout(self.transport.deadline_seconds):
                return await self._snapshot_path(camera)
        except SourceError:
            raise
        except asyncio.TimeoutError:
            raise SourceError("timeout") from None
        except Exception:
            raise SourceError("source_error") from None

    async def snapshot(
        self, upstream_id: str, token: str | None = None
    ) -> tuple[bytes, str]:
        """Fetch one DWR JPEG through its official public image proxy."""

        camera = get_camera(DWR_SOURCE, upstream_id)
        if camera is None:
            raise SourceError("unknown_camera")
        try:
            async with asyncio.timeout(self.transport.deadline_seconds):
                path = token if token is not None else await self._snapshot_path(camera)
                # Validate again immediately before using the proxy path.  It
                # must be source-derived and cannot contain a user URL/query.
                self._parse_snapshot_path(camera, path)
                response = await self.transport.request(
                    "POST",
                    self.url(DWR_IMAGE_PATH),
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
        return body, "image/jpeg"
