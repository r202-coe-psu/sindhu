import asyncio
import json
import sys
import types
import unittest
from pathlib import Path

BRYTHON_ROOT = (
    Path(__file__).resolve().parents[2] / "sindhu" / "web" / "static" / "brython"
)


class _BrowserStub(dict):
    def __getattr__(self, name):
        if name not in self:
            self[name] = _BrowserStub()
        return self[name]

    def __setattr__(self, name, value):
        self[name] = value

    def __call__(self, *args, **kwargs):
        return _BrowserStub()

    def __bool__(self):
        return True


def _load_brython_classes():
    if str(BRYTHON_ROOT) not in sys.path:
        sys.path.insert(0, str(BRYTHON_ROOT))

    browser = types.ModuleType("browser")
    for name in ("ajax", "alert", "document", "html", "timer", "window"):
        setattr(browser, name, _BrowserStub())

    class _AioStub:
        @staticmethod
        async def get(url, cache=False):
            return _MockResponse({})

    browser.aio = _AioStub()
    sys.modules.setdefault("browser", browser)

    javascript = types.ModuleType("javascript")
    javascript.JSON = _BrowserStub()
    javascript.NULL = None
    sys.modules.setdefault("javascript", javascript)

    from maps.map import Map
    from monitors.water import WaterMonitor

    return Map, WaterMonitor


Map, WaterMonitor = _load_brython_classes()


class _MockResponse:
    def __init__(self, data):
        self.data = json.dumps(data)


class DbFloodZoneTests(unittest.TestCase):
    def setUp(self):
        self.map_view = Map.__new__(Map)
        self.map_view.leaflet = _BrowserStub()
        self.map_view.map = _BrowserStub()
        self.map_view.zone_layers_by_id = {}
        self.map_view.reference_boundary_layer = None
        self.map_view.reference_boundary_visible = True
        self.map_view.zones_visible = True
        self.map_view._selected_zone_id = None
        self.map_view.ZONE_STYLE = {"color": "#6366f1", "fillColor": "transparent"}

    def test_load_zones_filters_inactive_and_reference_zones(self):
        monitor = WaterMonitor("th", "http://test", "water")
        monitor.map = self.map_view
        rendered_zones = []
        monitor.map.show_all_zones = lambda zones, **kwargs: rendered_zones.extend(
            zones
        )

        mock_data = {
            "zones": [
                {
                    "id": "z1",
                    "name": "Zone A",
                    "status": "active",
                    "zone_kind": "flood",
                },
                {"id": "z2", "name": "Zone B", "status": "inactive"},
                {
                    "id": "z3",
                    "name": "Hat Yai",
                    "status": "active",
                    "zone_kind": "reference",
                    "code": "hatyai-boundary",
                },
                {
                    "id": "z4",
                    "name": "Ref Boundary",
                    "status": "active",
                    "metadata": {"role": "reference_boundary"},
                },
            ]
        }

        async def fake_get(url, cache=False):
            return _MockResponse(mock_data)

        sys.modules["browser"].aio.get = fake_get
        asyncio.run(monitor.load_zones())

        self.assertEqual(len(monitor.zones), 1)
        self.assertEqual(monitor.zones[0]["id"], "z1")
        self.assertEqual(len(rendered_zones), 1)
        self.assertEqual(rendered_zones[0]["id"], "z1")

    def test_load_zones_empty_clears_old_zones(self):
        monitor = WaterMonitor("th", "http://test", "water")
        monitor.map = self.map_view
        calls = []
        monitor.map.show_all_zones = lambda zones, **kwargs: calls.append(zones)

        async def fake_get(url, cache=False):
            return _MockResponse({"zones": []})

        sys.modules["browser"].aio.get = fake_get
        asyncio.run(monitor.load_zones())

        self.assertEqual(monitor.zones, [])
        self.assertEqual(calls, [[]])

    def test_load_zones_api_failure_preserves_existing_zones(self):
        monitor = WaterMonitor("th", "http://test", "water")
        monitor.map = self.map_view
        monitor.zones = [{"id": "existing"}]

        async def fake_get(url, cache=False):
            raise ConnectionError("API down")

        sys.modules["browser"].aio.get = fake_get
        result = asyncio.run(monitor.load_zones())

        self.assertFalse(result)
        self.assertEqual(len(monitor.zones), 1)
        self.assertEqual(monitor.zones[0]["id"], "existing")

    def test_reference_boundary_is_styled_as_black_outline_without_fill(self):
        geo_json_options = []

        def mock_geo_json(feature, options):
            geo_json_options.append(options)
            return _BrowserStub()

        self.map_view.leaflet.geoJson = mock_geo_json
        self.map_view.leaflet.svg = lambda *args: _BrowserStub()

        pane = _BrowserStub()
        self.map_view.map.getPane = lambda *args: pane
        self.map_view.show_reference_boundary({"type": "Polygon", "coordinates": []})

        self.assertEqual(pane.style.pointerEvents, "none")
        self.assertEqual(len(geo_json_options), 1)
        style = geo_json_options[0]["style"]
        self.assertEqual(style["color"], "#0f172a")
        self.assertEqual(style["fillOpacity"], 0.0)
        self.assertFalse(geo_json_options[0]["interactive"])

    def test_dynamic_zone_toggle(self):
        monitor = WaterMonitor("th", "http://test", "water")
        monitor.map = self.map_view
        monitor.zones = [
            {"id": "zone-custom-abc", "code": "code-123"},
            {"id": "zone-custom-xyz", "code": "code-456"},
        ]

        toggled = []
        self.map_view.set_zone_visible = lambda zid, vis: toggled.append((zid, vis))

        event = types.SimpleNamespace(target=types.SimpleNamespace(checked=True))
        monitor.on_toggle_single_zone("zone-custom-abc", event)

        self.assertEqual(toggled, [("zone-custom-abc", True)])


if __name__ == "__main__":
    unittest.main()
