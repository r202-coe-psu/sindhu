import datetime
import unittest
from unittest.mock import patch

from starlette.exceptions import HTTPException
from starlette.responses import Response

from sindhu.api.routers.v1 import visual_feeds as visual_feeds_router
from sindhu.schemas.visual_feeds import Availability, MediaType, PublicVisualFeed


def _feed() -> PublicVisualFeed:
    return PublicVisualFeed(
        source="hatyai_city_climate",
        upstream_id="camera-1",
        slug="camera-1",
        title_th="Camera 1",
        media_type=MediaType.CCTV,
        availability=Availability.ONLINE,
        fetched_at=datetime.datetime(2026, 8, 27, 3, tzinfo=datetime.timezone.utc),
        attribution={
            "provider": "Hatyai",
            "source_url": "https://hatyaicityclimate.org",
        },
    )


class VisualFeedRouterTests(unittest.IsolatedAsyncioTestCase):
    async def test_list_endpoint_returns_required_envelope(self) -> None:
        feed = _feed()

        async def fake_list(**kwargs):
            self.assertIs(kwargs["media_type"], MediaType.CCTV)
            return [feed], {}

        with patch.object(
            visual_feeds_router.services.visual_feeds,
            "list_visual_feeds",
            fake_list,
        ):
            response = await visual_feeds_router.list_visual_feeds(
                response=Response(),
                media_type=MediaType.CCTV,
                coverage_group=None,
                availability=None,
                has_coordinates=None,
            )

        self.assertEqual(response.count, 1)
        self.assertEqual(response.visual_feeds, [feed])
        self.assertEqual(response.generated_at.tzinfo, datetime.timezone.utc)
        self.assertEqual(response.source_health, {})

    async def test_detail_endpoint_returns_404_when_missing(self) -> None:
        async def fake_get(source, upstream_id):
            self.assertEqual(source, "provider")
            self.assertEqual(upstream_id, "missing")
            return None

        with patch.object(
            visual_feeds_router.services.visual_feeds,
            "get_visual_feed",
            fake_get,
        ):
            with self.assertRaises(HTTPException) as error:
                await visual_feeds_router.get_visual_feed(
                    "provider", "missing", Response()
                )

        self.assertEqual(error.exception.status_code, 404)
        self.assertEqual(error.exception.detail, "Visual feed not found")
