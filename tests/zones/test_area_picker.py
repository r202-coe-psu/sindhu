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


class BuildAreaOptionsTests(unittest.TestCase):
    def test_order_is_all_then_zones_then_tambons(self):
        zones = [
            zone("z1", "Zone A", ["ควนรู"]),
            zone("z2", "Zone B", ["คอหงส์"]),
        ]

        values = [o["value"] for o in area.build_area_options(zones)]

        self.assertEqual(
            values, ["", "zone:z1", "zone:z2", "tambon:ควนรู", "tambon:คอหงส์"]
        )

    def test_tambon_shared_by_two_zones_is_listed_once(self):
        zones = [zone("z1", "A", ["ควนรู"]), zone("z2", "B", ["ควนรู"])]

        tambon_values = [
            o["value"]
            for o in area.build_area_options(zones)
            if o["value"].startswith("tambon:")
        ]

        self.assertEqual(tambon_values, ["tambon:ควนรู"])

    def test_tambon_label_and_group(self):
        options = area.build_area_options([zone("z1", "A", ["ควนรู"])])

        option = [o for o in options if o["value"] == "tambon:ควนรู"][0]
        self.assertEqual(option["label"], "ต.ควนรู")
        self.assertEqual(option["group"], "ตำบล")


class ZoneIdsForValueTests(unittest.TestCase):
    def setUp(self):
        self.zones = [
            zone("z1", "Zone A", ["A1"]),
            zone("z2", "Zone B", ["A1", "B2"]),
        ]

    def test_zone_value_returns_that_zone(self):
        self.assertEqual(area.zone_ids_for_value(self.zones, "zone:z2"), ["z2"])

    def test_unknown_zone_value_returns_empty(self):
        self.assertEqual(area.zone_ids_for_value(self.zones, "zone:nope"), [])

    def test_tambon_value_in_one_zone(self):
        self.assertEqual(area.zone_ids_for_value(self.zones, "tambon:B2"), ["z2"])

    def test_multi_zone_tambon_returns_every_zone(self):
        self.assertEqual(
            area.zone_ids_for_value(self.zones, "tambon:A1"), ["z1", "z2"]
        )

    def test_unknown_tambon_returns_empty(self):
        self.assertEqual(area.zone_ids_for_value(self.zones, "tambon:nope"), [])

    def test_all_areas_and_empty_value_return_empty(self):
        self.assertEqual(area.zone_ids_for_value(self.zones, ""), [])
        self.assertEqual(area.zone_ids_for_value(self.zones, None), [])


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
    def test_in_zone(self):
        message = area.location_message("in_zone", zone=zone("z1", "โซน A"))
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
