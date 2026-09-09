import json
import unittest
from pathlib import Path
from unittest.mock import patch

from pydantic import ValidationError

from sindhu import models
from sindhu.schemas.zones import CreateUpdateZone
from sindhu.services import zones as zones_service


BOUNDARY_PATH = (
    Path(__file__).resolve().parents[2]
    / "sindhu"
    / "web"
    / "static"
    / "resources"
    / "hatyai_boundary.geojson"
)


class ReferenceBoundaryTests(unittest.TestCase):
    def test_hatyai_boundary_is_a_closed_polygon(self):
        boundary = json.loads(BOUNDARY_PATH.read_text(encoding="utf-8"))
        ring = boundary["coordinates"][0]

        self.assertEqual(boundary["type"], "Polygon")
        self.assertGreaterEqual(len(ring), 4)
        self.assertEqual(ring[0], ring[-1])
        self.assertTrue(
            all(
                len(point) == 2
                and all(isinstance(value, (int, float)) for value in point)
                for point in ring
            )
        )

    def test_zone_kind_defaults_to_flood_and_accepts_reference(self):
        base = {
            "name": "Hat Yai",
            "name_th": "หาดใหญ่",
            "code": "hatyai-boundary",
            "boundary": {
                "type": "Polygon",
                "coordinates": [
                    [[100.0, 7.0], [100.1, 7.0], [100.1, 7.1], [100.0, 7.0]]
                ],
            },
        }

        self.assertEqual(CreateUpdateZone(**base).zone_kind, "flood")
        self.assertEqual(
            CreateUpdateZone(**base, zone_kind="reference").zone_kind,
            "reference",
        )
        with self.assertRaises(ValidationError):
            CreateUpdateZone(**base, zone_kind="unknown")

    async def _capture_location_query(self):
        captured = {}

        async def fake_find_one(query):
            captured["query"] = query
            return None

        with patch.object(models.Zone, "find_one", new=fake_find_one):
            result = await zones_service.find_zone_by_location(100.0, 7.0)

        return result, captured["query"]

    def test_location_lookup_excludes_reference_zones(self):
        result, query = __import__("asyncio").run(self._capture_location_query())

        self.assertIsNone(result)
        self.assertIn("$or", query)
        self.assertIn({"zone_kind": "flood"}, query["$or"])
        self.assertIn({"zone_kind": {"$exists": False}}, query["$or"])


if __name__ == "__main__":
    unittest.main()
