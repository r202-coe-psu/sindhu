"""Runs the admin page's pure tambon helpers in node.

The helpers live between /* tambon-pure:start */ and /* tambon-pure:end */ in
sindhu/web/templates/zones/index.html. The block is extracted, evaluated by
node through stdin (no temp files), and the results are checked in Python.
Skipped when node is not installed.
"""

import json
import shutil
import subprocess
import unittest
from pathlib import Path

TEMPLATE = (
    Path(__file__).resolve().parents[2]
    / "sindhu"
    / "web"
    / "templates"
    / "zones"
    / "index.html"
)
START = "/* tambon-pure:start */"
END = "/* tambon-pure:end */"
NODE = shutil.which("node")


def pure_source():
    text = TEMPLATE.read_text(encoding="utf-8")
    start = text.index(START)
    end = text.index(END) + len(END)
    return text[start:end]


def merge(entries):
    body = (
        "const r = mergeTambonFiles(input.entries);"
        "process.stdout.write(JSON.stringify(r));"
    )
    return _run(body, {"entries": entries})


def derive(features, cfg):
    body = (
        "const r = deriveTambonFeatures(input.features, input.cfg);"
        "process.stdout.write(JSON.stringify(r));"
    )
    return _run(body, {"features": features, "cfg": cfg})


def _run(body, payload):
    script = (
        pure_source()
        + "\nconst input = "
        + json.dumps(payload, ensure_ascii=False)
        + ";\n"
        + body
        + "\n"
    )
    proc = subprocess.run(
        [NODE, "-"],
        input=script,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=20,
    )
    if proc.returncode != 0:
        raise AssertionError(f"node failed: {proc.stderr}")
    return json.loads(proc.stdout)


def square_polygon():
    return {
        "type": "Polygon",
        "coordinates": [[[100.0, 7.0], [100.1, 7.0], [100.1, 7.1], [100.0, 7.0]]],
    }


def entry(name, data):
    text = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)
    return {"name": name, "text": text}


@unittest.skipUnless(NODE, "node is not installed")
class AdminTambonJsTests(unittest.TestCase):
    def test_source_block_markers_exist_once(self):
        text = TEMPLATE.read_text(encoding="utf-8")
        self.assertEqual(text.count(START), 1)
        self.assertEqual(text.count(END), 1)

    # mergeTambonFiles

    def test_bare_polygon_becomes_one_feature(self):
        result = merge([entry("001_ควนรู.json", square_polygon())])

        self.assertEqual(result["errors"], [])
        self.assertEqual(len(result["features"]), 1)
        feature = result["features"][0]
        self.assertEqual(feature["type"], "Feature")
        self.assertEqual(feature["geometry"]["type"], "Polygon")
        self.assertEqual(feature["properties"]["__filename"], "001_ควนรู")

    def test_feature_becomes_one_feature_keeping_properties(self):
        feature = {
            "type": "Feature",
            "properties": {"name": "x"},
            "geometry": square_polygon(),
        }
        result = merge([entry("a.geojson", feature)])

        self.assertEqual(result["errors"], [])
        self.assertEqual(len(result["features"]), 1)
        self.assertEqual(result["features"][0]["properties"]["name"], "x")
        self.assertEqual(result["features"][0]["properties"]["__filename"], "a")

    def test_feature_collection_flattens_every_feature(self):
        fc = {
            "type": "FeatureCollection",
            "features": [
                {"type": "Feature", "properties": {"tc": "1"}, "geometry": square_polygon()},
                {"type": "Feature", "properties": {"tc": "2"}, "geometry": square_polygon()},
            ],
        }
        result = merge([entry("b.json", fc)])

        self.assertEqual(result["errors"], [])
        self.assertEqual([f["properties"]["tc"] for f in result["features"]], ["1", "2"])
        self.assertEqual({f["properties"]["__filename"] for f in result["features"]}, {"b"})

    def test_bad_json_is_reported_per_file_and_other_files_still_merge(self):
        result = merge(
            [
                entry("bad.json", "{not json"),
                entry("good.json", square_polygon()),
            ]
        )

        self.assertEqual(len(result["errors"]), 1)
        self.assertEqual(result["errors"][0]["file"], "bad.json")
        self.assertTrue(result["errors"][0]["message"].startswith("JSON"))
        self.assertEqual(len(result["features"]), 1)
        self.assertEqual(result["features"][0]["properties"]["__filename"], "good")

    def test_unsupported_type_is_reported_per_file(self):
        result = merge([entry("p.json", {"type": "Point", "coordinates": [1, 2]})])

        self.assertEqual(result["features"], [])
        self.assertEqual(result["errors"][0]["file"], "p.json")
        self.assertIn("Point", result["errors"][0]["message"])

    # deriveTambonFeatures

    def _features(self, name):
        return merge([entry(name, square_polygon())])["features"]

    def test_filename_source_with_separator_and_part_indices(self):
        features = self._features("001-ควนรู-หาดใหญ่.json")
        cfg = {
            "code": {"source": "filename", "sep": "-", "part": 1},
            "name": {"source": "filename", "sep": "-", "part": 2},
        }

        derived = derive(features, cfg)

        self.assertEqual(derived[0]["properties"]["__code"], "001")
        self.assertEqual(derived[0]["properties"]["__name"], "ควนรู-หาดใหญ่")

    def test_filename_code_can_take_a_later_part(self):
        features = self._features("ปี_901101_ควนลัง.json")
        cfg = {
            "code": {"source": "filename", "sep": "_", "part": 2},
            "name": {"source": "filename", "sep": "_", "part": 3},
        }

        derived = derive(features, cfg)

        self.assertEqual(derived[0]["properties"]["__code"], "901101")
        self.assertEqual(derived[0]["properties"]["__name"], "ควนลัง")

    def test_filename_name_joins_every_part_from_the_index(self):
        features = self._features("901101_A_B_C.json")
        cfg = {
            "code": {"source": "filename", "sep": "_", "part": 1},
            "name": {"source": "filename", "sep": "_", "part": 2},
        }

        derived = derive(features, cfg)

        self.assertEqual(derived[0]["properties"]["__code"], "901101")
        self.assertEqual(derived[0]["properties"]["__name"], "A_B_C")

    def test_filename_part_zero_or_missing_falls_back_to_first(self):
        features = self._features("901101_X.json")
        cfg = {
            "code": {"source": "filename", "sep": "_", "part": 0},
            "name": {"source": "filename", "sep": "_", "part": 9},
        }

        derived = derive(features, cfg)

        self.assertEqual(derived[0]["properties"]["__code"], "901101")
        self.assertEqual(derived[0]["properties"]["__name"], "")

    def test_property_source_reads_the_named_key_as_string(self):
        features = [
            {
                "type": "Feature",
                "geometry": square_polygon(),
                "properties": {"tc": 90110101, "tn": "ควนรู", "__filename": "x"},
            },
            {
                "type": "Feature",
                "geometry": square_polygon(),
                "properties": {"__filename": "x"},
            },
        ]
        cfg = {
            "code": {"source": "property", "key": "tc"},
            "name": {"source": "property", "key": "tn"},
        }

        derived = derive(features, cfg)

        self.assertEqual(derived[0]["properties"]["__code"], "90110101")
        self.assertEqual(derived[0]["properties"]["__name"], "ควนรู")
        self.assertEqual(derived[1]["properties"]["__code"], "")
        self.assertEqual(derived[1]["properties"]["__name"], "")

    def test_property_source_ignores_the_filename(self):
        features = self._features("901101_X.json")
        cfg = {
            "code": {"source": "property", "key": "missing"},
            "name": {"source": "property", "key": "missing"},
        }

        derived = derive(features, cfg)

        self.assertEqual(derived[0]["properties"]["__code"], "")


if __name__ == "__main__":
    unittest.main()
