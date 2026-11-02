import sys
import unittest
from pathlib import Path

BRYTHON_ROOT = (
    Path(__file__).resolve().parents[2] / "sindhu" / "web" / "static" / "brython"
)
if str(BRYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(BRYTHON_ROOT))

from stations import bank_status  # noqa: E402


class CompareToBankTests(unittest.TestCase):
    def assert_status(self, water, bank, status, diff):
        result = bank_status.compare_to_bank(water, bank)
        self.assertEqual(result["status"], status)
        self.assertEqual(result["diff"], diff)

    def test_more_than_one_metre_under_the_bank_is_below(self):
        self.assert_status(10.0, 12.5, bank_status.STATUS_BELOW, -2.5)
        self.assert_status(10.99, 12.0, bank_status.STATUS_BELOW, -1.01)

    def test_within_one_metre_under_the_bank_is_near(self):
        self.assert_status(11.0, 12.0, bank_status.STATUS_NEAR, -1.0)
        self.assert_status(11.6, 12.0, bank_status.STATUS_NEAR, -0.4)
        self.assert_status(12.0, 12.0, bank_status.STATUS_NEAR, 0.0)

    def test_any_height_over_the_bank_is_overflow(self):
        self.assert_status(12.01, 12.0, bank_status.STATUS_OVERFLOW, 0.01)
        self.assert_status(14.0, 12.0, bank_status.STATUS_OVERFLOW, 2.0)

    def test_status_agrees_with_the_rounded_number_shown(self):
        # 10.7 - 11.7 is not exactly -1.0 in floating point
        self.assert_status(10.7, 11.7, bank_status.STATUS_NEAR, -1.0)
        result = bank_status.compare_to_bank(12.001, 12.0)
        self.assertEqual(result["status"], bank_status.STATUS_NEAR)
        self.assertEqual(result["detail"], "เสมอระดับตลิ่ง")

    def test_wording(self):
        below = bank_status.compare_to_bank(10.0, 12.5)
        self.assertEqual(below["summary"], "ต่ำกว่าตลิ่ง 2.50 ม.")
        near = bank_status.compare_to_bank(11.6, 12.0)
        self.assertEqual(near["summary"], "ใกล้ระดับตลิ่ง · ต่ำกว่าตลิ่ง 0.40 ม.")
        over = bank_status.compare_to_bank(12.3, 12.0)
        self.assertEqual(over["summary"], "ล้นตลิ่ง · สูงกว่าตลิ่ง 0.30 ม.")

    def test_negative_msl_levels_are_real_readings(self):
        self.assert_status(-0.5, 1.0, bank_status.STATUS_BELOW, -1.5)
        self.assert_status(-0.5, -0.8, bank_status.STATUS_OVERFLOW, 0.3)

    def test_missing_bank_is_neutral_never_a_risk(self):
        for bank in (None, "", "n/a", float("nan"), float("inf"), True):
            result = bank_status.compare_to_bank(100.0, bank)
            self.assertEqual(result["status"], bank_status.STATUS_UNKNOWN)
            self.assertIsNone(result["diff"])
            self.assertEqual(result["detail"], "ไม่มีข้อมูลระดับตลิ่ง")

    def test_missing_or_dead_sensor_is_neutral_not_safe(self):
        for water in (None, "", "-", float("nan"), -9.99, -999.0):
            result = bank_status.compare_to_bank(water, 12.0)
            self.assertEqual(result["status"], bank_status.STATUS_UNKNOWN)
            self.assertIsNone(result["diff"])
            self.assertEqual(result["detail"], "ไม่มีข้อมูลระดับน้ำ")

    def test_implausible_gap_is_neutral(self):
        for water, bank in ((200.0, 12.0), (2.0, 120.0)):
            result = bank_status.compare_to_bank(water, bank)
            self.assertEqual(result["status"], bank_status.STATUS_UNKNOWN)
            self.assertEqual(result["detail"], "ข้อมูลระดับน้ำผิดปกติ")

    def test_numeric_strings_are_accepted(self):
        self.assert_status("11.6", "12.0", bank_status.STATUS_NEAR, -0.4)


class UnreliableReadingTests(unittest.TestCase):
    def test_dead_sensor_constants_are_unreliable(self):
        for water in (-9.99, -999.0):
            self.assertTrue(bank_status.has_unreliable_reading(water, None))

    def test_level_far_from_its_thresholds_is_unreliable(self):
        self.assertTrue(bank_status.has_unreliable_reading(200.0, None, (11.25, 13.0)))

    def test_huge_etl_diff_is_unreliable(self):
        self.assertTrue(bank_status.has_unreliable_reading(11.6, -999.0))

    def test_normal_readings_are_reliable(self):
        for water, diff, references in (
            (11.6, -0.4, (11.25, 13.0)),
            (-0.5, None, (1.0,)),
            (250.0, None, (240.0,)),
            (None, None, (11.25,)),
            (11.6, None, (None, "-")),
        ):
            self.assertFalse(
                bank_status.has_unreliable_reading(water, diff, references)
            )


class CompareStationTests(unittest.TestCase):
    def station(self, source, metrics, bank_level=12.0):
        return {
            "source": source,
            "bank_level": bank_level,
            "metrics": [{"metric_type": k, "value": v} for k, v in metrics.items()],
        }

    def test_msl_sources_use_the_waterlevel_metric(self):
        for source in ("thaiwater", "rid"):
            station = self.station(source, {"waterlevel": 11.6})
            self.assertEqual(bank_status.compare_station(station)["diff"], -0.4)

    def test_dwr_waterlevel_is_not_msl_so_it_is_not_compared(self):
        # 3 m above gauge zero against a 12 m MSL bank would read as "far below"
        for source in ("dwr", "dwr_telemetry"):
            station = self.station(source, {"waterlevel": 3.0})
            result = bank_status.compare_station(station)
            self.assertEqual(result["status"], bank_status.STATUS_UNKNOWN)
            self.assertEqual(result["detail"], "ไม่มีข้อมูลระดับน้ำ")

    def test_explicit_msl_metric_works_for_any_source(self):
        station = self.station("dwr", {"waterlevel": 3.0, "waterlevel_msl": 11.6})
        self.assertEqual(bank_status.compare_station(station)["diff"], -0.4)

    def test_etl_diff_is_not_a_substitute_for_bank_level(self):
        station = self.station(
            "rid", {"waterlevel": 11.6, "diff_wl_bank": 2.0}, bank_level=None
        )
        result = bank_status.compare_station(station)
        self.assertEqual(result["status"], bank_status.STATUS_UNKNOWN)
        self.assertEqual(result["detail"], "ไม่มีข้อมูลระดับตลิ่ง")

    def test_tolerates_malformed_stations(self):
        for station in ({}, {"metrics": None}, {"metrics": [None, {}]}):
            result = bank_status.compare_station(station)
            self.assertEqual(result["status"], bank_status.STATUS_UNKNOWN)


if __name__ == "__main__":
    unittest.main()
