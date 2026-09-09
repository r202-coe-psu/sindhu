"""Real ASGI + Redis cache integration with only external HTTP mocked."""

import datetime as dt
import os
import unittest
import uuid
from unittest.mock import patch

import httpx
import redis.asyncio as redis
from fastapi import FastAPI

from sindhu.api.routers.v1.visual_feeds import router
from sindhu.services import visual_feeds
from tests.visual_feeds.test_api_integration import upstream_handler


@unittest.skipUnless(
    os.environ.get("CCTV_TEST_REDIS_URL"), "opt-in local Redis required"
)
class ApiRedisTests(unittest.IsolatedAsyncioTestCase):
    async def test_latest_and_history_warm_cache_avoid_upstream_calls(self):
        db = redis.from_url(
            os.environ["CCTV_TEST_REDIS_URL"],
            socket_timeout=1,
            socket_connect_timeout=1,
        )
        prefix = "sindhu:cctv:api-test:" + uuid.uuid4().hex
        calls = []

        def external(request):
            calls.append(request.url.path)
            return upstream_handler(request)

        try:
            await db.ping()
            with patch.object(visual_feeds, "PREFIX", prefix):
                async with httpx.AsyncClient(
                    transport=httpx.MockTransport(external)
                ) as client:
                    visual_feeds.configure_visual_feeds(client, db)
                    app = FastAPI()
                    app.include_router(router, prefix="/v1")
                    async with httpx.AsyncClient(
                        transport=httpx.ASGITransport(app), base_url="http://test"
                    ) as api:
                        first = await api.get("/v1/visual-feeds")
                        self.assertEqual(first.status_code, 200, first.text)
                        self.assertEqual(first.json()["count"], 30)
                        count = len(calls)
                        again = await api.get("/v1/visual-feeds?media_type=cctv")
                        self.assertEqual(again.status_code, 200)
                        self.assertEqual(len(calls), count)
                        today = dt.datetime.now(visual_feeds.BANGKOK).date()
                        url = f"/v1/visual-feeds/hatyai_city_climate/9/history?date={today}"
                        history = await api.get(url)
                        self.assertEqual(history.status_code, 200, history.text)
                        count = len(calls)
                        self.assertEqual((await api.get(url)).json(), history.json())
                        self.assertEqual(len(calls), count)
                        keys = [k async for k in db.scan_iter(match=prefix + ":*")]
                        self.assertEqual(len(keys), 3)
                        for key in keys:
                            self.assertGreater(await db.ttl(key), 0)
                            raw = await db.get(key)
                            self.assertNotIn(b"fixture-secret", raw)
                            self.assertNotIn(b"raw_payload", raw)
        finally:
            visual_feeds.close_visual_feeds()
            keys = [k async for k in db.scan_iter(match=prefix + ":*")]
            if keys:
                await db.delete(*keys)
            await db.aclose()
