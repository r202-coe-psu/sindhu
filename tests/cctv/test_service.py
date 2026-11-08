import asyncio
import datetime as dt
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx

from sindhu import models
from sindhu.schemas.visual_feeds import (
    Availability,
    ImageFreshness,
    MediaType,
    PublicVisualFeed,
)
from sindhu.services import visual_feeds as service


def record(source="hatyai_city_climate", id="9", **overrides):
    return (
        dict(
            source=source,
            upstream_id=id,
            slug="muangkong",
            title_th="สะพานม่วงก็อง",
            coverage_group="hatyai_city",
            media_type="cctv",
            availability="online",
            image_url="https://hatyaicityclimate.org/floodphoto/last/muangkong.jpg?v=123",
            captured_at=dt.datetime.now(dt.timezone.utc).isoformat(),
            fetched_at=dt.datetime.now(dt.timezone.utc).isoformat(),
            history_supported=source == "hatyai_city_climate",
            attribution={
                "provider": "Hatyai City Climate",
                "source_url": "https://hatyaicityclimate.org",
            },
        )
        | overrides
    )


class ImmediateCache:
    def __init__(self):
        self.calls = []

    async def get(self, key, loader, **kwargs):
        self.calls.append((key, kwargs))
        return SimpleNamespace(
            value=await loader(),
            fetched_at=dt.datetime.now(dt.timezone.utc),
            stale=False,
            error=None,
        )


class VisualFeedServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.client = httpx.AsyncClient()
        self.cache = ImmediateCache()
        self.provider = SimpleNamespace(
            latest=AsyncMock(return_value=[record()]),
            history=AsyncMock(),
            snapshot=AsyncMock(),
            rid_snapshot=AsyncMock(return_value=(b"image", "image/jpeg")),
        )
        self.viewer = service.VisualFeedService(
            self.client, None, sources=self.provider, cache=self.cache
        )

    async def asyncTearDown(self):
        await self.client.aclose()

    async def test_no_mongo_and_filters_applied_after_source_cache(self):
        async def latest(source):
            if source == "dwr":
                raise RuntimeError("DO_NOT_EXPOSE_password")
            return [record()]

        self.provider.latest.side_effect = latest
        with (
            patch.object(
                models.VisualFeed, "find", side_effect=AssertionError("Mongo read")
            ),
            patch.object(
                models.VisualFeed, "find_one", side_effect=AssertionError("Mongo read")
            ),
        ):
            feeds, health = await self.viewer.list(
                media_type=MediaType.CCTV,
                coverage_group="hatyai_city",
                has_coordinates=False,
            )
            self.assertEqual(len(feeds), 1)
            self.assertEqual(health["dwr"].error, "source_unavailable")
            self.assertNotIn("password", str(health))
            self.assertEqual(len(self.cache.calls), 3)
            self.assertEqual(
                self.cache.calls[0][0],
                f"sindhu:cctv:v1:latest:hatyai_city_climate:{service.HATYAI_REGISTRY_VERSION}:r{self.viewer._source_config_revision}",
            )

    async def test_cached_latest_uses_24_hour_freshness_window(self):
        now = dt.datetime.now(dt.timezone.utc)
        for age, expected in (
            (dt.timedelta(hours=23), Availability.ONLINE),
            (dt.timedelta(hours=25), Availability.STALE),
        ):
            with self.subTest(age=age):
                self.provider.latest.return_value = [
                    record(captured_at=(now - age).isoformat())
                ]
                feeds, _ = await self.viewer._catalog("hatyai_city_climate")
                self.assertEqual(feeds[0].availability, expected)

    def test_image_freshness_requires_recent_timestamp_and_image_url(self):
        now = dt.datetime(2026, 9, 3, 4, 30, tzinfo=dt.timezone.utc)
        cases = (
            (dt.timedelta(0), "https://hatyaicityclimate.org/latest.jpg", "fresh"),
            (
                dt.timedelta(hours=1),
                "https://hatyaicityclimate.org/latest.jpg",
                "fresh",
            ),
            (
                dt.timedelta(hours=1, microseconds=1),
                "https://hatyaicityclimate.org/latest.jpg",
                "stale",
            ),
            (
                dt.timedelta(minutes=-5),
                "https://hatyaicityclimate.org/latest.jpg",
                "fresh",
            ),
            (
                dt.timedelta(hours=-1),
                "https://hatyaicityclimate.org/latest.jpg",
                "stale",
            ),
        )
        for age, image_url, expected in cases:
            with self.subTest(age=age, image_url=image_url):
                feed = PublicVisualFeed.model_validate(
                    record(
                        image_url=image_url,
                        captured_at=(now - age).isoformat(),
                    )
                )
                self.assertEqual(service.image_freshness_for(feed, now).value, expected)

        for overrides in (
            {"image_url": None},
            {"image_url": "   "},
            {"captured_at": None},
            {"captured_at": "not-a-timestamp"},
            {"captured_at": "2026-09-03T05:00:00Z"},
        ):
            with self.subTest(overrides=overrides):
                feed = PublicVisualFeed.model_validate(record(**overrides))
                self.assertEqual(
                    service.image_freshness_for(feed, now), ImageFreshness.STALE
                )

    async def test_freshness_is_judged_when_the_provider_was_asked(self):
        # A 29-minute-old cache entry about a photo that was 40 minutes old
        # then: the camera was online, and cache age must not flip it.
        now = dt.datetime.now(dt.timezone.utc)
        fetched_at = now - dt.timedelta(minutes=29)
        self.provider.latest.return_value = [
            record(
                captured_at=(fetched_at - dt.timedelta(minutes=40)).isoformat(),
                fetched_at=fetched_at.isoformat(),
            )
        ]

        feeds, _ = await self.viewer._catalog("hatyai_city_climate")

        self.assertEqual(feeds[0].image_freshness, ImageFreshness.FRESH)

    def test_rid_freshness_uses_capture_time_like_every_source(self):
        now = dt.datetime(2026, 9, 3, 4, 30, tzinfo=dt.timezone.utc)
        for captured_at, expected in (
            (now.isoformat(), ImageFreshness.FRESH),
            ((now - dt.timedelta(days=2)).isoformat(), ImageFreshness.STALE),
            (None, ImageFreshness.STALE),
        ):
            with self.subTest(captured_at=captured_at):
                feed = PublicVisualFeed.model_validate(
                    record(
                        source="rid",
                        id="STN04",
                        image_url="/v1/visual-feeds/rid/STN04/snapshot",
                        captured_at=captured_at,
                        history_supported=False,
                    )
                )
                self.assertEqual(service.image_freshness_for(feed, now), expected)

    async def test_concurrent_rid_snapshots_wait_for_bounded_capacity(self):
        active = 0
        max_active = 0
        first_pair_started = asyncio.Event()
        release = asyncio.Event()

        async def fetch(_upstream_id):
            nonlocal active, max_active
            active += 1
            max_active = max(max_active, active)
            if active == service.SNAPSHOT_CONCURRENCY:
                first_pair_started.set()
            try:
                await release.wait()
                return b"image", "image/jpeg"
            finally:
                active -= 1

        self.provider.rid_snapshot.side_effect = fetch
        requests = [
            asyncio.create_task(self.viewer.rid_snapshot(upstream_id))
            for upstream_id in ("STN04", "STN07", "STN08")
        ]
        await first_pair_started.wait()
        await asyncio.sleep(0)
        self.assertFalse(requests[2].done())
        release.set()
        results = await asyncio.gather(*requests)

        self.assertEqual(len(results), 3)
        self.assertEqual(max_active, service.SNAPSHOT_CONCURRENCY)

    async def test_recent_image_freshness_is_independent_of_provider_availability(self):
        self.provider.latest.return_value = [
            record(
                availability="offline",
                captured_at=dt.datetime.now(dt.timezone.utc).isoformat(),
            )
        ]

        feeds, _ = await self.viewer._catalog("hatyai_city_climate")

        self.assertEqual(feeds[0].availability, Availability.OFFLINE)
        self.assertEqual(feeds[0].image_freshness, ImageFreshness.FRESH)

    async def test_non_cctv_never_calls_provider(self):
        self.assertEqual(await self.viewer.list(media_type=MediaType.RADAR), ([], {}))
        self.provider.latest.assert_not_awaited()

    async def test_all_sources_fail_is_503_not_empty_success(self):
        self.provider.latest.side_effect = RuntimeError("secret")
        with self.assertRaises(service.ViewerError) as err:
            await self.viewer.list()
        self.assertEqual(err.exception.status_code, 503)

    async def test_strict_public_boundary_blocks_extra_fields_before_cache(self):
        self.provider.latest.return_value = [record(token="secret")]
        with self.assertRaises(service.ViewerError):
            await self.viewer.list()

    async def test_unknown_camera_does_not_fetch(self):
        self.assertIsNone(await self.viewer.get("hatyai_city_climate", "../secret"))
        self.provider.latest.assert_not_awaited()

    async def test_history_is_source_scoped_sorted_and_no_raw_passthrough(self):
        today = dt.datetime.now(service.BANGKOK).date()

        def frame(hour):
            return {
                "captured_at": dt.datetime.combine(
                    today, dt.time(hour), service.BANGKOK
                ).isoformat(),
                "image_url": f"https://hatyaicityclimate.org/floodphoto/cam/{hour}.jpg",
            }

        self.provider.history.return_value = {
            "frames": [frame(2), frame(1)],
            "possibly_truncated": False,
            "token": "secret",
        }
        result = await self.viewer.history("hatyai_city_climate", "9", today)
        self.assertEqual(
            result.frames[0].captured_at.astimezone(service.BANGKOK).hour, 1
        )
        self.assertNotIn("secret", result.model_dump_json())
        self.assertEqual(
            self.cache.calls[0][0],
            "sindhu:cctv:v1:history:hatyai_city_climate:9",
        )
        self.provider.history.assert_awaited_with("hatyai_city_climate", "9")

    async def test_empty_history_success_and_dwr_unsupported(self):
        self.provider.history.return_value = {"frames": [], "possibly_truncated": False}
        today = dt.datetime.now(service.BANGKOK).date()
        result = await self.viewer.history("hatyai_city_climate", "9", today)
        self.assertEqual(result.frames, [])
        with self.assertRaises(service.ViewerError) as error:
            await self.viewer.history(
                "dwr", "0e976e02-8381-4f6e-988a-81ecbed96fb9", today
            )
        self.assertEqual(error.exception.status_code, 400)

    async def test_history_returns_whole_photo_set_or_filters_one_day(self):
        today = dt.datetime.now(service.BANGKOK).date()
        yesterday = today - dt.timedelta(days=1)

        def frame(day, hour):
            return {
                "captured_at": dt.datetime.combine(
                    day, dt.time(hour), service.BANGKOK
                ).isoformat(),
                "image_url": f"https://hatyaicityclimate.org/{day}-{hour}.jpg",
            }

        self.provider.history.return_value = {
            "frames": [frame(today, 1), frame(yesterday, 23), frame(yesterday, 1)],
            "available_dates": [yesterday.isoformat(), today.isoformat()],
            "possibly_truncated": True,
        }
        everything = await self.viewer.history("hatyai_city_climate", "9")
        self.assertIsNone(everything.date)
        self.assertEqual(len(everything.frames), 3)
        self.assertEqual(everything.available_dates, [yesterday, today])

        one_day = await self.viewer.history("hatyai_city_climate", "9", yesterday)
        self.assertEqual(
            [f.captured_at.astimezone(service.BANGKOK).hour for f in one_day.frames],
            [1, 23],
        )
        self.assertEqual(one_day.available_dates, [yesterday, today])
        # Both requests share one cached provider call per camera.
        self.assertEqual(
            {call[0] for call in self.cache.calls},
            {"sindhu:cctv:v1:history:hatyai_city_climate:9"},
        )

    def _history_payload(self, days_ago, hours=(1, 13)):
        now = dt.datetime.now(service.BANGKOK)
        frames = [
            {
                "captured_at": (now - dt.timedelta(days=d, hours=-h)).isoformat(),
                "image_url": f"https://hatyaicityclimate.org/{d}-{h}.jpg",
            }
            for d in days_ago
            for h in hours
        ]
        frames.sort(key=lambda f: f["captured_at"])
        dates = sorted(
            {
                dt.datetime.fromisoformat(f["captured_at"])
                .astimezone(service.BANGKOK)
                .date()
                .isoformat()
                for f in frames
            }
        )
        return {"frames": frames, "available_dates": dates, "possibly_truncated": False}

    async def test_history_reports_the_provider_range_and_is_not_stale_when_current(
        self,
    ):
        self.provider.history.return_value = self._history_payload([3, 2, 1, 0], (0,))

        result = await self.viewer.history("hatyai_city_climate", "9")

        self.assertEqual(result.oldest_captured_at, result.frames[0].captured_at)
        self.assertEqual(result.latest_captured_at, result.frames[-1].captured_at)
        self.assertFalse(result.history_stale)

    async def test_history_that_stopped_updating_is_flagged_stale(self):
        self.provider.history.return_value = self._history_payload([6, 5, 4], (0,))

        result = await self.viewer.history("hatyai_city_climate", "9")

        self.assertTrue(result.history_stale)
        self.assertEqual(len(result.available_dates), 3)

    async def test_day_without_provider_photos_is_an_empty_success_with_the_range(
        self,
    ):
        payload = self._history_payload([3, 2], (0,))
        self.provider.history.return_value = payload
        today = dt.datetime.now(service.BANGKOK).date()

        result = await self.viewer.history("hatyai_city_climate", "9", today)

        self.assertEqual(result.frames, [])
        self.assertEqual(len(result.available_dates), 2)
        self.assertIsNotNone(result.oldest_captured_at)
        self.assertIsNotNone(result.latest_captured_at)

    async def test_hundred_realistic_frames_fit_the_history_cache_limit(self):
        import json

        payload = self._history_payload([4, 3, 2, 1, 0], tuple(range(20)))
        payload["frames"] = [
            {
                "captured_at": f["captured_at"],
                "image_url": "https://hatyaicityclimate.org/floodphoto/cam/2026/10/"
                f"hatyainai/20261020-{i:06d}.jpg",
                "thumbnail_url": "https://hatyaicityclimate.org/floodphoto/thumb/"
                f"2026/10/20/hatyainai-20261020-{i:06d}.jpg",
            }
            for i, f in enumerate(payload["frames"])
        ]
        self.assertEqual(len(payload["frames"]), 100)
        self.provider.history.return_value = payload
        seen = {}
        original_get = self.cache.get

        async def spy(key, loader, **kwargs):
            result = await original_get(key, loader, **kwargs)
            seen["value"], seen["kwargs"] = result.value, kwargs
            return result

        self.cache.get = spy

        result = await self.viewer.history("hatyai_city_climate", "9")

        self.assertEqual(len(result.frames), 100)
        limit = service.CctvCache.HISTORY_MAX_BYTES
        self.assertLess(len(json.dumps(seen["value"]).encode()), limit)
        self.assertEqual(seen["kwargs"]["max_bytes"], limit)
        self.assertEqual(seen["kwargs"]["fresh_seconds"], 600)

    def test_history_bangkok_boundary(self):
        now = dt.datetime(2026, 9, 2, 17, 1, tzinfo=dt.timezone.utc)
        for date in [dt.date(2026, 9, 3), dt.date(2026, 8, 1)]:
            service.validate_history_date(date, now)
        with self.assertRaises(service.ViewerError):
            service.validate_history_date(dt.date(2026, 9, 4), now)

    def test_health_counts(self):
        feeds = [
            PublicVisualFeed.model_validate(record()),
            PublicVisualFeed.model_validate(record(id="3", availability="stale")),
        ]
        health = service.build_source_health(feeds)["hatyai_city_climate"]
        self.assertEqual(health.online, 1)
        self.assertEqual(health.stale, 1)
        self.assertEqual(health.status.value, "degraded")
