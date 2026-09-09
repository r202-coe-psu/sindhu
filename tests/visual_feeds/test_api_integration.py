"""Real ASGI -> service -> providers; only the external HTTP servers are mocked."""

import datetime as dt
import json
import unittest
from unittest.mock import patch

import httpx
from fastapi import FastAPI

from sindhu import models
from sindhu.api.routers.v1.visual_feeds import router
from sindhu.services import visual_feeds
from sindhu.services.cctv_catalog import HATYAI_CAMERAS

DWR_IDS = [
    "0e976e02-8381-4f6e-988a-81ecbed96fb9",
    "3e55f300-3d80-4520-acfa-7a12c2a6bef9",
]


def upstream_handler(request, *, history_date=None, source_failure=None):
    """Synthetic shapes reconstructed from observed official endpoints; no secrets."""
    now = dt.datetime.now(visual_feeds.BANGKOK)
    date = history_date or now.date()
    path = request.url.path
    if source_failure == "all" or (
        source_failure == "dwr" and request.url.host == "telemetry.dwr.go.th"
    ):
        return httpx.Response(503)
    if path in ("/api/flood/cameras", "/api/flood/cams"):
        items = [
            {
                "cameraId": int(c["upstream_id"]),
                "name": c["slug"],
                "code": c["code"],
                "title": c["title_th"],
                "enable": 1,
                "statusMsg": None,
                "atDate": now.strftime("%Y-%m-%d %H:%M:%S"),
                "photo": f"https://hatyaicityclimate.org/floodphoto/last/{c['slug']}.jpg",
                "token": "fixture-secret-not-real",
            }
            for c in HATYAI_CAMERAS
        ]
        return httpx.Response(200, json={"count": len(items), "items": items})
    if path == "/api/flood/cam":
        requested = request.url.params.get("date", date.isoformat())
        return httpx.Response(
            200,
            json={
                "cameraId": int(request.url.params["id"]),
                "token": "fixture-secret-not-real",
                "photos": [
                    {
                        "atDate": f"{requested} 02:00:00",
                        "photoUrl": "https://hatyaicityclimate.org/floodphoto/cam/2.jpg",
                    },
                    {
                        "atDate": f"{requested} 01:00:00",
                        "photoUrl": "https://hatyaicityclimate.org/floodphoto/cam/1.jpg",
                    },
                ],
            },
        )
    if path == "/api/public/reportCctv/listPaginate":
        assert request.method == "POST"
        return httpx.Response(
            200,
            json={
                "value": {
                    "totalCount": 2,
                    "results": [
                        {
                            "provinceNameTh": "สงขลา",
                            "entity": {
                                "id": ident,
                                "stationCode": f"TA20030{3+i}",
                                "stnNameTh": "คลองอู่ตะเภา",
                                "cctvOnline": True,
                                "cctvSnapshotLink": "http://fixture:secret@camera.invalid/snap.jpg",
                            },
                        }
                        for i, ident in enumerate(DWR_IDS)
                    ],
                }
            },
        )
    if path.startswith("/api/public/reportCctv/snapshot/"):
        i = DWR_IDS.index(path.rsplit("/", 1)[1])
        return httpx.Response(
            200,
            json={
                "value": f"/TA20030{3+i}/{now.year}/{now.month}/{now.day}/{now.hour}_{now.minute}.jpg"
            },
        )
    if path == "/api/file/image/cctv":
        assert request.method == "POST"
        assert json.loads(request.content)["path"].startswith("/TA20030")
        return httpx.Response(
            200,
            content=b"\xff\xd8\xff\xe0" + b"fixture" + b"\xff\xd9",
            headers={"content-type": "image/jpeg"},
        )
    return httpx.Response(404)


class ViewerASGITests(unittest.IsolatedAsyncioTestCase):
    async def test_map_coordinates_keep_longitude_first_and_unknown_camera_null(self):
        response = await self.api.get("/v1/visual-feeds?has_coordinates=true")
        self.assertEqual(response.status_code, 200, response.text)
        feeds = response.json()["visual_feeds"]
        self.assertEqual(len(feeds), 29)
        for feed in feeds:
            longitude, latitude = feed["coordinates"]["coordinates"]
            self.assertTrue(100 < longitude < 101)
            self.assertTrue(6 < latitude < 8)
            self.assertEqual(feed["coordinate_status"], "verified")
            self.assertEqual(
                feed["registry_version"],
                feed["coordinate_provenance"]["registry_version"],
            )
        muangkong = next(f for f in feeds if f["slug"] == "muangkong")
        self.assertEqual(
            muangkong["coordinates"]["coordinates"], [100.438272, 6.823193]
        )
        missing = await self.api.get("/v1/visual-feeds?has_coordinates=false")
        self.assertEqual(missing.json()["count"], 1)
        self.assertEqual(missing.json()["visual_feeds"][0]["slug"], "kalyanamit")
        self.assertIsNone(missing.json()["visual_feeds"][0]["coordinates"])

    async def asyncSetUp(self):
        self.failure = None
        self.upstream_calls = []

        def handler(request):
            self.upstream_calls.append((request.method, str(request.url)))
            return upstream_handler(request, source_failure=self.failure)

        self.external = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        visual_feeds.configure_visual_feeds(self.external, None)
        app = FastAPI()
        app.include_router(router, prefix="/v1")
        self.api = httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="http://test"
        )

    async def asyncTearDown(self):
        await self.api.aclose()
        await self.external.aclose()
        visual_feeds.close_visual_feeds()

    async def test_full_path_cctv_only_and_no_mongo_or_secrets(self):
        with (
            patch.object(
                models.VisualFeed, "find", side_effect=AssertionError("Mongo called")
            ),
            patch.object(
                models.VisualFeed,
                "find_one",
                side_effect=AssertionError("Mongo called"),
            ),
        ):
            response = await self.api.get("/v1/visual-feeds?media_type=cctv")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers["cache-control"], "no-store")
        payload = response.json()
        self.assertEqual(payload["count"], 30)
        self.assertEqual({f["media_type"] for f in payload["visual_feeds"]}, {"cctv"})
        for banned in (
            "fixture-secret",
            "raw_payload",
            "cctvSnapshotLink",
            "token",
            "camera.invalid",
        ):
            self.assertNotIn(banned, response.text)
        dwr = [f for f in payload["visual_feeds"] if f["source"] == "dwr"]
        self.assertEqual(len(dwr), 2)
        self.assertTrue(
            all(f["image_url"].startswith("/v1/visual-feeds/dwr/") for f in dwr)
        )

    async def test_history_public_shape_and_date_validation(self):
        date = dt.datetime.now(visual_feeds.BANGKOK).date()
        response = await self.api.get(
            f"/v1/visual-feeds/hatyai_city_climate/9/history?date={date}"
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(len(response.json()["frames"]), 2)
        self.assertNotIn("token", response.text)
        for date in ("bad", "1900-01-01", "9999-12-31"):
            r = await self.api.get(
                f"/v1/visual-feeds/hatyai_city_climate/9/history?date={date}"
            )
            self.assertEqual(r.status_code, 422)

    async def test_partial_and_total_failure(self):
        self.failure = "dwr"
        r = await self.api.get("/v1/visual-feeds")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["count"], 28)
        self.assertEqual(
            r.json()["source_health"]["dwr"]["error"], "source_unavailable"
        )
        self.failure = "all"
        r = await self.api.get("/v1/visual-feeds")
        self.assertEqual(r.status_code, 503)

    async def test_unknown_id_and_unsupported_history_no_fetch(self):
        for path, expected in [
            ("/v1/visual-feeds/unknown/9", 404),
            (f"/v1/visual-feeds/dwr/{DWR_IDS[0]}/history?date=2026-09-03", 400),
            ("/v1/visual-feeds/dwr/unknown/snapshot", 404),
        ]:
            r = await self.api.get(path)
            self.assertEqual(r.status_code, expected, r.text)
        self.assertEqual(self.upstream_calls, [])

    async def test_snapshot_etag_and_content_type(self):
        url = f"/v1/visual-feeds/dwr/{DWR_IDS[0]}/snapshot"
        r = await self.api.get(url)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.headers["content-type"], "image/jpeg")
        self.assertEqual(r.headers["cache-control"], "private, max-age=120")
        again = await self.api.get(url, headers={"if-none-match": r.headers["etag"]})
        self.assertEqual(again.status_code, 304)
        self.assertEqual(again.content, b"")
