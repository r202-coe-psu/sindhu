import importlib.util
import unittest
from pathlib import Path

AREA_PATH = (
    Path(__file__).resolve().parents[2]
    / "sindhu"
    / "web"
    / "static"
    / "brython"
    / "monitors"
    / "area.py"
)

# monitors/__init__.py imports the browser module, so load area.py by path.
_spec = importlib.util.spec_from_file_location("area_under_test", AREA_PATH)
area = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(area)


def zone(zone_id, name_th, tambons=None, stations=None):
    return {
        "id": zone_id,
        "name_th": name_th,
        "tambons": tambons or [],
        "stations": stations or [],
    }


def tb(code, name_th, amphoe_th=None):
    return {"code": code, "name_th": name_th, "amphoe_th": amphoe_th}


class BuildAreaOptionsTests(unittest.TestCase):
    def test_order_is_all_then_zones_then_tambons(self):
        zones = [
            zone("z1", "Zone A", [tb("1", "ควนรู", "หาดใหญ่")]),
            zone("z2", "Zone B", [tb("2", "คอหงส์", "หาดใหญ่")]),
        ]

        options = area.build_area_options(zones)

        self.assertEqual(options[0]["value"], area.ALL_AREAS)
        self.assertEqual(options[0]["group"], None)
        self.assertEqual(
            [o["value"] for o in options],
            ["", "zone:z1", "zone:z2", "tambon:1", "tambon:2"],
        )
        self.assertEqual([o["group"] for o in options[1:3]], ["Zone", "Zone"])
        self.assertEqual([o["group"] for o in options[3:]], ["ตำบล", "ตำบล"])

    def test_tambon_shared_by_two_zones_is_listed_once(self):
        zones = [
            zone("z1", "Zone A", [tb("1", "ควนรู", "หาดใหญ่")]),
            zone("z2", "Zone B", [tb("1", "ควนรู", "หาดใหญ่")]),
        ]

        tambon_values = [
            o["value"]
            for o in area.build_area_options(zones)
            if o["value"].startswith("tambon:")
        ]
        self.assertEqual(tambon_values, ["tambon:1"])

    def test_amphoe_is_in_the_label(self):
        options = area.build_area_options(
            [zone("z1", "Zone A", [tb("1", "ควนรู", "หาดใหญ่")])]
        )
        tambon_option = [o for o in options if o["value"] == "tambon:1"][0]

        self.assertEqual(tambon_option["label"], "ต.ควนรู (อ.หาดใหญ่)")

    def test_duplicate_names_get_the_code_in_the_label(self):
        zones = [
            zone("z1", "Zone A", [tb("100", "ท่าช้าง"), tb("200", "ท่าช้าง")]),
        ]

        labels = {
            o["value"]: o["label"]
            for o in area.build_area_options(zones)
            if o["value"].startswith("tambon:")
        }

        self.assertEqual(labels, {"tambon:100": "ต.ท่าช้าง (100)", "tambon:200": "ต.ท่าช้าง (200)"})

    def test_unique_name_without_amphoe_has_no_code_suffix(self):
        options = area.build_area_options([zone("z1", "Zone A", [tb("100", "ท่าช้าง")])])
        tambon_option = [o for o in options if o["value"] == "tambon:100"][0]
        self.assertEqual(tambon_option["label"], "ต.ท่าช้าง")

    def test_zone_without_id_is_skipped(self):
        options = area.build_area_options([{"name_th": "No id"}])
        self.assertEqual([o["value"] for o in options], [area.ALL_AREAS])

    def test_legacy_string_tambons_are_listed(self):
        options = area.build_area_options([zone("z1", "Zone A", ["ควนรู"])])
        values = [o["value"] for o in options]
        self.assertIn("tambon:ควนรู", values)
        labels = {o["value"]: o["label"] for o in options}
        self.assertEqual(labels["tambon:ควนรู"], "ต.ควนรู")


class ZoneIdsForValueTests(unittest.TestCase):
    def setUp(self):
        self.zones = [
            zone("z1", "Zone A", [tb("1", "A1")]),
            zone("z2", "Zone B", [tb("1", "A1"), tb("2", "B2")]),
            zone("z3", "Zone C", ["legacy"]),
        ]

    def test_zone_value_returns_that_zone(self):
        self.assertEqual(area.zone_ids_for_value(self.zones, "zone:z2"), ["z2"])

    def test_unknown_zone_value_returns_empty(self):
        self.assertEqual(area.zone_ids_for_value(self.zones, "zone:nope"), [])

    def test_tambon_value_in_one_zone(self):
        self.assertEqual(area.zone_ids_for_value(self.zones, "tambon:2"), ["z2"])

    def test_multi_zone_tambon_returns_every_zone(self):
        self.assertEqual(
            area.zone_ids_for_value(self.zones, "tambon:1"), ["z1", "z2"]
        )

    def test_legacy_string_tambon_resolves_to_its_zone(self):
        self.assertEqual(area.zone_ids_for_value(self.zones, "tambon:legacy"), ["z3"])

    def test_all_areas_and_empty_value_return_empty(self):
        self.assertEqual(area.zone_ids_for_value(self.zones, ""), [])
        self.assertEqual(area.zone_ids_for_value(self.zones, None), [])

    def test_zones_for_tambon_accepts_int_code(self):
        found = area.zones_for_tambon(self.zones, 2)
        self.assertEqual([z["id"] for z in found], ["z2"])


class MergeStationCodesTests(unittest.TestCase):
    def test_codes_are_deduplicated_in_first_seen_order(self):
        zones = [
            zone("z1", "A", stations=[{"code": "S2"}, {"code": "S1"}]),
            zone("z2", "B", stations=[{"code": "S1"}, {"code": "S3"}, {"code": "S2"}]),
        ]

        self.assertEqual(area.merge_station_codes(zones), ["S2", "S1", "S3"])

    def test_missing_or_empty_codes_are_skipped(self):
        zones = [
            zone("z1", "A", stations=[{"code": ""}, {"name": "no code"}, None, {"code": 7}]),
        ]
        self.assertEqual(area.merge_station_codes(zones), ["7"])

    def test_no_zones_gives_empty_list(self):
        self.assertEqual(area.merge_station_codes([]), [])
        self.assertEqual(area.merge_station_codes(None), [])


class LocationMessageTests(unittest.TestCase):
    def test_in_zone_with_tambon(self):
        message = area.location_message(
            "in_zone",
            zone=zone("z1", "โซน A"),
            tambon=tb("1", "ควนรู", "หาดใหญ่"),
        )
        self.assertEqual(message, "คุณอยู่ใน โซน A (ต.ควนรู)")

    def test_in_zone_without_tambon(self):
        message = area.location_message("in_zone", zone=zone("z1", "โซน A"), tambon=None)
        self.assertEqual(message, "คุณอยู่ใน โซน A")

    def test_in_zone_falls_back_to_name_when_no_name_th(self):
        message = area.location_message("in_zone", zone={"id": "z1", "name": "Zone A"})
        self.assertEqual(message, "คุณอยู่ใน Zone A")

    def test_outside(self):
        message = area.location_message("outside")
        self.assertIn("นอกพื้นที่ Zone", message)
        self.assertIn("เลือกพื้นที่จากรายการแทนได้", message)

    def test_denied(self):
        message = area.location_message("denied")
        self.assertIn("อนุญาตการเข้าถึงตำแหน่ง", message)

    def test_error_with_message_attribute(self):
        class Err:
            message = "timeout"

        message = area.location_message("error", error=Err())
        self.assertIn("(timeout)", message)
        self.assertIn("เลือกพื้นที่จากรายการแทนได้", message)

    def test_error_without_detail_has_no_suffix(self):
        message = area.location_message("error")
        self.assertTrue(message.startswith("ไม่สามารถระบุตำแหน่งได้ —"))
        self.assertNotIn("(", message)

    def test_error_falls_back_to_str(self):
        message = area.location_message("error", error=ValueError("boom"))
        self.assertIn("(boom)", message)


if __name__ == "__main__":
    unittest.main()
