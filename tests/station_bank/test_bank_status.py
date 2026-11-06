import sys
import unittest
from pathlib import Path

BRYTHON_ROOT = (
    Path(__file__).resolve().parents[2] / "sindhu" / "web" / "static" / "brython"
)
if str(BRYTHON_ROOT) not in sys.path:
    sys.path.append(str(BRYTHON_ROOT))

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


class RiskTests(unittest.TestCase):
    def test_risk_bands_around_the_bank(self):
        for diff, risk in (
            (-2.5, bank_status.RISK_NORMAL),
            (-1.01, bank_status.RISK_NORMAL),
            (-1.0, bank_status.RISK_WATCH),
            (0.0, bank_status.RISK_WATCH),
            (0.01, bank_status.RISK_CRITICAL),
            (0.5, bank_status.RISK_CRITICAL),
            (0.51, bank_status.RISK_EVACUATE),
            (None, bank_status.RISK_UNKNOWN),
        ):
            with self.subTest(diff=diff):
                self.assertEqual(bank_status.risk_for_gap(diff), risk)

    def test_comparison_carries_the_same_risk_as_its_gap(self):
        for water in (9.0, 11.5, 12.3, 12.8):
            result = bank_status.compare_to_bank(water, 12.0)
            self.assertEqual(result["risk"], bank_status.risk_for_gap(result["diff"]))

    def test_unknown_comparison_has_unknown_risk(self):
        for water, bank in ((11.0, None), (-9.99, 12.0), (200.0, 12.0)):
            result = bank_status.compare_to_bank(water, bank)
            self.assertEqual(result["risk"], bank_status.RISK_UNKNOWN)

    def test_chip_colour_follows_the_risk(self):
        watch = bank_status.compare_to_bank(11.6, 12.0)
        evacuate = bank_status.compare_to_bank(13.0, 12.0)
        self.assertNotEqual(watch["color"], evacuate["color"])
        self.assertEqual(
            bank_status.compare_to_bank(11.5, 12.0)["color"], watch["color"]
        )


class CompareStationTests(unittest.TestCase):
    def station(self, source, metrics, bank_level=12.0, etl_critical=None):
        return {
            "source": source,
            "bank_level": bank_level,
            "metadata": {"water_level_critical": etl_critical},
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

    def test_etl_diff_metric_is_never_used(self):
        station = self.station(
            "rid", {"waterlevel": 11.6, "diff_wl_bank": 2.0}, bank_level=None
        )
        result = bank_status.compare_station(station)
        self.assertEqual(result["status"], bank_status.STATUS_UNKNOWN)
        self.assertEqual(result["detail"], "ไม่มีข้อมูลระดับตลิ่ง")

    def test_admin_bank_wins_over_the_etl_critical_level(self):
        station = self.station(
            "rid", {"waterlevel": 11.6}, bank_level=12.0, etl_critical=11.0
        )
        result = bank_status.compare_station(station)
        self.assertEqual(result["diff"], -0.4)
        self.assertEqual(result["bank_source"], bank_status.BANK_FROM_ADMIN)

    def test_msl_sources_fall_back_to_the_etl_critical_level(self):
        for source in ("rid", "thaiwater"):
            with self.subTest(source=source):
                station = self.station(
                    source, {"waterlevel": 11.6}, bank_level=None, etl_critical=12.0
                )
                result = bank_status.compare_station(station)
                self.assertEqual(result["diff"], -0.4)
                self.assertEqual(result["bank_source"], bank_status.BANK_FROM_ETL)

    def test_dwr_gets_no_etl_bank(self):
        station = self.station(
            "dwr", {"waterlevel_msl": 11.6}, bank_level=None, etl_critical=12.0
        )
        self.assertEqual(bank_status.station_bank_level(station), (None, None))

    def test_dead_sensor_constant_is_not_a_bank(self):
        station = self.station(
            "rid", {"waterlevel": 11.6}, bank_level=None, etl_critical=-9.99
        )
        self.assertEqual(bank_status.station_bank_level(station), (None, None))

    def test_tolerates_malformed_stations(self):
        for station in ({}, {"metrics": None}, {"metrics": [None, {}]}):
            result = bank_status.compare_station(station)
            self.assertEqual(result["status"], bank_status.STATUS_UNKNOWN)


if __name__ == "__main__":
    unittest.main()
