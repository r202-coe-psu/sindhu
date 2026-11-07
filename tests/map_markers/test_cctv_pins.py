"""Camera pins move off their station whichever layer loads first, and follow
filters and zoom."""

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


def _load_base_map():
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

    return BaseMap


BaseMap = _load_base_map()


class _Overlay:
    def __init__(self):
        self.is_open = False
        self.updates = 0

    def update(self):
        self.updates += 1


class _Marker:
    def __init__(self, lat, lng, icon=None):
        self.lat, self.lng = lat, lng
        self.icon = icon
        self.set_icon_calls = 0
        self.popup = _Overlay()
        self.tooltip = _Overlay()

    def getLatLng(self):
        return types.SimpleNamespace(lat=self.lat, lng=self.lng)

    def setIcon(self, icon):
        self.icon = icon
        self.set_icon_calls += 1

    def isPopupOpen(self):
        return self.popup.is_open

    def getPopup(self):
        return self.popup

    def isTooltipOpen(self):
        return self.tooltip.is_open

    def getTooltip(self):
        return self.tooltip

    def bindTooltip(self, *_args):
        return self

    def on(self, *_args):
        return self


class _LeafletMap:
    """Flat projection: ``scale`` px per degree, y grows southward."""

    def __init__(self, scale):
        self.scale = scale
        self.layers = set()

    def hasLayer(self, layer):
        return id(layer) in self.layers

    def remove(self):
        pass

    def latLngToLayerPoint(self, latlng):
        if isinstance(latlng, list):
            lat, lng = latlng
        else:
            lat, lng = latlng.lat, latlng.lng
        return types.SimpleNamespace(x=lng * self.scale, y=-lat * self.scale)


class _Leaflet:
    @staticmethod
    def divIcon(options):
        return options

    @staticmethod
    def marker(latlng, options):
        return _Marker(latlng[0], latlng[1], options["icon"])


# 0.0001 deg -> 10 px: a camera 11 m north of a station overlaps it
CLOSE_ZOOM = 100_000
# 0.0001 deg -> 1000 px: the same pair is far apart on screen
DEEP_ZOOM = 10_000_000

FEED = {
    "source": "rid",
    "upstream_id": "cam1",
    "code": "",
    "coordinates": {"coordinates": [100.0, 7.0001]},
}


class CctvPinTests(unittest.TestCase):
    def setUp(self):
        self.view = BaseMap.__new__(BaseMap)
        self.view.leaflet = _Leaflet()
        self.view.map = _LeafletMap(CLOSE_ZOOM)
        self.view.metric_markers = {}
        self.view.latest_stations = []
        self.view.visual_feeds = []
        self.view.visual_feed_markers_by_id = {}
        self.view.visual_feed_shift = {}
        self.view.cctv_station_of = {}
        self.view.cctv_camera_of = {}
        self.view.set_visual_feed_layer = lambda markers: None

    def _add_station(self, station_id="s1", lat=7.0, lng=100.0, code="S1"):
        """Load one more station the way BaseMap.update does: pair, then draw."""
        self.view.latest_stations = self.view.latest_stations + [
            {"id": station_id, "code": code, "coordinates": {"coordinates": [lng, lat]}}
        ]
        self.view.update_cctv_pairs()
        marker = _Marker(lat, lng)
        self.view.metric_markers[station_id] = marker
        self.view.map.layers.add(id(marker))
        return marker

    def _camera(self):
        return self.view.visual_feed_markers_by_id["rid_cam1"]

    def _shift(self):
        return self.view.visual_feed_shift.get("rid_cam1", (0, 0))

    def test_stations_first_then_cameras(self):
        self._add_station()
        self.view.show_visual_feeds([FEED])
        sx, sy = self._shift()
        self.assertLess(sy, 0)  # camera is north, so pushed further up
        self.assertEqual(self._camera().icon["iconAnchor"], [14 - sx, 32 - sy])

    def test_cameras_first_then_stations(self):
        self.view.show_visual_feeds([FEED])
        self.assertEqual(self._shift(), (0, 0))
        self._add_station()
        self.view.refresh_cctv_pins()
        self.assertNotEqual(self._shift(), (0, 0))

    def test_hidden_station_releases_the_pin(self):
        station = self._add_station()
        self.view.show_visual_feeds([FEED])
        self.assertNotEqual(self._shift(), (0, 0))

        self.view.map.layers.discard(id(station))  # filtered out
        self.view.refresh_cctv_pins()
        self.assertEqual(self._shift(), (0, 0))
        self.assertEqual(self._camera().icon["iconAnchor"], [14, 32])

    def test_zooming_in_far_enough_releases_the_pin(self):
        self._add_station()
        self.view.show_visual_feeds([FEED])
        self.assertNotEqual(self._shift(), (0, 0))

        self.view.map.scale = DEEP_ZOOM
        self.view.refresh_cctv_pins()
        self.assertEqual(self._shift(), (0, 0))

    def test_popup_and_tooltip_follow_the_pin(self):
        self._add_station()
        self.view.show_visual_feeds([FEED])
        sx, sy = self._shift()
        icon = self._camera().icon
        self.assertEqual(icon["tooltipAnchor"], [sx, sy])
        self.assertEqual(icon["popupAnchor"][0], sx)

    def test_unchanged_shift_keeps_the_icon(self):
        self._add_station()
        self.view.show_visual_feeds([FEED])
        calls = self._camera().set_icon_calls
        self.view.refresh_cctv_pins()
        self.assertEqual(self._camera().set_icon_calls, calls)

    def test_hidden_linked_station_does_not_hand_the_pin_to_another(self):
        # the camera's own station (by code) is 55 m away; an unrelated
        # station sits right under the camera
        self._add_station("near", lat=7.0001, code="NEAR")
        linked = self._add_station("linked", lat=7.0006, code="CAM")
        self.view.show_visual_feeds([dict(FEED, code="cam")])
        self.view.map.layers.discard(id(linked))  # filtered out
        self.view.refresh_cctv_pins()
        self.assertEqual(self._shift(), (0, 0))

    def test_open_popup_and_tooltip_follow_a_moved_pin(self):
        self.view.show_visual_feeds([FEED])
        camera = self._camera()
        camera.popup.is_open = True
        camera.tooltip.is_open = True
        self._add_station()
        self.view.refresh_cctv_pins()
        self.assertNotEqual(self._shift(), (0, 0))
        self.assertEqual(camera.popup.updates, 1)
        self.assertEqual(camera.tooltip.updates, 1)

    def test_station_card_shows_the_camera_whose_pin_it_moves(self):
        self._add_station()
        self.view.show_visual_feeds([FEED])
        self.assertIs(self.view.find_matching_cctv(self.view.latest_stations[0]), FEED)

    def test_station_not_linked_to_the_camera_does_not_move_it(self):
        # same spot as FEED, but the camera's code points at another station
        self._add_station("near", lat=7.0001, code="NEAR")
        self._add_station("linked", lat=7.01, code="CAM")
        self.view.show_visual_feeds([dict(FEED, code="cam")])
        self.assertEqual(self._shift(), (0, 0))


if __name__ == "__main__":
    unittest.main()
