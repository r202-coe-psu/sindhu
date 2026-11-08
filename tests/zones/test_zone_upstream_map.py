import sys
import types
import unittest
from unittest import mock
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


def _load_map_class():
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

    return Map


Map = _load_map_class()


class _Layer:
    def __init__(self):
        self.styles = []

    def setStyle(self, style):
        self.styles.append(style)

    def bringToFront(self):
        pass

    @property
    def style(self):
        return self.styles[-1]


class _Element:
    def __init__(self):
        self.text = ""
        self.style = types.SimpleNamespace(display="")


class _Container:
    def __init__(self):
        self.children = []

    def appendChild(self, child):
        self.children.append(child)


class _Document:
    def createElement(self, tag):
        return _Element()


class _LeafletMap:
    def __init__(self, container):
        self.container = container

    def getContainer(self):
        return self.container

    def fitBounds(self, *args, **kwargs):
        pass

    def remove(self):
        pass


ZONES = [
    {
        "id": "z1",
        "name": "Zone 1",
        "name_th": "โซน 1",
        "upstream_zone_ids": ["z2", "z3"],
    },
    {"id": "z2", "name": "Zone 2", "name_th": "โซน 2", "upstream_zone_ids": []},
    {"id": "z3", "name": "Zone 3", "upstream_zone_ids": []},
    {"id": "z4", "name": "Zone 4", "name_th": "โซน 4"},
]


class ZoneUpstreamMapTests(unittest.TestCase):
    def setUp(self):
        self.container = _Container()
        self.map_view = Map.__new__(Map)
        self.map_view.map = _LeafletMap(self.container)
        self.map_view.zone_layers_by_id = {
            zone["id"]: {"layer": _Layer(), "zone": zone, "risk": None, "style": {}}
            for zone in ZONES
        }
        self.map_view._selected_zone_id = None
        self.map_view._reset_btn_container = None
        self.map_view.zone_shading_mode = "outline"

        patcher = mock.patch.object(sys.modules["browser"], "document", _Document())
        patcher.start()
        self.addCleanup(patcher.stop)

    def layer(self, zone_id):
        return self.map_view.zone_layers_by_id[zone_id]["layer"]

    def label(self):
        return self.container.children[0]

    def label_text_if_visible(self):
        if not self.container.children or self.label().style.display == "none":
            return None
        return self.label().text

    def assertStyledAsUpstream(self, zone_id):
        style = self.layer(zone_id).style
        self.assertTrue(style["dashArray"])
        self.assertNotEqual(style, self.map_view.zone_style(zone_id))
        self.assertNotEqual(style, self.map_view.zone_style(zone_id, "selected"))

    def assertStyledAsNormal(self, zone_id):
        self.assertEqual(self.layer(zone_id).style, self.map_view.zone_style(zone_id))

    def test_selecting_a_zone_highlights_its_upstream_zones(self):
        self.map_view.select_zone("z1", fit_bounds=False)

        self.assertStyledAsUpstream("z2")
        self.assertStyledAsUpstream("z3")
        self.assertStyledAsNormal("z4")
        self.assertEqual(
            self.layer("z1").style, self.map_view.zone_style("z1", "selected")
        )

    def test_label_names_upstream_zones(self):
        self.map_view.select_zone("z1", fit_bounds=False)

        self.assertEqual(self.label_text_if_visible(), "น้ำไหลมาจาก: โซน 2, Zone 3")

    def test_zone_without_upstream_says_no_data(self):
        self.map_view.select_zone("z2", fit_bounds=False)

        self.assertEqual(self.label_text_if_visible(), "ไม่มีข้อมูลต้นน้ำ")
        for zone_id in ("z1", "z3", "z4"):
            self.assertStyledAsNormal(zone_id)

    def test_zone_from_before_the_field_existed_says_no_data(self):
        self.map_view.select_zone("z4", fit_bounds=False)

        self.assertEqual(self.label_text_if_visible(), "ไม่มีข้อมูลต้นน้ำ")

    def test_upstream_zone_that_is_not_drawn_is_skipped(self):
        self.map_view.zone_layers_by_id["z4"]["zone"] = {
            **ZONES[3],
            "upstream_zone_ids": ["hidden-or-deleted"],
        }

        self.map_view.select_zone("z4", fit_bounds=False)

        self.assertEqual(self.label_text_if_visible(), "ไม่มีข้อมูลต้นน้ำ")

    def test_selecting_another_zone_replaces_the_upstream_highlight(self):
        self.map_view.select_zone("z1", fit_bounds=False)
        self.map_view.select_zone("z4", fit_bounds=False)

        self.assertStyledAsNormal("z2")
        self.assertStyledAsNormal("z3")
        self.assertEqual(self.label_text_if_visible(), "ไม่มีข้อมูลต้นน้ำ")

    def test_clearing_selection_removes_highlight_and_label(self):
        self.map_view.select_zone("z1", fit_bounds=False)

        self.map_view.clear_zone_selection()

        self.assertStyledAsNormal("z2")
        self.assertStyledAsNormal("z3")
        self.assertIsNone(self.label_text_if_visible())

    def test_reset_removes_highlight_and_label(self):
        self.map_view.zone_layer = None
        self.map_view.station_lines = []
        self.map_view.station_markers = []
        self.map_view.select_zone("z1", fit_bounds=False)

        self.map_view.clear_zone_display()

        self.assertStyledAsNormal("z2")
        self.assertIsNone(self.label_text_if_visible())

    def test_risk_update_keeps_upstream_zone_highlighted(self):
        self.map_view.select_zone("z1", fit_bounds=False)

        self.map_view.set_zone_risk(
            "z2", {"risk": 3, "color": "#dc2626", "border": "#991b1b"}
        )

        self.assertStyledAsUpstream("z2")

    def test_shading_mode_change_keeps_upstream_zone_highlighted(self):
        self.map_view.select_zone("z1", fit_bounds=False)

        self.map_view.set_zone_shading_mode("shaded")

        self.assertStyledAsUpstream("z2")
        self.assertEqual(
            self.layer("z1").style, self.map_view.zone_style("z1", "selected")
        )

    def test_risk_update_after_clear_restyles_as_normal(self):
        self.map_view.select_zone("z1", fit_bounds=False)
        self.map_view.clear_zone_selection()

        self.map_view.set_zone_risk(
            "z2", {"risk": 3, "color": "#dc2626", "border": "#991b1b"}
        )

        self.assertStyledAsNormal("z2")


if __name__ == "__main__":
    unittest.main()
