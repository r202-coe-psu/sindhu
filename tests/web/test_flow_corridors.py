import importlib.util
import json
import pathlib
import unittest
from collections import Counter

ROOT = pathlib.Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "build_flow_corridors", ROOT / "scripts" / "build_flow_corridors.py"
)
build_flow_corridors = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(build_flow_corridors)


def _committed():
    return json.loads(build_flow_corridors.OUTPUT.read_text(encoding="utf-8"))


class WaterwayDataTests(unittest.TestCase):
    def test_committed_file_matches_the_build_script(self):
        source = build_flow_corridors.load_source()
        self.assertEqual(
            build_flow_corridors.OUTPUT.read_text(encoding="utf-8"),
            build_flow_corridors.render(build_flow_corridors.build(source)),
            "rerun scripts/build_flow_corridors.py",
        )

    def test_every_source_line_is_drawable_and_has_a_class(self):
        source = build_flow_corridors.load_source()
        features = _committed()["features"]
        self.assertEqual(len(features), len(source["features"]))
        for feature in features:
            self.assertEqual(feature["geometry"]["type"], "LineString")
            self.assertGreaterEqual(len(feature["geometry"]["coordinates"]), 2)
            self.assertTrue(feature["properties"]["fclass"])

    def test_only_the_listed_lines_carry_a_system(self):
        counts = Counter(
            f["properties"].get("corridor") for f in _committed()["features"]
        )
        counts.pop(None)
        self.assertEqual(
            counts,
            {
                system: len(osm_ids)
                for system, osm_ids in build_flow_corridors.CORRIDOR_LINES.items()
            },
        )

    def test_simplify_keeps_the_ends_and_the_bends(self):
        line = [[0, 0], [1, 0.00001], [2, 0], [2, 1], [2, 2]]
        self.assertEqual(
            build_flow_corridors.simplify(line, 0.001), [[0, 0], [2, 0], [2, 2]]
        )


if __name__ == "__main__":
    unittest.main()
