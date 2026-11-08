import sys
import unittest
from pathlib import Path

BRYTHON_ROOT = (
    Path(__file__).resolve().parents[2] / "sindhu" / "web" / "static" / "brython"
)
if str(BRYTHON_ROOT) not in sys.path:
    sys.path.append(str(BRYTHON_ROOT))

from stations import bank_status  # noqa: E402


def _station(
    source="rid",
    bank_level=None,
    metadata=None,
    **metrics,
):
    return {
        "source": source,
        "bank_level": bank_level,
        "metadata": metadata or {},
        "metrics": [{"metric_type": k, "value": v} for k, v in metrics.items()],
    }


def _admin_station(water, bank, source="rid"):
    return _station(source, bank_level=bank, waterlevel=water)


class StationStatusTests(unittest.TestCase):
    def assert_status(self, water, bank, status, diff):
        result = bank_status.compare_station(_admin_station(water, bank))
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
        self.assert_status(10.7, 11.7, bank_status.STATUS_NEAR, -1.0)
        result = bank_status.compare_station(_admin_station(12.001, 12.0))
        self.assertEqual(result["status"], bank_status.STATUS_NEAR)
        self.assertEqual(result["detail"], "เสมอระดับตลิ่ง")

    def test_wording(self):
        for water, bank, summary in (
            (10.0, 12.5, "ต่ำกว่าตลิ่ง 2.50 ม."),
            (11.6, 12.0, "ใกล้ระดับตลิ่ง · ต่ำกว่าตลิ่ง 0.40 ม."),
            (12.3, 12.0, "ล้นตลิ่ง · สูงกว่าตลิ่ง 0.30 ม."),
        ):
            with self.subTest(water=water):
                result = bank_status.compare_station(_admin_station(water, bank))
                self.assertEqual(result["summary"], summary)

    def test_negative_msl_levels_are_real_readings(self):
        self.assert_status(-0.5, 1.0, bank_status.STATUS_BELOW, -1.5)
        self.assert_status(-0.5, -0.8, bank_status.STATUS_OVERFLOW, 0.3)

    def test_missing_or_bad_bank_is_neutral_never_a_risk(self):
        for bank in (None, "", "  ", "n/a", float("nan"), float("inf"), True, 0):
            with self.subTest(bank=bank):
                result = bank_status.compare_station(_admin_station(11.0, bank))
                self.assertEqual(result["status"], bank_status.STATUS_UNKNOWN)
                self.assertIsNone(result["diff"])
                self.assertEqual(result["detail"], "ไม่มีข้อมูลระดับตลิ่ง")

    def test_missing_dead_or_zero_sensor_is_neutral_not_safe(self):
        for water in (None, "", "-", float("nan"), -9.99, -999.0, 0, 0.0):
            with self.subTest(water=water):
                result = bank_status.compare_station(_admin_station(water, 12.0))
                self.assertEqual(result["status"], bank_status.STATUS_UNKNOWN)
                self.assertIsNone(result["diff"])
                self.assertEqual(result["detail"], "ไม่มีข้อมูลระดับน้ำ")

    def test_zero_water_with_an_etl_bank_is_not_safe(self):
        station = _station(
            "thaiwater", metadata={"water_level_critical": 12.0}, waterlevel=0
        )
        self.assertEqual(
            bank_status.compare_station(station)["risk"], bank_status.RISK_UNKNOWN
        )

    def test_numeric_strings_are_accepted(self):
        self.assert_status("11.6", "12.0", bank_status.STATUS_NEAR, -0.4)

    def test_implausible_gap_blames_neither_reading(self):
        for water, bank in ((200.0, 12.0), (2.0, 120.0)):
            with self.subTest(water=water, bank=bank):
                result = bank_status.compare_station(_admin_station(water, bank))
                self.assertEqual(result["status"], bank_status.STATUS_UNKNOWN)
                self.assertEqual(
                    result["detail"], "ระดับน้ำกับระดับตลิ่งห่างกันผิดปกติ"
                )


class NearBandTests(unittest.TestCase):
    def assert_status(self, diff, near_band, status):
        self.assertEqual(bank_status.status_for_gap(diff, near_band)["status"], status)

    def test_three_levels_and_no_evacuation(self):
        for diff, risk in (
            (-2.5, bank_status.RISK_NORMAL),
            (-1.01, bank_status.RISK_NORMAL),
            (-1.0, bank_status.RISK_WATCH),
            (0.0, bank_status.RISK_WATCH),
            (0.01, bank_status.RISK_CRITICAL),
            (3.0, bank_status.RISK_CRITICAL),
        ):
            with self.subTest(diff=diff):
                self.assertEqual(bank_status.status_for_gap(diff)["risk"], risk)
        self.assertFalse(hasattr(bank_status, "RISK_EVACUATE"))

    def test_band_reaches_down_to_the_warning_level(self):
        self.assert_status(-0.8, 0.8, bank_status.STATUS_NEAR)
        self.assert_status(-0.81, 0.8, bank_status.STATUS_BELOW)
        self.assert_status(-1.7, 1.75, bank_status.STATUS_NEAR)

    def test_chip_colour_follows_the_risk(self):
        watch = bank_status.status_for_gap(-0.4)
        overflow = bank_status.status_for_gap(1.0)
        self.assertNotEqual(watch["color"], overflow["color"])
        self.assertEqual(bank_status.status_for_gap(-0.5)["color"], watch["color"])


class GapPriorityTests(unittest.TestCase):
    def gap(self, station):
        return bank_status.station_gap(station)

    def test_admin_bank_comes_first(self):
        station = _station(
            bank_level=12.0,
            metadata={"water_level_critical": 11.0},
            waterlevel=11.6,
            diff_wl_bank=0.6,
        )
        self.assertEqual(self.gap(station), (-0.4, bank_status.GAP_FROM_ADMIN))

    def test_etl_diff_comes_before_the_etl_bank(self):
        station = _station(
            metadata={"water_level_critical": 12.0}, waterlevel=11.6, diff_wl_bank=-0.5
        )
        self.assertEqual(self.gap(station), (-0.5, bank_status.GAP_FROM_ETL_DIFF))

    def test_etl_bank_is_used_when_there_is_no_diff(self):
        for source in ("rid", "thaiwater"):
            with self.subTest(source=source):
                station = _station(
                    source, metadata={"water_level_critical": 12.0}, waterlevel=11.6
                )
                self.assertEqual(
                    self.gap(station), (-0.4, bank_status.GAP_FROM_ETL_BANK)
                )

    def test_admin_bank_without_an_msl_reading_falls_through(self):
        station = _station("dwr", bank_level=12.0, waterlevel=3.0, diff_wl_bank=-0.7)
        self.assertEqual(self.gap(station), (-0.7, bank_status.GAP_FROM_ETL_DIFF))

    def test_nothing_usable_is_unknown(self):
        result = bank_status.compare_station(_station(waterlevel=11.6))
        self.assertEqual(result["status"], bank_status.STATUS_UNKNOWN)
        self.assertEqual(result["detail"], "ไม่มีข้อมูลระดับตลิ่ง")
        self.assertIsNone(result["gap_source"])

    def test_bank_without_water_reports_missing_water(self):
        station = _station(metadata={"water_level_critical": 12.0})
        self.assertEqual(
            bank_status.compare_station(station)["detail"], "ไม่มีข้อมูลระดับน้ำ"
        )

    def test_implausible_gap_falls_to_the_next_source(self):
        station = _station(
            bank_level=120.0,
            metadata={"water_level_critical": 12.0},
            waterlevel=11.6,
        )
        self.assertEqual(self.gap(station), (-0.4, bank_status.GAP_FROM_ETL_BANK))

    def test_every_source_implausible_is_flagged(self):
        station = _station(metadata={"water_level_critical": 12.0}, waterlevel=200.0)
        result = bank_status.compare_station(station)
        self.assertEqual(result["status"], bank_status.STATUS_UNKNOWN)
        self.assertEqual(result["detail"], "ระดับน้ำกับระดับตลิ่งห่างกันผิดปกติ")


class DwrTests(unittest.TestCase):
    METADATA = {"zflowMsl": 8.0, "lbMsl": 12.5, "rbMsl": 12.0}

    def test_stage_plus_gauge_zero_is_the_msl_level(self):
        station = _station("dwr", metadata=self.METADATA, waterlevel=3.6)
        self.assertEqual(bank_status.station_water_level(station), 11.6)

    def test_lower_bank_is_the_etl_bank(self):
        station = _station("dwr_telemetry", metadata=self.METADATA)
        self.assertEqual(bank_status.etl_bank_level(station), 12.0)

    def test_dwr_is_compared_with_its_lower_bank(self):
        station = _station("dwr", metadata=self.METADATA, waterlevel=3.6)
        result = bank_status.compare_station(station)
        self.assertEqual(result["diff"], -0.4)
        self.assertEqual(result["gap_source"], bank_status.GAP_FROM_ETL_BANK)

    def test_admin_bank_works_for_dwr_with_a_gauge_zero(self):
        station = _station(
            "dwr", bank_level=12.2, metadata=self.METADATA, waterlevel=3.6
        )
        self.assertEqual(
            bank_status.station_gap(station), (-0.6, bank_status.GAP_FROM_ADMIN)
        )

    def test_dwr_without_gauge_zero_has_no_msl_level(self):
        station = _station("dwr", metadata={"lbMsl": 12.0}, waterlevel=3.6)
        self.assertIsNone(bank_status.station_water_level(station))
        self.assertEqual(
            bank_status.compare_station(station)["detail"], "ไม่มีข้อมูลระดับน้ำ"
        )


class NoDataFilterTests(unittest.TestCase):
    def test_zero_and_dead_sensor_banks_are_missing(self):
        for value in (0, 0.0, -9.99, -999.0, "-9.99"):
            with self.subTest(value=value):
                self.assertIsNone(bank_status.admin_bank_level(value))
                station = _station(metadata={"water_level_critical": value})
                self.assertIsNone(bank_status.etl_bank_level(station))

    def test_stored_bank_outside_the_accepted_range_is_missing(self):
        for value in (-20.01, 3000.01):
            with self.subTest(value=value):
                self.assertIsNone(bank_status.admin_bank_level(value))

    def test_stored_bad_admin_bank_is_treated_like_a_missing_one(self):
        bad = _station(
            bank_level=-9.99, metadata={"water_level_critical": 12.0}, waterlevel=11.6
        )
        missing = _station(
            bank_level=None, metadata={"water_level_critical": 12.0}, waterlevel=11.6
        )
        self.assertEqual(
            bank_status.compare_station(bad), bank_status.compare_station(missing)
        )

    def test_rid_diff_built_on_a_zero_bank_is_ignored(self):
        on_zero = _station(
            metadata={"water_level_critical": 0}, waterlevel=11.6, diff_wl_bank=11.6
        )
        equal_to_level = _station(waterlevel=11.6, diff_wl_bank=11.6)
        for station in (on_zero, equal_to_level):
            self.assertIsNone(bank_status.etl_bank_gap(station))

    def test_diff_from_a_dead_sensor_is_ignored(self):
        station = _station(waterlevel=-9.99, diff_wl_bank=-22.99)
        self.assertIsNone(bank_status.etl_bank_gap(station))

    def test_reader_range_matches_the_api_range(self):
        from sindhu.schemas import stations as station_schemas

        self.assertEqual(bank_status.BANK_LEVEL_MIN_M, station_schemas.BANK_LEVEL_MIN_M)
        self.assertEqual(bank_status.BANK_LEVEL_MAX_M, station_schemas.BANK_LEVEL_MAX_M)

    def test_public_views_hide_raw_levels_and_the_etl_diff(self):
        for metric in bank_status.RAW_WATER_LEVEL_METRICS + ("diff_wl_bank",):
            self.assertIn(metric, bank_status.PUBLIC_HIDDEN_METRICS)

    def test_tolerates_malformed_stations(self):
        for station in ({}, {"metrics": None}, {"metrics": [None, {}]}):
            result = bank_status.compare_station(station)
            self.assertEqual(result["status"], bank_status.STATUS_UNKNOWN)


class WarningBandTests(unittest.TestCase):
    def band(self, source, warning, critical=12.0):
        return bank_status.near_bank_band(
            _station(
                source,
                metadata={
                    "water_level_warning": warning,
                    "water_level_critical": critical,
                },
            )
        )

    def test_band_is_the_gap_between_warning_and_critical(self):
        self.assertEqual(self.band("rid", 11.2), 0.8)

    def test_unusable_warning_falls_back_to_one_metre(self):
        for warning in (None, 12.0, 13.0, 0, -9.99, 9.99, 3.0):
            with self.subTest(warning=warning):
                self.assertEqual(
                    self.band("rid", warning), bank_status.DEFAULT_NEAR_BAND_M
                )

    def test_band_up_to_the_ceiling_is_kept(self):
        self.assertEqual(self.band("rid", 10.0), bank_status.MAX_NEAR_BAND_M)

    def test_thaiwater_warning_made_up_by_the_etl_is_ignored(self):
        for warning, critical in ((9.6, 12.0), (7.1, 8.88), (7.11, 8.88)):
            with self.subTest(warning=warning, critical=critical):
                self.assertEqual(
                    self.band("thaiwater", warning, critical),
                    bank_status.DEFAULT_NEAR_BAND_M,
                )
        self.assertEqual(self.band("thaiwater", 11.5), 0.5)

    def test_station_status_uses_its_own_band(self):
        station = _station(
            metadata={"water_level_warning": 11.7, "water_level_critical": 12.0},
            waterlevel=11.6,
        )
        result = bank_status.compare_station(station)
        self.assertEqual(result["status"], bank_status.STATUS_BELOW)
        self.assertEqual(result["near_band"], 0.3)


if __name__ == "__main__":
    unittest.main()
