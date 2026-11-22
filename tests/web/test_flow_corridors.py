import importlib.util
import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "build_flow_corridors", ROOT / "scripts" / "build_flow_corridors.py"
)
build_flow_corridors = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(build_flow_corridors)


class FlowCorridorDataTests(unittest.TestCase):
    def test_committed_file_matches_the_build_script(self):
        source = json.loads(build_flow_corridors.SOURCE.read_text(encoding="utf-8"))
        expected = build_flow_corridors.render(build_flow_corridors.build(source))
        self.assertEqual(
            build_flow_corridors.OUTPUT.read_text(encoding="utf-8"),
            expected,
            "rerun scripts/build_flow_corridors.py",
        )

    def test_every_corridor_has_drawable_lines(self):
        collection = json.loads(build_flow_corridors.OUTPUT.read_text(encoding="utf-8"))
        corridors = {}
        for feature in collection["features"]:
            self.assertEqual(feature["geometry"]["type"], "LineString")
            self.assertGreaterEqual(len(feature["geometry"]["coordinates"]), 2)
            corridors.setdefault(feature["properties"]["corridor"], 0)
            corridors[feature["properties"]["corridor"]] += 1
        self.assertEqual(set(corridors), set(build_flow_corridors.CORRIDOR_LINES))


if __name__ == "__main__":
    unittest.main()
