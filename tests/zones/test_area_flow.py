import asyncio
import json
import re
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

BRYTHON_ROOT = (
    Path(__file__).resolve().parents[2] / "sindhu" / "web" / "static" / "brython"
)
MAP_SOURCE = BRYTHON_ROOT / "maps" / "map.py"

SQUARE = {
    "type": "Polygon",
    "coordinates": [[[100.0, 7.0], [100.1, 7.0], [100.1, 7.1], [100.0, 7.1], [100.0, 7.0]]],
}


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


class _AioStub:
    @staticmethod
    async def get(url, cache=False):
        return _Response({})

    @staticmethod
    async def post(url, data=None, headers=None):
        return _Response({})

    @staticmethod
    def run(coro):
        return asyncio.run(coro)


class _Response:
    def __init__(self, data, status=200):
        self.status = status
        self.data = json.dumps(data)


def _load_brython_classes():
    if str(BRYTHON_ROOT) not in sys.path:
        sys.path.insert(0, str(BRYTHON_ROOT))

    if "browser" not in sys.modules:
        browser = types.ModuleType("browser")
        for name in ("ajax", "alert", "document", "html", "timer", "window"):
            setattr(browser, name, _BrowserStub())
        browser.aio = _AioStub()
        sys.modules["browser"] = browser
    browser = sys.modules["browser"]
    # Another test module may have registered a leaner aio stub first.
    for name in ("get", "post", "run"):
        if not hasattr(browser.aio, name):
            setattr(browser.aio, name, getattr(_AioStub, name))

    if "javascript" not in sys.modules:
        javascript = types.ModuleType("javascript")
        javascript.JSON = _BrowserStub()
        javascript.NULL = None
        sys.modules["javascript"] = javascript

    from maps.map import Map
    from monitors.base import BaseMonitor
    from monitors.water import WaterMonitor

    return Map, BaseMonitor, WaterMonitor


Map, BaseMonitor, WaterMonitor = _load_brython_classes()

from monitors.area import (  # noqa: E402
    MSG_ERROR,
    MSG_OUTSIDE,
    SOURCE_LIST,
    SOURCE_LOCATION,
    SOURCE_MAP,
    location_message,
)


class RecordingMap:
    """Stands in for BaseMap: records every method call it receives."""

    user_mark = None
    user_coord = None
    _pin_mode_active = False

    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        def record(*args, **kwargs):
            self.calls.append((name, args, kwargs))

        return record

    def names(self):
        return [c[0] for c in self.calls]


class FakeLeafletMap:
    def __init__(self):
        self.handlers = {}
        self.located = 0
        self.fly = []

    def on(self, event, handler):
        self.handlers.setdefault(event, []).append(handler)

    def off(self, event, handler):
        if event in self.handlers and handler in self.handlers[event]:
            self.handlers[event].remove(handler)

    def locate(self):
        self.located += 1

    def flyTo(self, coord, zoom):
        self.fly.append((coord, zoom))

    def remove(self):
        # Map.__del__ calls this on the leaflet map.
        pass

    def fire(self, event, payload):
        for handler in list(self.handlers.get(event, [])):
            handler(payload)


class FlyToUserTests(unittest.TestCase):
    def setUp(self):
        self.map_view = Map.__new__(Map)
        self.map_view.leaflet = _BrowserStub()
        self.map_view.map = FakeLeafletMap()

    def test_location_found_calls_on_found_and_never_alerts(self):
        found, errors = [], []
        alert = Mock()
        with patch.object(sys.modules["browser"], "alert", alert, create=True):
            self.map_view.fly_to_user(
                on_found=lambda lat, lng: found.append((lat, lng)),
                on_error=errors.append,
            )
            self.assertEqual(self.map_view.map.located, 1)
            self.map_view.map.fire(
                "locationfound",
                SimpleNamespace(latlng=SimpleNamespace(lat=7.02, lng=100.47)),
            )

        self.assertEqual(found, [(7.02, 100.47)])
        self.assertEqual(errors, [])
        self.assertEqual(self.map_view.map.fly, [((7.02, 100.47), 16)])
        alert.assert_not_called()

    def test_location_error_calls_on_error_and_never_alerts(self):
        found, errors = [], []
        alert = Mock()
        with patch.object(sys.modules["browser"], "alert", alert, create=True):
            self.map_view.fly_to_user(
                on_found=lambda lat, lng: found.append((lat, lng)),
                on_error=errors.append,
            )
            error = SimpleNamespace(code=1, message="denied")
            self.map_view.map.fire("locationerror", error)

        self.assertEqual(found, [])
        self.assertEqual(errors, [error])
        alert.assert_not_called()

    def test_handlers_are_removed_after_either_outcome(self):
        self.map_view.fly_to_user(on_found=lambda a, b: None, on_error=lambda e: None)
        self.map_view.map.fire(
            "locationfound", SimpleNamespace(latlng=SimpleNamespace(lat=1, lng=2))
        )

        self.assertEqual(self.map_view.map.handlers["locationfound"], [])
        self.assertEqual(self.map_view.map.handlers["locationerror"], [])

    def test_repeat_clicks_while_locating_bind_one_handler_pair(self):
        found = []
        for _ in range(3):
            self.map_view.fly_to_user(
                on_found=lambda lat, lng: found.append((lat, lng)),
                on_error=lambda e: None,
            )
        self.map_view.map.fire(
            "locationfound", SimpleNamespace(latlng=SimpleNamespace(lat=1, lng=2))
        )

        self.assertEqual(self.map_view.map.located, 1)
        self.assertEqual(found, [(1, 2)])

    def test_synchronous_location_error_still_reaches_on_error(self):
        errors = []
        error = SimpleNamespace(code=2, message="unavailable")
        self.map_view.map.locate = lambda: self.map_view.map.fire("locationerror", error)

        self.map_view.fly_to_user(on_found=lambda a, b: None, on_error=errors.append)

        self.assertEqual(errors, [error])

    def test_map_source_has_no_alert_call(self):
        source = MAP_SOURCE.read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"\balert\s*\(", source))


class MonitorAreaFlowTests(unittest.TestCase):
    def setUp(self):
        self.monitor = BaseMonitor("th", "http://test", "water")
        self.monitor.map = RecordingMap()
        self.monitor.zones = [
            {
                "id": "z1",
                "name_th": "Zone A",
                "stations": [{"code": "S1"}, {"code": "S2"}],
                "tambons": ["ควนรู"],
            },
            {
                "id": "z2",
                "name_th": "Zone B",
                "stations": [{"code": "S2"}, {"code": "S3"}],
                "tambons": [],
            },
        ]
        self.messages = []
        self.monitor.set_area_message = lambda text=None: self.messages.append(text)

    def _post(self, payload, status=200):
        async def fake_post(url, data=None, headers=None):
            return _Response(payload, status)

        sys.modules["browser"].aio.post = fake_post

    def _select_zones_calls(self):
        return [c for c in self.monitor.map.calls if c[0] == "select_zones"]

    def test_locate_http_error_shows_error_message(self):
        self._post({"detail": "boom"}, status=500)

        asyncio.run(self.monitor.on_location_received(7.0, 100.0))

        self.assertEqual(
            self.messages[-1],
            location_message(MSG_ERROR, error=RuntimeError("locate returned HTTP 500")),
        )
        self.assertIn("HTTP 500", self.messages[-1])
        self.assertIsNone(self.monitor.selected_zone_codes)

    def test_locate_network_failure_shows_error_message(self):
        async def failing_post(url, data=None, headers=None):
            raise ConnectionError("offline")

        sys.modules["browser"].aio.post = failing_post

        asyncio.run(self.monitor.on_location_received(7.0, 100.0))

        self.assertIn("ไม่สามารถระบุตำแหน่งได้", self.messages[-1])
        self.assertIn("(offline)", self.messages[-1])
        self.assertEqual(self.monitor.selected_zone_ids, [])

    def test_zone_missing_from_drawn_zones_still_selects_its_id_and_codes(self):
        self._post(
            {
                "zone": {"id": "z9", "name_th": "Undrawn", "boundary": SQUARE},
                "nearby_stations": [{"code": "N1"}, {"code": "N2"}],
            }
        )

        asyncio.run(self.monitor.on_location_received(7.05, 100.05))

        self.assertEqual(self.monitor.selected_zone_ids, ["z9"])
        self.assertEqual(self.monitor.selected_zone_codes, ["N1", "N2"])
        self.assertIn("show_zone", self.monitor.map.names())
        self.assertEqual(self.messages[-1], "คุณอยู่ใน Undrawn")

    def test_fit_bounds_only_for_list_selection(self):
        self.monitor.select_area(["z1"], SOURCE_LIST)
        self.monitor.select_area(["z1"], SOURCE_MAP)
        self._post(
            {
                "zone": {"id": "z1", "name_th": "Zone A", "boundary": SQUARE},
                "nearby_stations": [],
            }
        )
        asyncio.run(self.monitor.on_location_received(7.05, 100.05))

        flags = [c[2].get("fit_bounds") for c in self._select_zones_calls()]
        self.assertEqual(flags, [True, False, False])

    def test_no_zone_response_shows_outside_message_and_clears_selection(self):
        from monitors.area import location_message

        self.monitor.selected_zone_ids = ["z1"]
        self.monitor.selected_zone_codes = ["S1"]
        self._post({"zone": None, "nearby_stations": []})

        asyncio.run(self.monitor.on_location_received(7.0, 100.0))

        self.assertIsNone(self.monitor.selected_zone_codes)
        self.assertEqual(self.monitor.selected_zone_ids, [])
        self.assertEqual(self.messages[-1], location_message("outside"))
        self.assertIn("show_all_markers", self.monitor.map.names())
        self.assertEqual(self.messages[-1], location_message(MSG_OUTSIDE))

    def test_zone_response_selects_that_zone_with_server_stations(self):
        # Drawn z1 links S1 and S2; the server dropped inactive S1 and sorted
        # by distance, so its list wins over the zone's own GET /zones list.
        found = []
        self.monitor.on_zone_stations_found = found.append
        self._post(
            {
                "zone": {"id": "z1", "name_th": "Zone A", "boundary": SQUARE},
                "nearby_stations": [{"code": "S2", "distance": 10}],
            }
        )

        asyncio.run(self.monitor.on_location_received(7.05, 100.05))

        self.assertEqual(self.monitor.selected_zone_ids, ["z1"])
        self.assertEqual(self.monitor.selected_zone_codes, ["S2"])
        self.assertEqual(found, [[{"code": "S2", "distance": 10}]])
        self.assertEqual(self.messages[-1], "คุณอยู่ใน Zone A")

    def test_select_area_with_two_zones_merges_codes(self):
        self.monitor.select_area(["z1", "z2"], "list")

        self.assertEqual(self.monitor.selected_zone_ids, ["z1", "z2"])
        self.assertEqual(self.monitor.selected_zone_codes, ["S1", "S2", "S3"])
        filter_calls = [c for c in self.monitor.map.calls if c[0] == "filter_markers_by_codes"]
        self.assertEqual(filter_calls[-1][1], (["S1", "S2", "S3"],))

    def test_slow_older_pick_does_not_overwrite_newer_pick(self):
        self.monitor.zones[0]["stations"] = []  # zone A must fetch its stations
        release = None

        async def slow_get(url, cache=False):
            await release.wait()
            return _Response({"stations": [{"code": "S1"}]})

        async def scenario():
            nonlocal release
            release = asyncio.Event()
            sys.modules["browser"].aio.get = slow_get
            older = asyncio.create_task(self.monitor._select_area(["z1"], SOURCE_LIST))
            await asyncio.sleep(0)
            await self.monitor._select_area(["z2"], SOURCE_LIST)
            release.set()
            return await older

        try:
            self.assertFalse(asyncio.run(scenario()))
        finally:
            sys.modules["browser"].aio.get = _AioStub.get

        self.assertEqual(self.monitor.selected_zone_ids, ["z2"])
        self.assertEqual(self.monitor.selected_zone_codes, ["S2", "S3"])

    def test_select_area_with_unknown_ids_selects_nothing(self):
        self.assertFalse(
            asyncio.run(self.monitor._select_area(["nope"], "list"))
        )
        self.assertEqual(self.monitor.selected_zone_ids, [])


class WaterSourceChangeTests(unittest.TestCase):
    def test_source_change_keeps_the_merged_zone_codes(self):
        monitor = WaterMonitor("th", "http://test", "water")
        monitor.map = RecordingMap()
        monitor.zones = [
            {"id": "z1", "name_th": "Zone A", "stations": [{"code": "S1"}, {"code": "S2"}]},
            {"id": "z2", "name_th": "Zone B", "stations": [{"code": "S2"}, {"code": "S3"}]},
        ]
        monitor.set_area_message = lambda text=None: None
        monitor.latest_data = {"stations": []}
        monitor.select_area(["z1", "z2"], "list")

        with patch.object(monitor, "apply_marker_filters") as apply_filters, patch.object(
            monitor, "render_data_list"
        ) as render, patch.object(monitor, "update_zone_risks"):
            monitor.on_source_change(SimpleNamespace(target=SimpleNamespace(value="rain")))

        # apply_marker_filters() takes its codes from selected_zone_codes.
        apply_filters.assert_called_once_with()
        render.assert_called_once_with()
        self.assertEqual(monitor.selected_zone_codes, ["S1", "S2", "S3"])
        self.assertEqual(monitor.selected_zone_ids, ["z1", "z2"])


if __name__ == "__main__":
    unittest.main()
