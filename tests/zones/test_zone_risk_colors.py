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


def _load_brython_classes():
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

    from maps.map import Map
    from monitors.water import WaterMonitor
    from stations import metric_infos

    return Map, WaterMonitor, metric_infos


Map, WaterMonitor, metric_infos = _load_brython_classes()


class _Layer:
    def __init__(self):
        self.styles = []

    def setStyle(self, style):
        self.styles.append(style)


class _RiskMap:
    def __init__(self):
        self.updates = []

    def set_zone_risk(self, zone_id, level):
        self.updates.append((zone_id, level["risk"]))


class _Bounds:
    def __init__(self, names=None):
        self.names = list(names or [])

    def isValid(self):
        return bool(self.names)

    def extend(self, other):
        self.names.extend(other.names)
        return self


class _BoundedLayer:
    def __init__(self, name):
        self.bounds = _Bounds([name])

    def getBounds(self):
        return self.bounds


class _Leaflet:
    def __init__(self):
        self.bounds = None

    def latLngBounds(self, _coordinates):
        self.bounds = _Bounds()
        return self.bounds


class _ViewportMap:
    def __init__(self):
        self.invalidations = []
        self.fits = []

    def invalidateSize(self, options):
        self.invalidations.append(options)

    def fitBounds(self, bounds, options):
        self.fits.append((bounds, options))

    def remove(self):
        pass


def _station(code, source, water_level, warning=1.0, critical=2.0, evacuation=3.0):
    metrics = []
    if water_level is not None:
        metrics.append({"metric_type": "waterlevel", "value": water_level})
    return {
        "code": code,
        "source": source,
        "metadata": {
            "water_level_warning": warning,
            "water_level_critical": critical,
            "water_level_evacuation": evacuation,
        },
        "metrics": metrics,
    }


class ZoneRiskAggregationTests(unittest.TestCase):
    def make_monitor(self, stations, source="all"):
        monitor = WaterMonitor.__new__(WaterMonitor)
        monitor.latest_data = {"stations": stations}
        monitor.get_selected_source = lambda: source
        return monitor

    def test_zone_uses_worst_station_risk(self):
        monitor = self.make_monitor(
            [
                _station("normal", "rid", 0.5),
                _station("warning", "rid", 1.5),
                _station("critical", "rid", 2.5),
                _station("evacuation", "rid", 3.5),
            ]
        )
        zone = {
            "stations": [
                {"code": "normal"},
                {"code": "warning"},
                {"code": "critical"},
                {"code": "evacuation"},
            ]
        }

        self.assertEqual(monitor.zone_risk_level(zone)["risk"], 3)

    def test_station_without_fresh_metrics_does_not_recolour_zone(self):
        monitor = self.make_monitor([_station("stale", "rid", None)])

        level = monitor.zone_risk_level({"stations": [{"code": "stale"}]})

        self.assertEqual(level["risk"], -1)

    def test_source_change_recomputes_zone_risk(self):
        monitor = self.make_monitor(
            [
                _station("shared", "rid", 1.5),
                _station("shared", "dwr", 3.5),
            ],
            source="rid",
        )
        monitor.zones = [{"id": "zone-1", "stations": [{"code": "shared"}]}]
        monitor.map = _RiskMap()

        monitor.update_zone_risks()
        monitor.get_selected_source = lambda: "dwr"
        monitor.update_zone_risks()

        self.assertEqual(monitor.map.updates, [("zone-1", 1), ("zone-1", 3)])

    def test_reference_boundary_is_not_sent_for_risk_update(self):
        monitor = self.make_monitor([_station("station", "rid", 3.5)])
        monitor.zones = [
            {
                "id": "reference",
                "zone_kind": "reference",
                "stations": [{"code": "station"}],
            },
            {"id": "flood", "stations": [{"code": "station"}]},
        ]
        monitor.map = _RiskMap()

        monitor.update_zone_risks()

        self.assertEqual(monitor.map.updates, [("flood", 3)])


class ZoneStyleTests(unittest.TestCase):
    def make_map(self, zone, risk):
        map_view = Map.__new__(Map)
        map_view.map = _BrowserStub()
        map_view.zone_shading_mode = "outline"
        map_view._selected_zone_id = None
        map_view.zone_layers_by_id = {
            "zone": {"zone": zone, "risk": risk, "layer": _Layer()}
        }
        return map_view

    def test_normal_and_no_data_follow_risk_colours(self):
        zone = {"metadata": {"fill": "#123456", "stroke": "#654321"}}

        expected = {0: ("#16a34a", "#22c55e"), -1: ("#6b7280", "#9ca3af")}
        for risk, (border, fill) in expected.items():
            with self.subTest(mode="outline", risk=risk):
                level = metric_infos.get_risk_level(risk)
                style = self.make_map(zone, level).zone_style("zone")
                self.assertEqual(style["color"], border)
                self.assertEqual(style["fillColor"], "transparent")
                self.assertEqual(style["fillOpacity"], 0.0)

            with self.subTest(mode="shaded", risk=risk):
                level = metric_infos.get_risk_level(risk)
                map_view = self.make_map(zone, level)
                map_view.zone_shading_mode = "shaded"
                style = map_view.zone_style("zone")
                self.assertEqual(style["color"], border)
                self.assertEqual(style["fillColor"], fill)
                self.assertGreater(style["fillOpacity"], 0.0)

    def test_alert_colours_match_warning_critical_and_evacuation(self):
        zone = {"metadata": {"fill": "#123456", "stroke": "#654321"}}
        expected_colours = {
            1: ("#f97316", "#ea580c"),
            2: ("#ef4444", "#dc2626"),
            3: ("#9333ea", "#7e22ce"),
        }

        for risk in (1, 2, 3):
            with self.subTest(mode="outline", risk=risk):
                level = metric_infos.get_risk_level(risk)
                self.assertEqual(
                    (level["color"], level["border"]), expected_colours[risk]
                )
                style = self.make_map(zone, level).zone_style("zone")
                self.assertEqual(style["color"], level["border"])
                self.assertEqual(style["fillColor"], "transparent")
                self.assertEqual(style["fillOpacity"], 0.0)

            with self.subTest(mode="shaded", risk=risk):
                level = metric_infos.get_risk_level(risk)
                map_view = self.make_map(zone, level)
                map_view.zone_shading_mode = "shaded"
                style = map_view.zone_style("zone")
                self.assertEqual(style["color"], level["border"])
                self.assertEqual(style["fillColor"], level["color"])
                self.assertGreater(style["fillOpacity"], 0.0)

    def test_reference_boundary_keeps_its_colour_during_alert(self):
        zone = {
            "zone_kind": "reference",
            "metadata": {"fill": "#111111", "stroke": "#222222"},
        }
        level = metric_infos.get_risk_level(3)

        style = self.make_map(zone, level).zone_style("zone")

        self.assertEqual(style["color"], "#222222")
        self.assertEqual(style["fillColor"], "transparent")

    def test_switching_shading_mode_restyles_existing_zone(self):
        zone = {"metadata": {"fill": "#123456", "stroke": "#654321"}}
        level = metric_infos.get_risk_level(2)
        map_view = self.make_map(zone, level)
        layer = map_view.zone_layers_by_id["zone"]["layer"]

        map_view.set_zone_shading_mode("shaded")

        self.assertEqual(layer.styles[-1]["fillColor"], level["color"])
        self.assertGreater(layer.styles[-1]["fillOpacity"], 0.0)

    def test_initial_viewport_includes_every_zone_and_reference_boundary(self):
        map_view = Map.__new__(Map)
        map_view.leaflet = _Leaflet()
        map_view.map = _ViewportMap()
        map_view.zone_layers_by_id = {
            f"zone-{index}": {"layer": _BoundedLayer(f"zone-{index}")}
            for index in range(1, 5)
        }
        map_view.reference_boundary_layer = _BoundedLayer("reference")

        map_view.fit_to_hatyai_bounds()

        self.assertEqual(
            map_view.map.fits[0][0].names,
            ["zone-1", "zone-2", "zone-3", "zone-4", "reference"],
        )
        self.assertEqual(map_view.map.fits[0][1], {"padding": [24, 24]})
        self.assertEqual(map_view.map.invalidations, [{"pan": False}])


if __name__ == "__main__":
    unittest.main()
