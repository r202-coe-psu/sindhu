import datetime as dt
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx

from sindhu import models
from sindhu.schemas.visual_feeds import Availability, MediaType, PublicVisualFeed
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
            self.assertEqual(len(self.cache.calls), 2)
            self.assertEqual(
                self.cache.calls[0][0],
                f"sindhu:cctv:v1:latest:hatyai_city_climate:{service.HATYAI_REGISTRY_VERSION}:r{self.viewer._source_config_revision}",
            )

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
            f"sindhu:cctv:v1:history:hatyai_city_climate:9:{today}",
        )

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

    async def test_wrong_day_history_not_silently_substituted(self):
        today = dt.datetime.now(service.BANGKOK).date()
        wrong = dt.datetime.combine(
            today - dt.timedelta(days=1), dt.time(1), service.BANGKOK
        )
        self.provider.history.return_value = {
            "frames": [
                {
                    "captured_at": wrong.isoformat(),
                    "image_url": "https://hatyaicityclimate.org/old.jpg",
                }
            ]
        }
        with self.assertRaises(service.ViewerError):
            await self.viewer.history("hatyai_city_climate", "9", today)

    def test_history_bangkok_boundary(self):
        now = dt.datetime(2026, 9, 2, 17, 1, tzinfo=dt.timezone.utc)
        for date in [dt.date(2026, 9, 3), dt.date(2026, 8, 28)]:
            service.validate_history_date(date, now)
        for date in [dt.date(2026, 9, 4), dt.date(2026, 8, 27)]:
            with self.assertRaises(service.ViewerError):
                service.validate_history_date(date, now)

    def test_health_counts(self):
        feeds = [
            PublicVisualFeed.model_validate(record()),
            PublicVisualFeed.model_validate(record(id="3", availability="stale")),
        ]
        health = service.build_source_health(feeds)["hatyai_city_climate"]
        self.assertEqual(health.online, 1)
        self.assertEqual(health.stale, 1)
        self.assertEqual(health.status.value, "degraded")
