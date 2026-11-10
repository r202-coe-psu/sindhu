import unittest
from types import SimpleNamespace

from sindhu.services import zones as zone_service


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
    )


class ZoneRoleTests(unittest.TestCase):
    def test_zone_kind_reference_is_reference(self):
        zone = fake_zone("r", square(0, 0), zone_kind="reference")

        self.assertTrue(zone_service.is_reference_zone(zone))

    def test_metadata_role_reference_boundary_is_reference(self):
        zone = fake_zone(
            "r", square(0, 0), zone_kind=None, metadata={"role": "reference_boundary"}
        )

        self.assertTrue(zone_service.is_reference_zone(zone))

    def test_zone_kind_none_without_role_is_flood(self):
        zone = fake_zone("f", square(0, 0), zone_kind=None, metadata={})

        self.assertFalse(zone_service.is_reference_zone(zone))

    def test_missing_metadata_is_flood(self):
        zone = fake_zone("f", square(0, 0), zone_kind=None, metadata=None)


    def test_code_001_alone_is_not_reference(self):
        zone = fake_zone("f", square(0, 0), zone_kind=None, metadata=None, code="001")

        self.assertFalse(zone_service.is_reference_zone(zone))

    def test_other_role_is_flood(self):
        zone = fake_zone("f", square(0, 0), zone_kind="flood", metadata={"role": "x"})


    def test_reference_boundary_code_constant_is_gone(self):
        self.assertFalse(hasattr(zone_service, "REFERENCE_BOUNDARY_CODE"))
