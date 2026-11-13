import asyncio
import datetime as dt
import unittest
from email.utils import format_datetime
from unittest.mock import AsyncMock, patch

import httpx

from sindhu.services.cctv_catalog import DWR_SOURCE, HATYAI_SOURCE, RID_SOURCE
from sindhu.services.cctv_providers import rid
from sindhu.services.cctv_providers import (
    PROVIDER_BY_SOURCE,
    SOURCES,
    CctvProvider,
    SourceError,
    Transport,
    build_providers,
)

NOW = dt.datetime(2026, 9, 3, 4, 30, tzinfo=dt.timezone.utc)


class MinimalProvider(CctvProvider):
    """The smallest valid provider: only ``latest`` is required."""

    source = "minimal"
    provider_name = "Minimal"
    registry_version = "v1"
    cameras = ()

    def source_url(self) -> str:
        return "https://example.test/"

    def detail_url(self, camera) -> str:
        return "https://example.test/camera"

    async def latest(self):
        return []


def _providers():
    return build_providers(
        Transport(AsyncMock(), 1.0),
        lambda: NOW,
        {
            HATYAI_SOURCE: "https://hatyaicityclimate.org",
            DWR_SOURCE: "https://telemetry.dwr.go.th/api",
            RID_SOURCE: "https://telerid.rid.go.th",
        },
    )


class ProviderCapabilityTests(unittest.IsolatedAsyncioTestCase):
    def test_registry_lists_every_source_once_in_display_order(self) -> None:
        self.assertEqual(SOURCES, (HATYAI_SOURCE, DWR_SOURCE, RID_SOURCE))
        self.assertEqual(set(PROVIDER_BY_SOURCE), set(SOURCES))

    def test_only_hatyai_has_history(self) -> None:
        self.assertEqual(
            {s for s, p in PROVIDER_BY_SOURCE.items() if p.history_supported},
            {HATYAI_SOURCE},
        )

    def test_records_advertise_the_capabilities_of_their_provider(self) -> None:
        for source, provider in _providers().items():
            camera = provider.cameras[0]
            record = provider.base_record(camera, fetched_at="2026-09-03T04:30:00Z")
            self.assertEqual(record["source"], source)
            self.assertEqual(record["history_supported"], provider.history_supported)
            self.assertEqual(record["registry_version"], provider.registry_version)
            self.assertEqual(
                record["attribution"]["provider"],
                PROVIDER_BY_SOURCE[source].provider_name,
            )

    async def test_unsupported_operations_fail_through_the_base_class(self) -> None:
        provider = MinimalProvider(
            Transport(AsyncMock(), 1.0),
            base_url="https://example.test",
            now=lambda: NOW,
        )
        with self.assertRaises(SourceError) as history:
            await provider.history("1")
        with self.assertRaises(SourceError) as snapshot:
            await provider.snapshot("1")

        self.assertEqual(history.exception.code, "history_unsupported")
        self.assertEqual(snapshot.exception.code, "snapshot_unsupported")

    async def test_existing_providers_inherit_the_same_defaults(self) -> None:
        providers = _providers()
        for source, operation in (
            (DWR_SOURCE, "history"),
            (RID_SOURCE, "history"),
            (HATYAI_SOURCE, "snapshot"),
        ):
            with self.subTest(source=source, operation=operation):
                with self.assertRaises(SourceError):
                    await getattr(providers[source], operation)("1")


class RidCaptureTimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_capture_time_is_the_camera_servers_last_modified(self) -> None:
        written = NOW - dt.timedelta(minutes=12)
        methods = set()

        def handler(request: httpx.Request) -> httpx.Response:
            methods.add(request.method)
            if request.url.path == "/CCTV/STN04/image.cgi":
                headers = {"last-modified": format_datetime(written, usegmt=True)}
                return httpx.Response(200, headers=headers)
            return httpx.Response(200)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = build_providers(
                Transport(client, 5.0),
                lambda: NOW,
                {
                    HATYAI_SOURCE: "https://hatyaicityclimate.org",
                    DWR_SOURCE: "https://telemetry.dwr.go.th/api",
                    RID_SOURCE: "http://rid.example.test",
                },
            )[RID_SOURCE]
            records = {r["upstream_id"]: r for r in await provider.latest()}

        self.assertEqual(methods, {"HEAD"})
        self.assertEqual(
            dt.datetime.fromisoformat(records["STN04"]["captured_at"]), written
        )
        self.assertIsNone(records["STN07"]["captured_at"])
        self.assertEqual(
            records["STN07"]["provider_status"], "capture_time_unavailable"
        )

    async def test_a_hung_camera_loses_only_its_own_capture_time(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/CCTV/STN04/image.cgi":
                await asyncio.sleep(5)
            return httpx.Response(
                200, headers={"last-modified": format_datetime(NOW, usegmt=True)}
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = build_providers(
                Transport(client, 10.0),
                lambda: NOW,
                {
                    HATYAI_SOURCE: "https://hatyaicityclimate.org",
                    DWR_SOURCE: "https://telemetry.dwr.go.th/api",
                    RID_SOURCE: "http://rid.example.test",
                },
            )[RID_SOURCE]
            with patch.object(rid, "LAST_MODIFIED_TIMEOUT_SECONDS", 0.05):
                records = {r["upstream_id"]: r for r in await provider.latest()}

        self.assertIsNone(records["STN04"]["captured_at"])
        self.assertIsNotNone(records["STN07"]["captured_at"])
