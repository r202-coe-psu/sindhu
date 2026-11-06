import unittest

from sindhu.schemas.tambons import TambonRef
from sindhu.schemas.zones import BaseZone
from sindhu.services import tambons as tambon_service


def square(x0, y0, size=2.0):
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


_DEFAULT = object()


def feature(code=None, name=None, geometry=_DEFAULT, amphoe=None):
    props = {}
    if code is not None:
        props["tc"] = code
    if name is not None:
        props["tn"] = name
    if amphoe is not None:
        props["ap"] = amphoe
    return {
        "type": "Feature",
        "properties": props,
        "geometry": square(0, 0) if geometry is _DEFAULT else geometry,
    }


def fc(*features):
    return {"type": "FeatureCollection", "features": list(features)}


def parse(*features):
    return tambon_service.parse_tambon_geojson(fc(*features), "tc", "tn", "ap")


def tambon(code, boundary, name=None, amphoe=None):
    return {
        "code": code,
        "name_th": name or f"T{code}",
        "amphoe_th": amphoe,
        "boundary": boundary,
    }


class ParseTambonGeojsonTests(unittest.TestCase):
    def test_polygon_and_multipolygon_are_both_kept(self):
        multi = {
            "type": "MultiPolygon",
            "coordinates": [square(0, 0)["coordinates"], square(5, 5)["coordinates"]],
        }
        result = parse(
            feature(code="1", name="A", geometry=square(0, 0)),
            feature(code="2", name="B", geometry=multi),
        )

        self.assertEqual([t["code"] for t in result["tambons"]], ["1", "2"])
        self.assertEqual(result["tambons"][0]["boundary"]["type"], "Polygon")
        self.assertEqual(result["tambons"][1]["boundary"]["type"], "MultiPolygon")
        self.assertEqual(result["skipped"], 0)
        self.assertEqual(result["warnings"], [])

    def test_missing_code_is_skipped_with_warning(self):
        result = parse(feature(code=None, name="A"))

        self.assertEqual(result["tambons"], [])
        self.assertEqual(result["skipped"], 1)
        self.assertEqual(len(result["warnings"]), 1)
        self.assertIn("รหัสตำบล", result["warnings"][0])

    def test_blank_code_counts_as_missing(self):
        result = parse(feature(code="   ", name="A"))

        self.assertEqual(result["tambons"], [])
        self.assertEqual(result["skipped"], 1)

    def test_missing_name_is_skipped_with_warning(self):
        result = parse(feature(code="1", name=None))

        self.assertEqual(result["tambons"], [])
        self.assertEqual(result["skipped"], 1)
        self.assertIn("ชื่อตำบล", result["warnings"][0])

    def test_duplicate_code_keeps_first_feature(self):
        result = parse(
            feature(code="1", name="First"),
            feature(code="1", name="Second"),
        )

        self.assertEqual(len(result["tambons"]), 1)
        self.assertEqual(result["tambons"][0]["name_th"], "First")
        self.assertEqual(result["skipped"], 1)
        self.assertIn("รหัสซ้ำ", result["warnings"][0])

    def test_bad_geometry_is_skipped(self):
        bad_geometries = [
            {"type": "Point", "coordinates": [100.0, 7.0]},
            {"type": "Polygon", "coordinates": []},
            None,
        ]
        for geometry in bad_geometries:
            with self.subTest(geometry=geometry):
                result = parse(feature(code="1", name="A", geometry=geometry))

                self.assertEqual(result["tambons"], [])
                self.assertEqual(result["skipped"], 1)
                self.assertIn("geometry", result["warnings"][0])

    def test_numeric_code_becomes_string(self):
        result = tambon_service.parse_tambon_geojson(
            fc({"type": "Feature", "properties": {"tc": 90010101, "tn": "A"}, "geometry": square(0, 0)}),
            "tc",
            "tn",
        )

        self.assertEqual(result["tambons"][0]["code"], "90010101")
        self.assertIsInstance(result["tambons"][0]["code"], str)

    def test_same_name_with_different_codes_both_stay(self):
        result = parse(
            feature(code="1", name="ควนรู", amphoe="A", geometry=square(0, 0)),
            feature(code="2", name="ควนรู", amphoe="B", geometry=square(5, 5)),
        )

        self.assertEqual([t["code"] for t in result["tambons"]], ["1", "2"])
        self.assertEqual([t["name_th"] for t in result["tambons"]], ["ควนรู", "ควนรู"])
        self.assertEqual(result["skipped"], 0)

    def test_amphoe_property_is_optional(self):
        result = parse(feature(code="1", name="A", amphoe="X"))
        self.assertEqual(result["tambons"][0]["amphoe_th"], "X")

        no_amphoe = tambon_service.parse_tambon_geojson(
            fc(feature(code="1", name="A", amphoe="X")), "tc", "tn"
        )
        self.assertIsNone(no_amphoe["tambons"][0]["amphoe_th"])

    def test_non_feature_collection_yields_no_tambons(self):
        result = tambon_service.parse_tambon_geojson(
            {"type": "Feature"}, "tc", "tn"
        )
        self.assertEqual(result["tambons"], [])
        self.assertEqual(len(result["warnings"]), 1)


class ClipToAreaTests(unittest.TestCase):
    def test_features_outside_the_area_are_dropped(self):
        inside = tambon("1", square(0.2, 0.2, 0.5))
        outside = tambon("2", square(10, 10))

        kept, dropped = tambon_service.clip_to_area(
            [inside, outside], square(0, 0, 2)
        )

        self.assertEqual([t["code"] for t in kept], ["1"])
        self.assertEqual(dropped, 1)

    def test_none_area_keeps_everything(self):
        items = [tambon("1", square(0, 0)), tambon("2", square(10, 10))]

        kept, dropped = tambon_service.clip_to_area(items, None)

        self.assertEqual(len(kept), 2)
        self.assertEqual(dropped, 0)


class AssignTambonsToZonesTests(unittest.TestCase):
    def test_tambon_inside_zone_is_assigned(self):
        result = tambon_service.assign_tambons_to_zones(
            [tambon("1", square(0.2, 0.2, 0.6), name="In", amphoe="X")],
            [{"id": "z1", "boundary": square(0, 0, 2)}],
        )

        self.assertEqual(
            result["z1"],
            [{"code": "1", "name_th": "In", "amphoe_th": "X"}],
        )

    def test_tambon_spanning_two_zones_goes_into_both(self):
        zones = [
            {"id": "z1", "boundary": square(0, 0, 2)},
            {"id": "z2", "boundary": square(1, 0, 2)},
        ]
        # x in [0.5, 1.5]: fully inside z1, half inside z2 (x in [1, 3]).
        result = tambon_service.assign_tambons_to_zones(
            [tambon("9", square(0.5, 0, 1))], zones
        )

        self.assertEqual([r["code"] for r in result["z1"]], ["9"])
        self.assertEqual([r["code"] for r in result["z2"]], ["9"])

    def test_tambon_only_touching_an_edge_is_ignored(self):
        # Shares only the x=2 edge with z1: zero overlap area.
        result = tambon_service.assign_tambons_to_zones(
            [tambon("1", square(2, 0, 2))],
            [{"id": "z1", "boundary": square(0, 0, 2)}],
        )
        self.assertEqual(result["z1"], [])

    def test_tambon_with_small_overlap_below_threshold_is_ignored(self):
        # Overlap is 0.02 wide x 2 tall = 0.04 of a 4.0 area = 1%.
        result = tambon_service.assign_tambons_to_zones(
            [tambon("1", square(1.98, 0, 2))],
            [{"id": "z1", "boundary": square(0, 0, 2)}],
        )
        self.assertEqual(result["z1"], [])

    def test_tambon_outside_every_zone_appears_nowhere(self):
        result = tambon_service.assign_tambons_to_zones(
            [tambon("1", square(50, 50))],
            [
                {"id": "z1", "boundary": square(0, 0, 2)},
                {"id": "z2", "boundary": square(1, 1, 2)},
            ],
        )

        for refs in result.values():
            self.assertEqual(refs, [])

    def test_every_zone_id_is_a_key_even_when_empty(self):
        result = tambon_service.assign_tambons_to_zones(
            [],
            [
                {"id": "z1", "boundary": square(0, 0, 2)},
                {"id": "z2", "boundary": square(5, 5, 2)},
            ],
        )
        self.assertEqual(set(result), {"z1", "z2"})
        self.assertEqual(result, {"z1": [], "z2": []})

    def test_refs_are_sorted_by_code(self):
        result = tambon_service.assign_tambons_to_zones(
            [tambon("20", square(0.1, 0.1, 0.3)), tambon("10", square(0.5, 0.5, 0.3))],
            [{"id": "z1", "boundary": square(0, 0, 2)}],
        )
        self.assertEqual([r["code"] for r in result["z1"]], ["10", "20"])


class DiffTambonsTests(unittest.TestCase):
    def test_added_and_removed_are_compared_by_code(self):
        current = [
            {"code": "1", "name_th": "A", "amphoe_th": None},
            {"code": "2", "name_th": "B", "amphoe_th": None},
        ]
        new = [
            {"code": "2", "name_th": "B", "amphoe_th": None},
            {"code": "3", "name_th": "C", "amphoe_th": "X"},
        ]

        added, removed = tambon_service.diff_tambons(current, new)

        self.assertEqual(added, [{"code": "3", "name_th": "C", "amphoe_th": "X"}])
        self.assertEqual(removed, [{"code": "1", "name_th": "A", "amphoe_th": None}])

    def test_legacy_string_current_matches_by_code(self):
        added, removed = tambon_service.diff_tambons(
            ["x"], [{"code": "x", "name_th": "x", "amphoe_th": None}]
        )
        self.assertEqual(added, [])
        self.assertEqual(removed, [])

    def test_legacy_string_current_is_removed_when_not_in_new(self):
        added, removed = tambon_service.diff_tambons(
            ["old"], [{"code": "new", "name_th": "New", "amphoe_th": None}]
        )
        self.assertEqual([r["code"] for r in added], ["new"])
        self.assertEqual(removed, [{"code": "old", "name_th": "old", "amphoe_th": None}])

    def test_accepts_tambon_ref_models(self):
        added, removed = tambon_service.diff_tambons(
            [TambonRef(code="1", name_th="A")],
            [{"code": "1", "name_th": "A", "amphoe_th": None}],
        )
        self.assertEqual((added, removed), ([], []))


class ZoneLegacyTambonValidatorTests(unittest.TestCase):
    def test_legacy_string_tambon_becomes_ref(self):
        zone = BaseZone(
            name="Zone",
            code="z",
            boundary={"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]},
            tambons=["x"],
        )
        self.assertEqual(zone.tambons, [TambonRef(code="x", name_th="x")])

    def test_missing_tambons_default_to_empty(self):
        zone = BaseZone(
            name="Zone",
            code="z",
            boundary={"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]},
        )
        self.assertEqual(zone.tambons, [])


if __name__ == "__main__":
    unittest.main()
