import importlib.util
import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "seed_zones_songkhla", ROOT / "scripts" / "seed_zones_songkhla.py"
)
seed = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(seed)


def zone(code, *upstream):
    return {"code": code, "upstream_codes": list(upstream)}


class UpstreamProblemsTests(unittest.TestCase):
    def test_a_chain_of_zones_is_accepted(self):
        zones = [zone("a"), zone("b", "a"), zone("c", "a", "b")]
        self.assertEqual(seed.upstream_problems(zones), [])

    def test_a_zone_upstream_of_itself_is_refused(self):
        self.assertEqual(len(seed.upstream_problems([zone("a", "a")])), 1)

    def test_a_cycle_is_refused(self):
        problems = seed.upstream_problems([zone("a", "b"), zone("b", "a")])
        self.assertTrue(problems)
        self.assertTrue(all("วงวน" in p for p in problems))

    def test_an_upstream_code_missing_from_the_file_is_refused(self):
        self.assertEqual(len(seed.upstream_problems([zone("a", "ghost")])), 1)


class SeedFileTests(unittest.TestCase):
    def setUp(self):
        self.zones = json.loads(seed.ZONES_PATH.read_text(encoding="utf-8"))

    def test_seed_file_loads_with_valid_upstream_links(self):
        self.assertEqual(seed.load_flood_zones(), self.zones)

    def test_every_zone_is_a_flood_polygon_with_a_unique_code(self):
        codes = [z["code"] for z in self.zones]
        self.assertEqual(len(codes), len(set(codes)))
        for z in self.zones:
            with self.subTest(code=z["code"]):
                self.assertEqual(z["zone_kind"], "flood")
                self.assertEqual(z["boundary"]["type"], "Polygon")
                self.assertGreaterEqual(len(z["boundary"]["coordinates"][0]), 4)
                self.assertEqual(len(z["station_codes"]), len(set(z["station_codes"])))


if __name__ == "__main__":
    unittest.main()
