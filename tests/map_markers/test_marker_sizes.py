import importlib.util
import unittest
from pathlib import Path

_MODULE_PATH = (
    Path(__file__).parents[2]
    / "sindhu"
    / "web"
    / "static"
    / "brython"
    / "maps"
    / "marker_sizes.py"
)
_spec = importlib.util.spec_from_file_location("marker_sizes", _MODULE_PATH)
ms = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ms)


class BubbleSizeTests(unittest.TestCase):
    def test_known_values(self):
        self.assertEqual(ms.bubble_size(0), 8)
        self.assertEqual(ms.bubble_size(100), 24)
        self.assertEqual(ms.bubble_size(48), 12)

    def test_negative_clamps_to_min(self):
        self.assertEqual(ms.bubble_size(-50), 8)

    def test_always_within_bounds(self):
        for pct in [-1000, -1, 0, 1, 25, 50, 75, 99, 100, 101, 500]:
            size = ms.bubble_size(pct)
            self.assertGreaterEqual(size, ms.BUBBLE_MIN_PX)
            self.assertLessEqual(size, ms.BUBBLE_MAX_PX)


class IsFarZoomTests(unittest.TestCase):
    def test_zoom_levels(self):
        self.assertTrue(ms.is_far_zoom(11))
        self.assertFalse(ms.is_far_zoom(12))
        self.assertTrue(ms.is_far_zoom(5))

    def test_none_is_not_far(self):
        self.assertFalse(ms.is_far_zoom(None))


class HitAreaTests(unittest.TestCase):
    def test_default_hit_box_at_least_28(self):
        self.assertGreaterEqual(ms.HIT_BOX_PX, 28)

    def test_hit_box_tuples_at_least_28(self):
        for name in ("CCTV_HIT_BOX", "USER_HIT_BOX", "MY_LOCATION_HIT_BOX"):
            box = getattr(ms, name)
            for dim in box:
                self.assertGreaterEqual(dim, 28, f"{name} dimension {dim} < 28")


class ShrinkTests(unittest.TestCase):
    def test_sizes_smaller_than_before(self):
        self.assertLess(ms.STATION_DOT_PX, 24)
        self.assertLess(ms.STATION_TANK[0], 14)
        self.assertLess(ms.STATION_TANK[1], 28)
        self.assertLess(ms.BUBBLE_MAX_PX, 40)
        self.assertLess(ms.CCTV_PIN[0], 28)
        self.assertLess(ms.CCTV_PIN[1], 35)
        self.assertLess(ms.USER_PIN[0], 30)
        self.assertLess(ms.USER_PIN[1], 40)
        self.assertLess(ms.MY_LOCATION_PX, 30)


class VisualFitTests(unittest.TestCase):
    def test_station_dot_fits_hit_box(self):
        self.assertLessEqual(ms.STATION_DOT_PX, ms.HIT_BOX_PX)

    def test_cctv_pin_fits_hit_box(self):
        self.assertLessEqual(ms.CCTV_PIN[0], ms.CCTV_HIT_BOX[0])
        self.assertLessEqual(ms.CCTV_PIN[1], ms.CCTV_HIT_BOX[1])

    def test_user_pin_fits_hit_box(self):
        self.assertLessEqual(ms.USER_PIN[0], ms.USER_HIT_BOX[0])
        self.assertLessEqual(ms.USER_PIN[1], ms.USER_HIT_BOX[1])

    def test_cctv_anchor_is_bottom_center(self):
        self.assertEqual(
            ms.CCTV_ANCHOR, (ms.CCTV_HIT_BOX[0] / 2, ms.CCTV_HIT_BOX[1])
        )


class HaversineTests(unittest.TestCase):
    def test_same_point_is_zero(self):
        self.assertEqual(ms.haversine_distance([100.0, 7.0], [100.0, 7.0]), 0)

    def test_one_thousandth_degree_latitude_is_about_111m(self):
        d = ms.haversine_distance([100.0, 7.0], [100.0, 7.001])
        self.assertAlmostEqual(d, 111, delta=2)

    def test_bad_input_returns_inf(self):
        self.assertEqual(ms.haversine_distance(None, [100.0, 7.0]), float("inf"))
        self.assertEqual(ms.haversine_distance(["x", "y"], [100.0, 7.0]), float("inf"))
        self.assertEqual(ms.haversine_distance([], [100.0, 7.0]), float("inf"))


class IsPairedTests(unittest.TestCase):
    def test_station_within_radius_is_paired(self):
        self.assertTrue(
            ms.is_paired_with_station([100.0, 7.0], [[100.0, 7.002]])
        )

    def test_station_outside_radius_is_not_paired(self):
        self.assertFalse(
            ms.is_paired_with_station([100.0, 7.0], [[100.0, 7.003]])
        )

    def test_empty_station_list_is_not_paired(self):
        self.assertFalse(ms.is_paired_with_station([100.0, 7.0], []))

    def test_none_feed_is_not_paired(self):
        self.assertFalse(ms.is_paired_with_station(None, [[100.0, 7.002]]))

    def test_malformed_station_entry_is_skipped(self):
        self.assertFalse(ms.is_paired_with_station([100.0, 7.0], [[]]))
        self.assertTrue(
            ms.is_paired_with_station([100.0, 7.0], [[], [100.0, 7.002]])
        )


class HitBoxHtmlTests(unittest.TestCase):
    def test_default_width_and_center_alignment(self):
        html = ms.hit_box_html("<i>x</i>")
        self.assertIn("width: 28px", html)
        self.assertIn("align-items: center", html)
        self.assertIn("<i>x</i>", html)

    def test_bottom_alignment_uses_flex_end(self):
        html = ms.hit_box_html("<i>x</i>", align="bottom")
        self.assertIn("align-items: flex-end", html)


if __name__ == "__main__":
    unittest.main()
