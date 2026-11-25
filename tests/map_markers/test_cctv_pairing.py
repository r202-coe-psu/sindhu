import sys
import unittest
from pathlib import Path

BRYTHON_ROOT = (
    Path(__file__).resolve().parents[2] / "sindhu" / "web" / "static" / "brython"
)
if str(BRYTHON_ROOT) not in sys.path:
    sys.path.append(str(BRYTHON_ROOT))

from maps import cctv_pairing as cp  # noqa: E402
from maps.marker_sizes import CCTV, HIT_BOX_PX  # noqa: E402


def _item(code=None, lng=100.0, lat=7.0):
    return {"code": code, "coordinates": {"coordinates": [lng, lat]}}


class HaversineTests(unittest.TestCase):
    def test_same_point_is_zero(self):
        self.assertEqual(cp.haversine_distance([100.0, 7.0], [100.0, 7.0]), 0)

    def test_one_thousandth_degree_latitude_is_about_111m(self):
        d = cp.haversine_distance([100.0, 7.0], [100.0, 7.001])
        self.assertAlmostEqual(d, 111, delta=2)

    def test_bad_input_returns_inf(self):
        self.assertEqual(cp.haversine_distance(None, [100.0, 7.0]), float("inf"))
        self.assertEqual(cp.haversine_distance(["x", "y"], [100.0, 7.0]), float("inf"))
        self.assertEqual(cp.haversine_distance([], [100.0, 7.0]), float("inf"))


class FindMatchTests(unittest.TestCase):
    def test_same_code_wins_over_a_nearer_camera(self):
        near = _item("other", lat=7.0001)
        same_code = _item("STN04", lat=7.01)  # ~1.1 km away
        self.assertIs(cp.find_match(_item("stn04"), [near, same_code]), same_code)

    def test_nearest_within_radius_without_code(self):
        far = _item(lat=7.002)
        near = _item(lat=7.001)
        self.assertIs(cp.find_match(_item(), [far, near]), near)

    def test_beyond_radius_is_no_match(self):
        self.assertIsNone(cp.find_match(_item(), [_item(lat=7.003)]))

    def test_malformed_input_is_skipped(self):
        good = _item(lat=7.001)
        candidates = [None, "x", {"coordinates": None}, _item(lat=None), good]
        self.assertIs(cp.find_match(_item(), candidates), good)
        self.assertIsNone(cp.find_match(None, [good]))
        self.assertIsNone(cp.find_match(_item(), None))

    def test_works_in_both_directions(self):
        station, camera = _item("A"), _item("a", lat=7.01)
        self.assertIs(cp.find_match(station, [camera]), camera)
        self.assertIs(cp.find_match(camera, [station]), station)


def _station(sid, code=None, lat=7.0):
    return dict(_item(code, lat=lat), id=sid)


def _feed(uid, code=None, lat=7.0):
    return dict(_item(code, lat=lat), source="rid", upstream_id=uid)


class PairCamerasTests(unittest.TestCase):
    def test_station_shows_only_a_camera_that_belongs_to_it(self):
        # camera A is nearest S2, but camera C is nearer S2 than A is; the
        # old station -> camera lookup gave S2 camera C while A's pin
        # belonged to S2
        s1, s2 = _station("s1", lat=7.0), _station("s2", lat=7.0018)
        a, c = _feed("a", lat=7.0012), _feed("c", lat=7.0022)
        station_of, camera_of = cp.pair_cameras([a, c], [s1, s2])
        self.assertIs(station_of["rid_a"], s2)
        self.assertIs(station_of["rid_c"], s2)
        self.assertIs(camera_of["s2"], c)
        self.assertNotIn("s1", camera_of)
        for station_id, camera in camera_of.items():
            key = cp.feed_key(camera["source"], camera["upstream_id"])
            self.assertEqual(station_of[key]["id"], station_id)

    def test_same_code_wins_for_both_sides(self):
        st = _station("s1", "STN04")
        near, coded = _feed("near", lat=7.0001), _feed("coded", "stn04", lat=7.01)
        station_of, camera_of = cp.pair_cameras([near, coded], [st])
        self.assertIs(camera_of["s1"], coded)
        self.assertIs(station_of["rid_near"], st)

    def test_no_feeds_or_stations(self):
        self.assertEqual(cp.pair_cameras(None, [_station("s1")]), ({}, {}))
        self.assertEqual(cp.pair_cameras([_feed("a")], []), ({}, {}))


def _overlaps(dx, dy):
    """Pin visual with its tip at (dx, dy) vs the station hit box at (0, 0)."""
    half = HIT_BOX_PX / 2
    w, h = CCTV.pin
    return not (
        dx + w / 2 <= -half or dx - w / 2 >= half or dy <= -half or dy - h >= half
    )


class PinShiftTests(unittest.TestCase):
    def test_far_apart_is_not_moved(self):
        self.assertEqual(cp.pin_shift(100, 0), (0, 0))
        self.assertEqual(cp.pin_shift(0, -60), (0, 0))

    def test_same_point_moves_upper_right(self):
        sx, sy = cp.pin_shift(0, 0)
        self.assertGreater(sx, 0)
        self.assertLess(sy, 0)
        self.assertFalse(_overlaps(sx, sy))

    def test_moves_away_from_the_station(self):
        sx, sy = cp.pin_shift(-5, 3)  # camera lower left of the station
        self.assertLess(sx, 0)
        self.assertGreater(sy, 0)

    def test_result_never_overlaps(self):
        for dx in range(-40, 41, 3):
            for dy in range(-50, 41, 3):
                sx, sy = cp.pin_shift(dx, dy)
                self.assertFalse(
                    _overlaps(dx + sx, dy + sy), f"still overlaps from {(dx, dy)}"
                )

    def test_shift_is_whole_pixels(self):
        sx, sy = cp.pin_shift(3, -2)
        self.assertIsInstance(sx, int)
        self.assertIsInstance(sy, int)


if __name__ == "__main__":
    unittest.main()
