import datetime
import unittest

from pydantic import ValidationError

from sindhu.schemas.visual_feeds import (
    Availability,
    CoordinateProvenance,
    CoordinateStatus,
    MediaType,
    PublicVisualFeed,
    PublicVisualFeedList,
    VisualFeed,
    VisualFeedList,
)

ATTRIBUTION = {
    "provider": "Hatyai City Climate",
    "source_url": "https://hatyaicityclimate.org/flood/map/camera",
}
PROVENANCE = {
    "source": "hatyai_city_climate_coordinate_registry",
    "method": "manual survey cross-checked against official map",
    "effective_date": "2026-08-27",
    "registry_version": "2026-08-27.v1",
    "reference_url": "https://hatyaicityclimate.org/flood/map/camera",
}


def _feed(**overrides):
    values = {
        "source": "hatyai_city_climate",
        "upstream_id": "22",
        "slug": "road30m",
        "title_th": "ถนนราษฎร์ยินดี",
        "fetched_at": "2026-08-27T03:05:00Z",
        "attribution": ATTRIBUTION,
    }
    values.update(overrides)
    return PublicVisualFeed(**values)


class VisualFeedSchemaTests(unittest.TestCase):
    def test_visual_feed_normalizes_id_and_timestamps_to_utc(self) -> None:
        feed = VisualFeed(
            source="hatyai_city_climate",
            upstream_id=22,
            slug="road30m",
            title_th="ถนนราษฎร์ยินดี",
            media_type=MediaType.CCTV,
            coordinate_status=CoordinateStatus.VERIFIED,
            coordinates={"type": "Point", "coordinates": [100.47, 7.01]},
            coordinate_provenance={
                "source": "hatyai_city_climate_coordinate_registry",
                "method": "manual survey cross-checked against official map",
                "effective_date": "2026-08-27",
                "registry_version": "2026-08-27.v1",
                "reference_url": "https://hatyaicityclimate.org/flood/map/camera",
            },
            registry_version="2026-08-27.v1",
            image_url="https://hatyaicityclimate.org/camera.jpg",
            captured_at="2026-08-27T10:00:00+07:00",
            fetched_at="2026-08-27T03:05:00Z",
        )

        self.assertEqual(feed.upstream_id, "22")
        self.assertEqual(
            feed.captured_at,
            datetime.datetime(2026, 8, 27, 3, 0, tzinfo=datetime.timezone.utc),
        )
        self.assertEqual(feed.fetched_at.tzinfo, datetime.timezone.utc)
        self.assertIsNotNone(feed.coordinates)
        self.assertEqual(feed.coordinates.coordinates, [100.47, 7.01])
        self.assertIsInstance(feed.coordinate_provenance, CoordinateProvenance)

    def test_verified_coordinates_require_auditable_provenance(self) -> None:
        base = {
            "source": "source",
            "upstream_id": "camera-1",
            "slug": "camera-1",
            "title_th": "Camera 1",
            "media_type": MediaType.CCTV,
            "coordinate_status": CoordinateStatus.VERIFIED,
            "coordinates": {"type": "Point", "coordinates": [100.47, 7.01]},
            "registry_version": "registry-v1",
        }

        with self.assertRaises(ValidationError):
            VisualFeed(**base)

        with self.assertRaises(ValidationError):
            VisualFeed(
                **base,
                coordinate_provenance={
                    "source": "survey",
                    "method": "manual survey",
                    "effective_date": "2026-08-27",
                    "registry_version": "registry-v1",
                },
            )

        with self.assertRaises(ValidationError):
            VisualFeed(
                **base,
                coordinate_provenance={
                    "source": "survey",
                    "method": "manual survey",
                    "effective_date": "2026-08-27",
                    "registry_version": "registry-v1",
                    "reference_url": "not-a-url",
                },
            )

        with self.assertRaises(ValidationError):
            VisualFeed(
                **base,
                coordinate_provenance={
                    "source": "survey",
                    "method": "manual survey",
                    "effective_date": "2026-08-27",
                    "registry_version": "registry-v2",
                    "reference_url": "https://example.org/coordinate-evidence",
                },
            )

    def test_timestamps_reject_naive_values_and_normalize_aware_values(self) -> None:
        with self.assertRaises(ValidationError):
            VisualFeed(
                source="source",
                upstream_id="camera-1",
                slug="camera-1",
                title_th="Camera 1",
                media_type=MediaType.CCTV,
                captured_at="2026-08-27T10:00:00",
            )

        with self.assertRaises(ValidationError):
            VisualFeedList(
                visual_feeds=[],
                count=0,
                generated_at="2026-08-27T10:00:00",
            )

        feed = VisualFeed(
            source="source",
            upstream_id="camera-1",
            slug="camera-1",
            title_th="Camera 1",
            media_type=MediaType.CCTV,
            captured_at="2026-08-27T10:00:00+07:00",
        )
        self.assertEqual(
            feed.captured_at,
            datetime.datetime(2026, 8, 27, 3, 0, tzinfo=datetime.timezone.utc),
        )

    def test_visual_feed_rejects_invalid_coordinates_and_non_http_urls(self) -> None:
        with self.assertRaises(ValidationError):
            VisualFeed(
                source="source",
                upstream_id="camera-1",
                slug="camera-1",
                title_th="Camera 1",
                media_type=MediaType.CCTV,
                coordinates={"type": "Point", "coordinates": [181, 7]},
            )

        with self.assertRaises(ValidationError):
            VisualFeed(
                source="source",
                upstream_id="camera-1",
                slug="camera-1",
                title_th="Camera 1",
                media_type=MediaType.CCTV,
                image_url="javascript:alert(1)",
            )

    def test_visual_feed_defaults_unknown_availability_and_nullable_coordinates(
        self,
    ) -> None:
        feed = VisualFeed(
            source="source",
            upstream_id="camera-1",
            slug="radar-1",
            title_th="Radar",
            media_type=MediaType.RADAR,
            coordinate_status=CoordinateStatus.NOT_APPLICABLE,
        )

        self.assertIsNone(feed.coordinates)
        self.assertIs(feed.availability, Availability.UNKNOWN)
        self.assertEqual(feed.raw_payload, {})


class PublicVisualFeedSchemaTests(unittest.TestCase):
    def test_feed_normalizes_timestamps_to_utc(self) -> None:
        feed = _feed(
            coordinate_status=CoordinateStatus.VERIFIED,
            coordinates={"type": "Point", "coordinates": [100.47, 7.01]},
            coordinate_provenance=PROVENANCE,
            registry_version="2026-08-27.v1",
            image_url="https://hatyaicityclimate.org/camera.jpg",
            captured_at="2026-08-27T10:00:00+07:00",
        )

        self.assertEqual(
            feed.captured_at,
            datetime.datetime(2026, 8, 27, 3, 0, tzinfo=datetime.timezone.utc),
        )
        self.assertEqual(feed.fetched_at.tzinfo, datetime.timezone.utc)
        self.assertEqual(feed.coordinates.coordinates, [100.47, 7.01])
        self.assertIsInstance(feed.coordinate_provenance, CoordinateProvenance)

    def test_verified_coordinates_require_auditable_provenance(self) -> None:
        base = {
            "coordinate_status": CoordinateStatus.VERIFIED,
            "coordinates": {"type": "Point", "coordinates": [100.47, 7.01]},
            "registry_version": "2026-08-27.v1",
        }

        with self.assertRaises(ValidationError):
            _feed(**base)

        for provenance in (
            {k: v for k, v in PROVENANCE.items() if k != "reference_url"},
            {**PROVENANCE, "reference_url": "not-a-url"},
            {**PROVENANCE, "registry_version": "2026-08-27.v2"},
        ):
            with self.subTest(provenance=provenance):
                with self.assertRaises(ValidationError):
                    _feed(**base, coordinate_provenance=provenance)

    def test_unverified_coordinates_are_never_published(self) -> None:
        with self.assertRaises(ValidationError):
            _feed(coordinates={"type": "Point", "coordinates": [100.47, 7.01]})

    def test_fetched_at_and_list_time_reject_naive_values(self) -> None:
        with self.assertRaises(ValidationError):
            _feed(fetched_at="2026-08-27T10:00:00")

        with self.assertRaises(ValidationError):
            PublicVisualFeedList(
                visual_feeds=[],
                count=0,
                generated_at="2026-08-27T10:00:00",
            )

    def test_unparseable_capture_time_is_dropped_not_fatal(self) -> None:
        self.assertIsNone(_feed(captured_at="2026-08-27T10:00:00").captured_at)

    def test_feed_rejects_invalid_coordinates_and_non_http_urls(self) -> None:
        with self.assertRaises(ValidationError):
            _feed(coordinates={"type": "Point", "coordinates": [181, 7]})

        with self.assertRaises(ValidationError):
            _feed(image_url="javascript:alert(1)")

    def test_feed_defaults_unknown_availability_and_no_coordinates(self) -> None:
        feed = _feed()

        self.assertIsNone(feed.coordinates)
        self.assertIs(feed.availability, Availability.UNKNOWN)
        self.assertEqual(feed.media_type, "cctv")
