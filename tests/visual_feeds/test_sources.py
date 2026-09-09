from __future__ import annotations

import base64
import datetime as dt
import json
from pathlib import Path
import unittest

import httpx

from sindhu.schemas.visual_feeds import PublicVisualFeed
from sindhu.services.cctv_catalog import (
    DWR_CAMERAS,
    DWR_SOURCE,
    HATYAI_CAMERAS,
    HATYAI_SOURCE,
    get_camera,
)
from sindhu.services.cctv_sources import (
    CctvSources,
    DWR_IMAGE_URL,
    DWR_LIST_URL,
    DWR_SNAPSHOT_URL,
    HATYAI_CATALOG_URL,
    HATYAI_HISTORY_URL,
    SourceError,
)

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "cctv"
NOW = dt.datetime(2026, 9, 3, 4, 30, tzinfo=dt.timezone.utc)
DWR_ID = "0e976e02-8381-4f6e-988a-81ecbed96fb9"
DWR_OTHER_ID = "3e55f300-3d80-4520-acfa-7a12c2a6bef9"


def _json_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _response(request: httpx.Request, payload: object, status_code: int = 200):
    return httpx.Response(status_code, json=payload, request=request)


class CctvCatalogTests(unittest.TestCase):
    def test_catalog_is_exactly_28_hatyai_cctv_and_two_dwr_records(self):
        self.assertEqual(len(HATYAI_CAMERAS), 28)
        self.assertEqual(len(DWR_CAMERAS), 2)
        self.assertEqual(
            {camera["upstream_id"] for camera in DWR_CAMERAS},
            {DWR_ID, DWR_OTHER_ID},
        )
        self.assertNotIn("radartmd", {camera["slug"] for camera in HATYAI_CAMERAS})
        self.assertNotIn("weather", {camera["slug"] for camera in HATYAI_CAMERAS})

    def test_get_camera_returns_a_defensive_copy(self):
        camera = get_camera(HATYAI_SOURCE, "22")
        self.assertIsNotNone(camera)
        assert camera is not None
        camera["title_th"] = "mutated"
        self.assertNotEqual(get_camera(HATYAI_SOURCE, 22)["title_th"], "mutated")
        self.assertIsNone(get_camera("unknown", "22"))


class HatyaiSourceTests(unittest.IsolatedAsyncioTestCase):
    async def test_latest_uses_exact_filter_drops_unknown_and_validates_public_shape(
        self,
    ):
        fixture = _json_fixture("hatyai_catalog.json")
        observed: dict[str, object] = {}

        async def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(
                request.url,
                httpx.URL(HATYAI_CATALOG_URL).copy_merge_params(
                    {
                        "name": ",".join(camera["slug"] for camera in HATYAI_CAMERAS),
                    }
                ),
            )
            observed["params"] = dict(request.url.params)
            return _response(request, fixture)

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            records = await CctvSources(client, clock=lambda: NOW).latest(HATYAI_SOURCE)

        self.assertEqual(len(records), 28)
        self.assertEqual(
            {record["slug"] for record in records},
            {camera["slug"] for camera in HATYAI_CAMERAS},
        )
        self.assertEqual(
            observed["params"],
            {"name": ",".join(camera["slug"] for camera in HATYAI_CAMERAS)},
        )

        for record in records:
            self.assertEqual(
                set(record),
                {
                    "source",
                    "upstream_id",
                    "slug",
                    "title_th",
                    "code",
                    "coverage_group",
                    "media_type",
                    "coordinate_status",
                    "coordinates",
                    "coordinate_provenance",
                    "registry_version",
                    "availability",
                    "provider_status",
                    "image_url",
                    "detail_url",
                    "captured_at",
                    "fetched_at",
                    "history_supported",
                    "attribution",
                },
            )
            self.assertEqual(set(record["attribution"]), {"provider", "source_url"})
            self.assertNotIn("fixture-secret", json.dumps(record, ensure_ascii=False))
            PublicVisualFeed.model_validate(record)

        road30m = next(record for record in records if record["slug"] == "road30m")
        self.assertEqual(road30m["availability"], "online")
        self.assertEqual(road30m["captured_at"], "2026-09-03T04:00:00Z")
        self.assertEqual(
            road30m["image_url"],
            "https://photo.hatyaicityclimate.org/cctv/road30m.jpg",
        )
        self.assertNotIn("?", road30m["image_url"])

        disabled = next(record for record in records if record["slug"] == "hatyainai")
        self.assertEqual(disabled["availability"], "offline")
        malformed_time = next(
            record for record in records if record["slug"] == "muangkong"
        )
        self.assertEqual(malformed_time["availability"], "unknown")
        self.assertEqual(malformed_time["captured_at"], None)

    async def test_invalid_or_empty_catalog_is_a_typed_failure(self):
        async def empty_handler(request: httpx.Request) -> httpx.Response:
            return _response(request, {"count": 0, "items": []})

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(empty_handler)
        ) as client:
            with self.assertRaises(SourceError) as error:
                await CctvSources(client, clock=lambda: NOW).latest(HATYAI_SOURCE)
        self.assertEqual(error.exception.code, "invalid_catalog")
        self.assertNotIn("items", str(error.exception))

    async def test_history_uses_bangkok_date_exact_limit_and_chronological_order(self):
        fixture = _json_fixture("hatyai_history.json")
        observed: dict[str, object] = {}

        async def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.url.path, "/api/flood/cam")
            observed["params"] = dict(request.url.params)
            return _response(request, fixture)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            result = await CctvSources(client, clock=lambda: NOW).history(
                HATYAI_SOURCE, "22", "2026-09-03"
            )

        self.assertEqual(
            observed["params"],
            {"id": "22", "date": "2026-09-03", "items": "144", "show": "144"},
        )
        self.assertFalse(result["possibly_truncated"])
        self.assertEqual(
            [frame["captured_at"] for frame in result["frames"]],
            ["2026-09-03T03:05:00Z", "2026-09-03T04:05:00Z"],
        )
        self.assertNotIn("fixture-secret", json.dumps(result))
        self.assertTrue(
            all("?" not in frame["image_url"] for frame in result["frames"])
        )

        async def limited_handler(request: httpx.Request) -> httpx.Response:
            photos = []
            for minute in range(145):
                photos.append(
                    {
                        "atDate": f"2026-09-03T08:{minute % 60:02d}:00",
                        "photoUrl": f"https://photo.hatyaicityclimate.org/cctv/{minute}.jpg",
                    }
                )
            return _response(request, {"count": 145, "photos": photos})

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(limited_handler)
        ) as client:
            limited = await CctvSources(client, clock=lambda: NOW).history(
                HATYAI_SOURCE, 22, dt.date(2026, 9, 3)
            )
        self.assertEqual(len(limited["frames"]), 144)
        self.assertTrue(limited["possibly_truncated"])

    async def test_history_empty_is_success_and_upstream_error_is_typed(self):
        async def empty_handler(request: httpx.Request) -> httpx.Response:
            return _response(request, {"photos": []})

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(empty_handler)
        ) as client:
            self.assertEqual(
                await CctvSources(client, clock=lambda: NOW).history(
                    HATYAI_SOURCE, 22, "2026-09-03"
                ),
                {"frames": [], "possibly_truncated": False},
            )

        async def error_handler(request: httpx.Request) -> httpx.Response:
            return _response(request, {"error": "fixture-secret"}, 503)

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(error_handler)
        ) as client:
            with self.assertRaises(SourceError) as error:
                await CctvSources(client, clock=lambda: NOW).history(
                    HATYAI_SOURCE, 22, "2026-09-03"
                )
        self.assertEqual(error.exception.code, "upstream_http_error")
        self.assertNotIn("fixture-secret", str(error.exception))

    async def test_history_rejects_invalid_and_out_of_window_dates(self):
        async def handler(request: httpx.Request) -> httpx.Response:
            self.fail("date validation should happen before a request")

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            sources = CctvSources(client, clock=lambda: NOW)
            with self.assertRaises(SourceError) as invalid:
                await sources.history(HATYAI_SOURCE, 22, "2026-02-30")
            with self.assertRaises(SourceError) as old:
                await sources.history(HATYAI_SOURCE, 22, "2026-08-04")
        self.assertEqual(invalid.exception.code, "invalid_history_date")
        self.assertEqual(old.exception.code, "history_date_out_of_window")


class DwrSourceTests(unittest.IsolatedAsyncioTestCase):
    async def test_latest_filters_songkhla_known_identities_and_excludes_scoped_credentials(
        self,
    ):
        list_fixture = _json_fixture("dwr_list.json")
        paths = _json_fixture("dwr_snapshot_paths.json")
        calls: list[tuple[str, str, object]] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            calls.append((request.method, request.url.path, request.content))
            if request.url == httpx.URL(DWR_LIST_URL):
                self.assertEqual(
                    json.loads(request.content),
                    {
                        "paginate": {"page": 1, "pageSize": 500, "orders": []},
                        "search": {},
                    },
                )
                return _response(request, list_fixture)
            if request.url.path == f"/api/public/reportCctv/snapshot/{DWR_ID}":
                return _response(request, paths[DWR_ID])
            self.fail(f"unexpected request path: {request.url.path}")

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            records = await CctvSources(client, clock=lambda: NOW).latest(DWR_SOURCE)

        self.assertEqual(len(records), 2)
        for record in records:
            PublicVisualFeed.model_validate(record)
            self.assertEqual(set(record["attribution"]), {"provider", "source_url"})
        self.assertEqual(
            next(record for record in records if record["upstream_id"] == DWR_ID)[
                "image_url"
            ],
            "/v1/visual-feeds/dwr/0e976e02-8381-4f6e-988a-81ecbed96fb9/snapshot?v=1788408000",
        )
        offline = next(
            record for record in records if record["upstream_id"] == DWR_OTHER_ID
        )
        self.assertEqual(offline["availability"], "offline")
        self.assertIsNone(offline["image_url"])
        serialized = json.dumps(records, ensure_ascii=False)
        self.assertNotIn("fixture-secret", serialized)
        self.assertNotIn("cctvSnapshotLink", serialized)
        self.assertNotIn("cctvVideoLink", serialized)
        self.assertNotIn("userinfo", serialized)
        self.assertEqual(len([call for call in calls if "snapshot" in call[1]]), 1)

    async def test_snapshot_uses_validated_path_official_proxy_and_jpeg_validation(
        self,
    ):
        paths = _json_fixture("dwr_snapshot_paths.json")
        jpeg = base64.b64decode(
            (FIXTURES / "dwr_snapshot.jpg.b64").read_text(encoding="ascii")
        )
        observed: dict[str, object] = {}

        async def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith(f"/snapshot/{DWR_ID}"):
                return _response(request, paths[DWR_ID])
            self.assertEqual(request.url, httpx.URL(DWR_IMAGE_URL))
            observed["json"] = json.loads(request.content)
            return httpx.Response(
                200,
                headers={"content-type": "image/jpeg; charset=binary"},
                content=jpeg,
                request=request,
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            body = await CctvSources(client, clock=lambda: NOW).snapshot(DWR_ID)
        self.assertEqual(body, jpeg)
        self.assertEqual(observed["json"], {"path": "/TA200303/2026/9/3/11_0.jpg"})

    async def test_snapshot_rejects_redirect_mime_magic_and_size(self):
        async def redirect_handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                302,
                headers={"location": "https://evil.invalid/secret"},
                request=request,
            )

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(redirect_handler)
        ) as client:
            with self.assertRaises(SourceError) as error:
                await CctvSources(client).snapshot(DWR_ID)
        self.assertEqual(error.exception.code, "redirect_rejected")

        async def invalid_response_handler(
            request: httpx.Request,
        ) -> httpx.Response:
            if request.url.path.endswith(f"/snapshot/{DWR_ID}"):
                return _response(request, {"value": "/TA200303/2026/9/3/11_0.jpg"})
            return httpx.Response(
                200,
                headers={"content-type": "text/html"},
                content=b"\xff\xd8\xff",
                request=request,
            )

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(invalid_response_handler)
        ) as client:
            with self.assertRaises(SourceError) as mime_error:
                await CctvSources(client).snapshot(DWR_ID)
        self.assertEqual(mime_error.exception.code, "invalid_jpeg")

        async def bad_magic_handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith(f"/snapshot/{DWR_ID}"):
                return _response(request, {"value": "/TA200303/2026/9/3/11_0.jpg"})
            return httpx.Response(
                200,
                headers={"content-type": "image/jpeg"},
                content=b"not-a-jpeg",
                request=request,
            )

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(bad_magic_handler)
        ) as client:
            with self.assertRaises(SourceError) as magic_error:
                await CctvSources(client).snapshot(DWR_ID)
        self.assertEqual(magic_error.exception.code, "invalid_jpeg")

        async def oversized_handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith(f"/snapshot/{DWR_ID}"):
                return _response(request, {"value": "/TA200303/2026/9/3/11_0.jpg"})
            return httpx.Response(
                200,
                headers={"content-type": "image/jpeg"},
                content=b"\xff\xd8\xff" + b"x" * (2 * 1024 * 1024),
                request=request,
            )

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(oversized_handler)
        ) as client:
            with self.assertRaises(SourceError) as size_error:
                await CctvSources(client).snapshot(DWR_ID)
        self.assertEqual(size_error.exception.code, "response_too_large")

    async def test_snapshot_rejects_untrusted_or_malformed_paths_before_proxy(self):
        async def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith(f"/snapshot/{DWR_ID}"):
                return _response(
                    request,
                    {
                        "value": "https://camera.invalid/image.jpg?password=fixture-secret"
                    },
                )
            self.fail("proxy must not receive an invalid path")

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with self.assertRaises(SourceError) as error:
                await CctvSources(client).snapshot(DWR_ID)
        self.assertEqual(error.exception.code, "invalid_snapshot_path")
        self.assertNotIn("fixture-secret", str(error.exception))


if __name__ == "__main__":
    unittest.main()
