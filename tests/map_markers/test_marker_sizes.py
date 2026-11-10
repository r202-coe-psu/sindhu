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
        for name in ("CCTV", "USER", "MY_LOCATION"):
            box = getattr(ms, name).hit_box
            for dim in box:
                self.assertGreaterEqual(dim, 28, f"{name} dimension {dim} < 28")


class ShrinkTests(unittest.TestCase):
    def test_sizes_smaller_than_before(self):
        self.assertLess(ms.STATION_DOT_PX, 24)
        self.assertLess(ms.STATION_TANK[0], 14)
        self.assertLess(ms.STATION_TANK[1], 28)
        self.assertLess(ms.BUBBLE_MAX_PX, 40)
        self.assertLess(ms.CCTV.pin[0], 28)
        self.assertLess(ms.CCTV.pin[1], 35)
        self.assertLess(ms.USER.pin[0], 30)
        self.assertLess(ms.USER.pin[1], 40)
        self.assertLess(ms.MY_LOCATION.pin[1], 30)


class VisualFitTests(unittest.TestCase):
    def test_station_dot_fits_hit_box(self):
        self.assertLessEqual(ms.STATION_DOT_PX, ms.HIT_BOX_PX)

    def test_pins_fit_their_hit_box(self):
        for name in ("CCTV", "USER", "MY_LOCATION"):
            spec = getattr(ms, name)
            self.assertLessEqual(spec.pin[0], spec.hit_box[0], name)
            self.assertLessEqual(spec.pin[1], spec.hit_box[1], name)

    def test_largest_bubble_fits_hit_box(self):
        self.assertLessEqual(ms.BUBBLE_MAX_PX, ms.HIT_BOX_PX)

    def test_pin_anchor_is_bottom_center(self):
        self.assertEqual(ms.CCTV.anchor, (14, 32))
        self.assertEqual(ms.MY_LOCATION.anchor, (14, 28))


class HitBoxHtmlTests(unittest.TestCase):
    def test_default_width_and_center_alignment(self):
        html = ms.hit_box_html("<i>x</i>")
        self.assertIn("width: 28px", html)
        self.assertIn("align-items: center", html)
        self.assertIn("<i>x</i>", html)

    def test_bottom_alignment_uses_flex_end(self):
        html = ms.hit_box_html("<i>x</i>", align="bottom")
        self.assertIn("align-items: flex-end", html)


class StationDotHtmlTests(unittest.TestCase):
    def test_carries_class_size_style_and_inner(self):
        html = ms.station_dot_html(10, 20, "border: 0;", "<i>x</i>")
        self.assertIn('class="station-dot"', html)
        self.assertIn("width: 10px; height: 20px; border: 0;", html)
        self.assertIn("<i>x</i></div>", html)


if __name__ == "__main__":
    unittest.main()
