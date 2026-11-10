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
        sys.path.append(str(BRYTHON_ROOT))

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
        map_view._selected_zone_ids = []
        map_view.zone_layers_by_id = {
            "zone": {"zone": zone, "risk": risk, "layer": _Layer()}
        }
        return map_view

    # #67: the outline says which zone it is; the fill says how risky it is.

    def test_outline_keeps_the_zone_colour_at_every_risk(self):
        zone = {"code": "songkhla-zone-1"}
        for risk in (-1, 0, 1, 2, 3):
            with self.subTest(risk=risk):
                level = metric_infos.get_risk_level(risk)
                style = self.make_map(zone, level).zone_style("zone")
                self.assertEqual(style["color"], Map.ZONE_IDENTITIES[0]["color"])
                self.assertEqual(style["dashArray"], Map.ZONE_IDENTITIES[0]["dash"])

    def test_fill_follows_the_risk_colour(self):
        zone = {"code": "songkhla-zone-1"}
        for risk in (0, 1, 2, 3):
            with self.subTest(risk=risk):
                level = metric_infos.get_risk_level(risk)
                style = self.make_map(zone, level).zone_style("zone")
                self.assertEqual(style["fillColor"], level["color"])
                self.assertAlmostEqual(style["fillOpacity"], Map.ZONE_RISK_FILL_OPACITY)

    def test_zone_without_data_is_not_filled(self):
        level = metric_infos.get_risk_level(-1)
        style = self.make_map({"code": "songkhla-zone-1"}, level).zone_style("zone")
        self.assertEqual(style["fillColor"], "transparent")
        self.assertEqual(style["fillOpacity"], 0.0)

    def test_colour_set_on_the_zone_page_wins_over_the_preset(self):
        zone = {"metadata": {"fill": "#123456", "stroke": "#654321"}}
        level = metric_infos.get_risk_level(2)
        style = self.make_map(zone, level).zone_style("zone")
        self.assertEqual(style["color"], "#654321")
        self.assertEqual(style["fillColor"], level["color"])

    def test_zones_take_preset_colours_in_number_order(self):
        zones = [
            {"code": "songkhla-zone-3"},
            {"code": "songkhla-zone-1"},
            {"code": "songkhla-zone-2"},
        ]
        ordered = sorted(zones, key=Map._zone_order_key)
        map_view = Map.__new__(Map)
        map_view.map = _BrowserStub()
        colours = [
            map_view.zone_identity(zone, index)["color"]
            for index, zone in enumerate(ordered)
        ]
        self.assertEqual([z["code"][-1] for z in ordered], ["1", "2", "3"])
        self.assertEqual(colours, [i["color"] for i in Map.ZONE_IDENTITIES])
        self.assertEqual(len(set(i["dash"] for i in Map.ZONE_IDENTITIES)), 3)

    def test_casing_is_a_wider_dark_line_without_fill(self):
        level = metric_infos.get_risk_level(1)
        map_view = self.make_map({"code": "songkhla-zone-1"}, level)
        style = map_view.zone_style("zone", "selected")
        casing = map_view.zone_casing_style(style)
        self.assertEqual(casing["color"], Map.ZONE_CASING_COLOR)
        self.assertGreater(casing["weight"], style["weight"])
        self.assertFalse(casing["fill"])

    def test_reference_boundary_keeps_its_colour_during_alert(self):
        zone = {
            "zone_kind": "reference",
            "metadata": {"fill": "#111111", "stroke": "#222222"},
        }
        level = metric_infos.get_risk_level(3)

        style = self.make_map(zone, level).zone_style("zone")

        self.assertEqual(style["color"], "#222222")
        self.assertEqual(style["fillColor"], "transparent")

    def test_zone_keeps_its_numbered_colour_when_an_earlier_zone_is_hidden(self):
        map_view = Map.__new__(Map)
        map_view.map = _BrowserStub()
        identity = map_view.zone_identity({"code": "songkhla-zone-3"}, 1)
        self.assertEqual(identity, dict(Map.ZONE_IDENTITIES[2]))

    def test_metadata_zone_number_wins_over_the_code(self):
        zone = {"code": "zone-9", "metadata": {"zone_number": 2}}
        self.assertEqual(Map.zone_number(zone), 2)

    def test_zone_number_comes_from_the_digits_after_zone_in_the_code(self):
        cases = {
            "songkhla-zone-2": 2,
            "zone-1-v2": 1,
            "songkhla-zone-3-2026": 3,
            "Zone_4": 4,
            "TSL40": None,
            "code-123": None,
        }
        for code, number in cases.items():
            with self.subTest(code=code):
                self.assertEqual(Map.zone_number({"code": code}), number)

    def test_unnumbered_zone_falls_back_to_its_draw_order(self):
        map_view = Map.__new__(Map)
        map_view.map = _BrowserStub()
        identity = map_view.zone_identity({"code": "east"}, 1)
        self.assertEqual(identity, dict(Map.ZONE_IDENTITIES[1]))

    def test_unsafe_stroke_and_dash_fall_back_to_the_preset(self):
        map_view = Map.__new__(Map)
        map_view.map = _BrowserStub()
        zone = {
            "code": "songkhla-zone-1",
            "metadata": {
                "stroke": 'red;background:url("x")',
                "dashArray": "4 4;stroke:red",
            },
        }
        self.assertEqual(map_view.zone_identity(zone), dict(Map.ZONE_IDENTITIES[0]))

    def test_valid_custom_dash_is_kept(self):
        map_view = Map.__new__(Map)
        map_view.map = _BrowserStub()
        zone = {"code": "songkhla-zone-1", "metadata": {"dashArray": "4, 4"}}
        self.assertEqual(map_view.zone_identity(zone)["dash"], "4, 4")

    def test_initial_viewport_includes_every_zone_and_reference_boundary(self):
        map_view = Map.__new__(Map)
        map_view.leaflet = _Leaflet()
        map_view.map = _ViewportMap()
        map_view.zone_layers_by_id = {
            f"zone-{index}": {"layer": _BoundedLayer(f"zone-{index}")}
            for index in range(1, 5)
        }
        map_view.reference_boundary_layer = _BoundedLayer("reference")

        import maps.map as map_module

        browser = sys.modules["browser"]
        saved = (browser.document, map_module.window)
        browser.document, map_module.window = _Document(), _Window(1440, 900)
        try:
            map_view.fit_to_hatyai_bounds()
        finally:
            browser.document, map_module.window = saved

        self.assertEqual(
            map_view.map.fits[0][0].names,
            ["zone-1", "zone-2", "zone-3", "zone-4", "reference"],
        )
        self.assertEqual(
            map_view.map.fits[0][1],
            {"paddingTopLeft": [24, 80], "paddingBottomRight": [24, 24]},
        )
        self.assertEqual(map_view.map.invalidations, [{"pan": False}])


class _Storage:
    def __init__(self, value=None):
        self.value = value

    def getItem(self, key):
        return self.value


class _Media:
    def __init__(self, matches):
        self.matches = matches


class _LegendWindow:
    def __init__(self, saved=None, wide=True):
        self.localStorage = _Storage(saved)
        self._wide = wide

    def matchMedia(self, query):
        return _Media(self._wide)


class LegendTests(unittest.TestCase):
    """The legend folds to a chip so it doesn't cover the map on phones."""

    LEVELS = [
        {"color": "#22c55e", "label": "ปกติ", "range": "ต่ำกว่าเฝ้าระวัง"},
        {"color": "#ef4444", "label": "วิกฤต", "range": "ถึงระดับวิกฤต"},
    ]

    def make_map(self):
        from maps.base import BaseMap

        map_view = BaseMap.__new__(BaseMap)
        map_view.map = _BrowserStub()
        map_view.zone_layers_by_id = {}
        return map_view

    def starts_collapsed(self, saved, wide):
        import maps.legend as legend_module

        saved_window = legend_module.window
        legend_module.window = _LegendWindow(saved, wide)
        try:
            return self.make_map().legend_starts_collapsed()
        finally:
            legend_module.window = saved_window

    def test_folded_chip_shows_only_the_colours(self):
        html = self.make_map().legend_html(self.LEVELS, "ระดับน้ำ", collapsed=True)
        self.assertIn('aria-expanded="false"', html)
        self.assertIn("#ef4444", html)
        self.assertNotIn("ถึงระดับวิกฤต", html)

    def test_open_legend_lists_every_level(self):
        html = self.make_map().legend_html(self.LEVELS, "ระดับน้ำ", collapsed=False)
        self.assertIn('aria-expanded="true"', html)
        for level in self.LEVELS:
            self.assertIn(level["label"], html)

    def test_folded_by_default_on_narrow_screens_only(self):
        self.assertTrue(self.starts_collapsed(saved=None, wide=False))
        self.assertFalse(self.starts_collapsed(saved=None, wide=True))

    def test_the_viewer_choice_wins_over_screen_width(self):
        self.assertFalse(self.starts_collapsed(saved="0", wide=False))
        self.assertTrue(self.starts_collapsed(saved="1", wide=True))

    def test_zone_names_are_escaped_in_the_legend(self):
        map_view = self.make_map()
        map_view.map = _ShownLayers()
        layer = object()
        map_view.map.shown.add(layer)
        map_view.zone_layers_by_id = {
            "z": {
                "zone": {"name": "<img src=x onerror=alert(1)>"},
                "layer": layer,
                "identity": dict(Map.ZONE_IDENTITIES[0]),
            }
        }
        html = map_view.zone_legend_html()
        self.assertNotIn("<img", html)
        self.assertIn("&lt;img", html)

    def test_hidden_zones_drop_out_of_the_legend(self):
        map_view = self.make_map()
        map_view.map = _ShownLayers()
        shown, hidden = object(), object()
        map_view.map.shown.add(shown)
        map_view.zone_layers_by_id = {
            "a": {
                "zone": {"name": "โซน 1"},
                "layer": shown,
                "identity": dict(Map.ZONE_IDENTITIES[0]),
            },
            "b": {
                "zone": {"name": "โซน 2"},
                "layer": hidden,
                "identity": dict(Map.ZONE_IDENTITIES[1]),
            },
        }
        names = [e["name"] for e in map_view.visible_zone_legend_entries()]
        self.assertEqual(names, ["โซน 1"])
        map_view.zones_visible = False
        self.assertEqual(map_view.visible_zone_legend_entries(), [])

    def test_failed_river_load_is_reported_in_the_legend(self):
        map_view = self.make_map()
        self.assertEqual(map_view.rivers_status_html(), "")
        map_view.rivers_unavailable = True
        self.assertIn("โหลดเส้นแม่น้ำไม่สำเร็จ", map_view.rivers_status_html())


class _ShownLayers:
    def __init__(self):
        self.shown = set()

    def hasLayer(self, layer):
        return layer in self.shown

    def addLayer(self, layer):
        self.shown.add(layer)

    def removeLayer(self, layer):
        self.shown.discard(layer)

    def remove(self):
        pass


class _Pane:
    def __init__(self):
        self.style = types.SimpleNamespace()


class _PaneMap(_ShownLayers):
    def __init__(self):
        super().__init__()
        self.panes = {}

    def getPane(self, name):
        return self.panes.get(name)

    def createPane(self, name):
        self.panes[name] = _Pane()
        return self.panes[name]


class _GeoJson:
    def __init__(self, feature, options):
        self.feature = feature
        self.options = options
        self.tooltips = []

    def bindTooltip(self, html, options):
        self.tooltips.append(html)

    def on(self, event, handler):
        pass

    def addTo(self, map_view):
        map_view.addLayer(self)


class _ZoneLeaflet:
    def svg(self, options):
        return options

    def geoJson(self, feature, options):
        return _GeoJson(feature, options)


class ShowAllZonesTests(unittest.TestCase):
    def draw(self, zones):
        map_view = Map.__new__(Map)
        map_view.map = _PaneMap()
        map_view.leaflet = _ZoneLeaflet()
        map_view.zone_layers_by_id = {}
        map_view._selected_zone_ids = []
        map_view._zone_renderer = None
        map_view.zones_visible = True
        map_view.show_all_zones(zones)
        return map_view

    def zone(self, number, status="active", name=None):
        return {
            "id": f"z{number}",
            "code": f"songkhla-zone-{number}",
            "name": name or f"Zone {number}",
            "status": status,
            "boundary": {"type": "Polygon", "coordinates": []},
        }

    def test_inactive_zone_does_not_shift_the_colours_of_later_zones(self):
        map_view = self.draw([self.zone(1), self.zone(2, "inactive"), self.zone(3)])
        self.assertNotIn("z2", map_view.zone_layers_by_id)
        self.assertEqual(
            map_view.zone_layers_by_id["z3"]["identity"],
            dict(Map.ZONE_IDENTITIES[2]),
        )

    def test_zone_name_is_escaped_in_the_map_label(self):
        map_view = self.draw([self.zone(1, name="<b>x</b>")])
        tooltip = map_view.zone_layers_by_id["z1"]["layer"].tooltips[0]
        self.assertNotIn("<b>", tooltip)
        self.assertIn("&lt;b&gt;x&lt;/b&gt;", tooltip)

    def test_casings_sit_in_their_own_pane_below_the_zones(self):
        map_view = self.draw([self.zone(1)])
        casing = map_view.zone_layers_by_id["z1"]["casing"]
        self.assertEqual(casing.options["pane"], "zoneCasings")
        self.assertFalse(casing.options["interactive"])
        self.assertLess(
            int(map_view.map.panes["zoneCasings"].style.zIndex),
            int(map_view.map.panes["zones"].style.zIndex),
        )


def _relative_luminance(hex_color):
    channels = []
    for i in (1, 3, 5):
        c = int(hex_color[i : i + 2], 16) / 255
        channels.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
    r, g, b = channels
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast(a, b):
    la, lb = sorted((_relative_luminance(a), _relative_luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


class ZoneContrastTests(unittest.TestCase):
    MID_GRAY_BASEMAP = "#808080"

    def test_every_zone_colour_stands_out_from_its_dark_casing(self):
        for identity in Map.ZONE_IDENTITIES:
            with self.subTest(color=identity["color"]):
                self.assertGreaterEqual(
                    _contrast(identity["color"], Map.ZONE_CASING_COLOR), 3.0
                )

    def test_casing_stands_out_from_a_mid_gray_basemap(self):
        self.assertGreaterEqual(
            _contrast(Map.ZONE_CASING_COLOR, self.MID_GRAY_BASEMAP), 3.0
        )


class ZoneAdminTemplateTests(unittest.TestCase):
    TEMPLATE = (
        Path(__file__).resolve().parents[2]
        / "sindhu"
        / "web"
        / "templates"
        / "zones"
        / "index.html"
    )

    def test_admin_preview_uses_the_same_zone_identities_as_the_map(self):
        import re

        source = self.TEMPLATE.read_text(encoding="utf-8")
        block = re.search(r"const ZONE_IDENTITIES = \[(.*?)\];", source, re.S)
        self.assertIsNotNone(block)
        presets = re.findall(
            r'\{ color: "(#[0-9a-fA-F]{6})", dash: "([^"]*)" \}', block.group(1)
        )
        self.assertEqual(
            presets, [(i["color"], i["dash"]) for i in Map.ZONE_IDENTITIES]
        )

    def test_admin_form_no_longer_writes_fill_or_shading_mode(self):
        source = self.TEMPLATE.read_text(encoding="utf-8")
        self.assertNotIn("form-shading-mode", source)
        self.assertNotIn("shading_mode: shadingMode", source)
        self.assertNotIn("fill: color", source)


class RiverStyleTests(unittest.TestCase):
    def style(self, fclass, zoom):
        map_view = Map.__new__(Map)
        map_view.map = _BrowserStub()
        return map_view.river_style(fclass, zoom)

    def test_main_waterways_show_at_every_zoom(self):
        for fclass in ("river", "canal"):
            with self.subTest(fclass=fclass):
                self.assertGreater(self.style(fclass, 8)["weight"], 0)

    def test_streams_and_drains_wait_for_detail_zoom(self):
        for fclass in ("stream", "drain"):
            with self.subTest(fclass=fclass):
                self.assertEqual(
                    self.style(fclass, Map.RIVER_DETAIL_ZOOM - 1)["weight"], 0
                )
                self.assertGreater(
                    self.style(fclass, Map.RIVER_DETAIL_ZOOM)["weight"], 0
                )

    def test_rivers_are_drawn_heavier_than_canals_and_streams(self):
        zoom = 13
        weights = [self.style(f, zoom)["weight"] for f in ("river", "canal", "stream")]
        self.assertEqual(weights, sorted(weights, reverse=True))

    def test_unknown_class_is_drawn_like_a_stream(self):
        self.assertEqual(self.style(None, 13), self.style("stream", 13))


class _MutableClassList:
    def __init__(self):
        self.names = set()

    def add(self, name):
        self.names.add(name)

    def remove(self, name):
        self.names.discard(name)

    def contains(self, name):
        return name in self.names


class _FocusDocument:
    def __init__(self):
        self.body = types.SimpleNamespace(classList=_MutableClassList())


class FocusModeTests(unittest.TestCase):
    def make_map(self, reset_display):
        map_view = Map.__new__(Map)
        map_view.map = _BrowserStub()
        map_view._reset_btn_container = types.SimpleNamespace(
            style=types.SimpleNamespace(display=reset_display)
        )
        map_view.lifts = 0

        def lift():
            map_view.lifts += 1

        map_view._lift_reset_button_over_legends = lift
        return map_view

    def toggle(self, map_view, *states):
        browser = sys.modules["browser"]
        saved = browser.document
        browser.document = _FocusDocument()
        try:
            for state in states:
                map_view.set_focus_mode(state)
        finally:
            browser.document = saved

    def test_leaving_focus_mode_restacks_a_visible_reset_button(self):
        map_view = self.make_map("block")
        self.toggle(map_view, True, False)
        self.assertEqual(map_view.lifts, 1)

    def test_hidden_reset_button_is_left_alone(self):
        map_view = self.make_map("none")
        self.toggle(map_view, True, False)
        self.assertEqual(map_view.lifts, 0)


class LegendRedrawTests(unittest.TestCase):
    def render(self, reset_display):
        from maps.base import BaseMap

        map_view = BaseMap.__new__(BaseMap)
        map_view.map = _BrowserStub()
        map_view.zone_layers_by_id = {}
        map_view._reset_btn_container = types.SimpleNamespace(
            style=types.SimpleNamespace(display=reset_display)
        )
        map_view.lifts = 0

        def lift():
            map_view.lifts += 1

        map_view._lift_reset_button_over_legends = lift
        map_view._legend_collapsed = False
        map_view._metric_legend_container = types.SimpleNamespace(
            html="", select_one=lambda selector: None
        )
        map_view.render_legend([], "ระดับน้ำ")
        return map_view

    def test_redrawn_legend_restacks_a_visible_reset_button(self):
        self.assertEqual(self.render("block").lifts, 1)

    def test_redrawn_legend_leaves_a_hidden_reset_button_alone(self):
        self.assertEqual(self.render("none").lifts, 0)


class _Rect:
    def __init__(self, left, top, width, height):
        self.left, self.top, self.width, self.height = left, top, width, height


class _Element:
    def __init__(self, rect):
        self._rect = rect

    def getBoundingClientRect(self):
        return self._rect


class _ClassList:
    def __init__(self, names):
        self.names = set(names)

    def contains(self, name):
        return name in self.names


class _Body:
    def __init__(self, classes):
        self.classList = _ClassList(classes)


class _Document:
    def __init__(self, panel=None, body_classes=()):
        self.body = _Body(body_classes)
        self._panel = panel

    def getElementById(self, element_id):
        return self._panel if element_id == "monitor_panel" else None


class _Window:
    def __init__(self, width, height):
        self.innerWidth, self.innerHeight = width, height


class MapFitPaddingTests(unittest.TestCase):
    """fitBounds keeps zones out from under the floating cards (#67)."""

    def fit(self, document, window):
        import maps.map as map_module

        browser = sys.modules["browser"]
        saved = (browser.document, map_module.window)
        browser.document, map_module.window = document, window
        try:
            map_view = Map.__new__(Map)
            map_view.map = _BrowserStub()
            return map_view.fit_bounds_options()
        finally:
            browser.document, map_module.window = saved

    def test_desktop_pads_the_right_edge_by_the_panel(self):
        panel = _Element(_Rect(left=1044, top=64, width=384, height=824))
        options = self.fit(_Document(panel), _Window(1440, 900))
        self.assertEqual(options["paddingTopLeft"], [24, 80])
        self.assertEqual(options["paddingBottomRight"], [420, 24])

    def test_folded_pill_adds_no_side_padding(self):
        panel = _Element(_Rect(left=1100, top=64, width=328, height=46))
        options = self.fit(_Document(panel), _Window(1440, 900))
        self.assertEqual(options["paddingTopLeft"], [24, 80])
        self.assertEqual(options["paddingBottomRight"], [24, 24])

    def test_open_panel_covering_a_phone_is_ignored(self):
        panel = _Element(_Rect(left=12, top=64, width=366, height=768))
        options = self.fit(_Document(panel), _Window(390, 844))
        self.assertEqual(options["paddingBottomRight"], [24, 24])

    def test_focus_mode_uses_plain_padding(self):
        panel = _Element(_Rect(left=1044, top=64, width=384, height=824))
        document = _Document(panel, body_classes=["map-focus"])
        options = self.fit(document, _Window(1440, 900))
        self.assertEqual(options["paddingTopLeft"], [24, 24])
        self.assertEqual(options["paddingBottomRight"], [24, 24])

    def test_hidden_panel_adds_no_side_padding(self):
        panel = _Element(_Rect(left=0, top=0, width=0, height=0))
        options = self.fit(_Document(panel), _Window(1440, 900))
        self.assertEqual(options["paddingBottomRight"], [24, 24])


if __name__ == "__main__":
    unittest.main()
