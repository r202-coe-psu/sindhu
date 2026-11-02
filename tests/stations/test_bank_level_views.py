import re
import sys
import types
import unittest
from pathlib import Path

BRYTHON_ROOT = (
    Path(__file__).resolve().parents[2] / "sindhu" / "web" / "static" / "brython"
)


class _BrowserStub(dict):
    def __getattr__(self, name):
        return _BrowserStub()

    def __call__(self, *args, **kwargs):
        return _BrowserStub()

    def __bool__(self):
        return False


def _load_views():
    if str(BRYTHON_ROOT) not in sys.path:
        sys.path.insert(0, str(BRYTHON_ROOT))

    browser = types.ModuleType("browser")
    for name in ("aio", "ajax", "alert", "document", "html", "timer", "window"):
        setattr(browser, name, _BrowserStub())
    sys.modules.setdefault("browser", browser)

    javascript = types.ModuleType("javascript")
    javascript.JSON = _BrowserStub()
    javascript.NULL = None
    sys.modules.setdefault("javascript", javascript)

    from maps.base import BaseMap
    from monitors.water import WaterMonitor

    return BaseMap, WaterMonitor


BaseMap, WaterMonitor = _load_views()


def _station(source="rid", bank_level=12.0, **metrics):
    return {
        "id": "abc",
        "source": source,
        "bank_level": bank_level,
        "metadata": {"water_level_warning": 11.25, "water_level_critical": 77.77},
        "metrics": [{"metric_type": k, "value": v} for k, v in metrics.items()],
    }


def _section(station):
    view = BaseMap.__new__(BaseMap)
    view.map = _BrowserStub()  # Map.__del__ removes it when the view is collected
    return view.build_waterlevel_section(station)


def _chips(station):
    monitor = WaterMonitor.__new__(WaterMonitor)
    return monitor.build_metric_chips(station, station["metrics"])


class WaterCardTests(unittest.TestCase):
    def test_shows_gap_and_status_but_no_raw_level(self):
        html = _chips(
            _station(waterlevel=111.6, waterlevel_msl=11.6, diff_wl_bank=-98.76)
        )
        self.assertIn("ใกล้ระดับตลิ่ง · ต่ำกว่าตลิ่ง 0.40 ม.", html)
        for raw in ("111.6", "11.6", "98.76", "รทก"):
            self.assertNotIn(raw, html)

    def test_station_without_bank_level_is_neutral(self):
        html = _chips(_station(bank_level=None, waterlevel=11.6, diff_wl_bank=2.0))
        self.assertIn("ไม่มีข้อมูลระดับตลิ่ง", html)
        self.assertNotIn("ล้นตลิ่ง", html)
        self.assertNotIn("11.6", html)

    def test_other_metrics_still_show(self):
        html = _chips(_station(waterlevel=11.6, rain=4.5))
        self.assertIn("4.50 มม.", html)


class RiskBadgeTests(unittest.TestCase):
    def _risk(self, station):
        monitor = WaterMonitor.__new__(WaterMonitor)
        return monitor.calculate_risk(station)[0]

    def _with_thresholds(self, **metrics):
        station = _station(**metrics)
        station["metadata"] = {
            "water_level_warning": 11.25,
            "water_level_critical": 13.0,
        }
        return station

    def test_dead_sensor_is_unknown_not_safe(self):
        for reading in (-9.99, -999.0):
            self.assertEqual(self._risk(self._with_thresholds(waterlevel=reading)), -1)

    def test_dead_sensor_is_not_rescued_by_a_diff_derived_from_it(self):
        station = _station(waterlevel=-9.99, diff_wl_bank=-22.99)
        station["metadata"] = {}
        self.assertEqual(self._risk(station), -1)

    def test_implausible_level_is_unknown_not_evacuation(self):
        self.assertEqual(self._risk(self._with_thresholds(waterlevel=200.0)), -1)

    def test_huge_etl_diff_is_unknown_not_safe(self):
        station = _station(waterlevel=11.6, diff_wl_bank=-999.0)
        station["metadata"] = {}
        self.assertEqual(self._risk(station), -1)

    def test_no_bank_level_is_unknown_even_above_every_threshold(self):
        station = self._with_thresholds(waterlevel=14.0, diff_wl_bank=2.0)
        station["bank_level"] = None
        self.assertEqual(self._risk(station), -1)

    def test_real_readings_keep_their_risk(self):
        for reading, risk in ((10.0, 0), (11.5, 1), (13.2, 2), (14.0, 3)):
            self.assertEqual(
                self._risk(self._with_thresholds(waterlevel=reading)), risk
            )


class TooltipSectionTests(unittest.TestCase):
    def test_shows_gap_relative_to_the_bank_only(self):
        html = _section(_station(waterlevel=11.6, diff_wl_bank=-98.76))
        self.assertIn("ใกล้ระดับตลิ่ง · ต่ำกว่าตลิ่ง 0.40 ม.", html)
        self.assertIn("0.40", html)
        # warning sits 0.75 m under the bank, shown as a gap and not as MSL
        self.assertIn("-0.75 ม.", html)
        for raw in ("11.60", "12.00", "11.25", "77.77", "98.76"):
            self.assertNotIn(raw, html)

    def test_overflow_draws_the_water_above_the_bank(self):
        html = _section(_station(waterlevel=12.5))
        self.assertIn("ล้นตลิ่ง · สูงกว่าตลิ่ง 0.50 ม.", html)
        water_y = float(re.search(r'<rect x="0" y="([\d.]+)"[^>]*fill="url', html)[1])
        self.assertLess(water_y, BaseMap.SECTION_BANK_Y)

    def test_warning_above_the_bank_is_not_drawn(self):
        station = _station(waterlevel=11.6)
        station["metadata"]["water_level_warning"] = 13.0
        self.assertNotIn("เฝ้าระวัง", _section(station))

    def test_unknown_states_draw_no_water_line(self):
        for station, message in (
            (_station(bank_level=None, waterlevel=11.6), "ไม่มีข้อมูลระดับตลิ่ง"),
            (_station(waterlevel=-9.99), "ไม่มีข้อมูลระดับน้ำ"),
            (_station(source="dwr", waterlevel=3.0), "ไม่มีข้อมูลระดับน้ำ"),
        ):
            html = _section(station)
            self.assertIn(message, html)
            self.assertNotIn("<svg", html)


if __name__ == "__main__":
    unittest.main()
