import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from shapely.geometry import shape
from shapely.ops import unary_union

from sindhu import models, schemas
from sindhu.services import tambons as tambon_service


def square(x0, y0, size=1.0):
    return {
        "type": "Polygon",
        "coordinates": [
            [
                [x0, y0],
                [x0 + size, y0],
                [x0 + size, y0 + size],
                [x0, y0 + size],
                [x0, y0],
            ]
        ],
    }


def fake_zone(name, boundary, zone_kind=None, metadata=None, code=None):
    return SimpleNamespace(
        id=name,
        name=name,
        name_th=name,
        code=code or name,
        boundary=SimpleNamespace(model_dump=lambda: boundary),
        zone_kind=zone_kind,
        metadata=metadata,
        tambons=[],
    )


class _FakeQuery:
    def __init__(self, items):
        self._items = items

    async def to_list(self):
        return list(self._items)


class ZoneRoleTests(unittest.TestCase):
    def test_zone_kind_reference_is_reference(self):
        zone = fake_zone("r", square(0, 0), zone_kind="reference")

        self.assertTrue(tambon_service.is_reference_zone(zone))
        self.assertFalse(tambon_service.is_flood_zone(zone))

    def test_metadata_role_reference_boundary_is_reference(self):
        zone = fake_zone(
            "r", square(0, 0), zone_kind=None, metadata={"role": "reference_boundary"}
        )

        self.assertTrue(tambon_service.is_reference_zone(zone))
        self.assertFalse(tambon_service.is_flood_zone(zone))

    def test_zone_kind_none_without_role_is_flood(self):
        zone = fake_zone("f", square(0, 0), zone_kind=None, metadata={})

        self.assertFalse(tambon_service.is_reference_zone(zone))
        self.assertTrue(tambon_service.is_flood_zone(zone))

    def test_missing_metadata_is_flood(self):
        zone = fake_zone("f", square(0, 0), zone_kind=None, metadata=None)

        self.assertTrue(tambon_service.is_flood_zone(zone))

    def test_code_001_alone_is_not_reference(self):
        zone = fake_zone("f", square(0, 0), zone_kind=None, metadata=None, code="001")

        self.assertFalse(tambon_service.is_reference_zone(zone))
        self.assertTrue(tambon_service.is_flood_zone(zone))

    def test_other_role_is_flood(self):
        zone = fake_zone("f", square(0, 0), zone_kind="flood", metadata={"role": "x"})

        self.assertTrue(tambon_service.is_flood_zone(zone))

    def test_reference_boundary_code_constant_is_gone(self):
        self.assertFalse(hasattr(tambon_service, "REFERENCE_BOUNDARY_CODE"))


class ImportClipAreaTests(unittest.IsolatedAsyncioTestCase):
    def _request(self):
        # One tambon that sits inside every zone used below, so the clip area
        # decides whether it is kept.
        feature = {
            "type": "Feature",
            "properties": {"tc": "1", "tn": "T"},
            "geometry": square(0.2, 0.2, 0.1),
        }
        return schemas.tambons.ImportTambonRequest(
            feature_collection={"type": "FeatureCollection", "features": [feature]},
            code_property="tc",
            name_property="tn",
            amphoe_property=None,
            dry_run=True,
        )

    async def _clip_area_for(self, zones):
        clip_spy = Mock(wraps=tambon_service.clip_to_area)
        with patch.object(
            models.Zone, "find", Mock(return_value=_FakeQuery(zones))
        ), patch.object(tambon_service, "clip_to_area", clip_spy):
            result = await tambon_service.import_tambons(self._request(), dry_run=True)
        self.assertTrue(result["dry_run"])
        clip_spy.assert_called_once()
        return shape(clip_spy.call_args.args[1])

    async def test_two_reference_zones_clip_to_their_union(self):
        # Two disjoint reference boundaries, and a flood zone that lies outside
        # both of them. The flood zone must not widen the clip area.
        zones = [
            fake_zone("ref-a", square(0, 0, 1), zone_kind="reference"),
            fake_zone("ref-b", square(3, 0, 1), zone_kind="reference"),
            fake_zone("flood", square(10, 10, 1), zone_kind="flood"),
        ]

        area = await self._clip_area_for(zones)

        expected = unary_union([shape(square(0, 0, 1)), shape(square(3, 0, 1))])
        self.assertTrue(area.equals(expected), area.wkt)
        self.assertAlmostEqual(area.area, 2.0)
        self.assertFalse(area.intersects(shape(square(10, 10, 1))))

    async def test_no_reference_zone_clips_to_union_of_flood_zones(self):
        zones = [
            fake_zone("flood-a", square(0, 0, 1)),
            fake_zone("flood-b", square(3, 0, 1), metadata={"role": "flood"}),
        ]

        area = await self._clip_area_for(zones)

        expected = unary_union([shape(square(0, 0, 1)), shape(square(3, 0, 1))])
        self.assertTrue(area.equals(expected), area.wkt)
        self.assertAlmostEqual(area.area, 2.0)

    async def test_reference_zone_hides_flood_zones_from_clip(self):
        # One reference zone exists, so the flood zone's area is not used.
        zones = [
            fake_zone("ref", square(0, 0, 1), metadata={"role": "reference_boundary"}),
            fake_zone("flood", square(3, 0, 1)),
        ]

        area = await self._clip_area_for(zones)

        self.assertTrue(area.equals(shape(square(0, 0, 1))), area.wkt)


if __name__ == "__main__":
    unittest.main()
