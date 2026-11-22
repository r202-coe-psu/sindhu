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
        for path, build in (
            (build_flow_corridors.OUTPUT, build_flow_corridors.build),
            (build_flow_corridors.CONTEXT_OUTPUT, build_flow_corridors.build_context),
        ):
            with self.subTest(path=path.name):
                self.assertEqual(
                    path.read_text(encoding="utf-8"),
                    build_flow_corridors.render(build(source)),
                    "rerun scripts/build_flow_corridors.py",
                )

    def test_context_holds_every_source_line_that_is_not_a_corridor(self):
        source = json.loads(build_flow_corridors.SOURCE.read_text(encoding="utf-8"))
        corridors = json.loads(build_flow_corridors.OUTPUT.read_text(encoding="utf-8"))
        context = json.loads(
            build_flow_corridors.CONTEXT_OUTPUT.read_text(encoding="utf-8")
        )
        self.assertEqual(
            len(context["features"]) + len(corridors["features"]),
            len(source["features"]),
        )

    def test_simplify_keeps_the_ends_and_the_bends(self):
        line = [[0, 0], [1, 0.00001], [2, 0], [2, 1], [2, 2]]
        self.assertEqual(
            build_flow_corridors.simplify(line, 0.001), [[0, 0], [2, 0], [2, 2]]
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
