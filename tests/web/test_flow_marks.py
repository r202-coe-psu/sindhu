import json
import math
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


def _load_flow():
    if str(BRYTHON_ROOT) not in sys.path:
        sys.path.append(str(BRYTHON_ROOT))
    browser = types.ModuleType("browser")
    for name in ("aio", "ajax", "alert", "document", "html", "timer", "window"):
        setattr(browser, name, _BrowserStub())
    sys.modules.setdefault("browser", browser)
    from maps import flow

    return flow


flow = _load_flow()


def _gap(a, b):
    return math.hypot(b[0] - a[0], b[1] - a[1])


class ArrowMarksTests(unittest.TestCase):
    def test_marks_are_evenly_spaced_along_a_multi_segment_path(self):
        path = [(0, 500), (0, 0), (300, 0), (300, 240)]
        marks = flow.arrow_marks(path, 100)
        self.assertEqual(len(marks), 10)
        # Measure along the path, not the straight line, across the corners.
        along = [500 - y for x, y, _ in marks[:5]]
        along += [500 + x for x, y, _ in marks[5:8]]
        along += [800 + y for x, y, _ in marks[8:]]
        steps = [round(b - a, 6) for a, b in zip(along, along[1:])]
        self.assertEqual(set(steps), {100.0})

    def test_angle_follows_each_segment_direction(self):
        for end, expected in (
            ((0, -200), 0),
            ((200, 0), 90),
            ((0, 200), 180),
            ((-200, 0), 270),
        ):
            with self.subTest(expected=expected):
                marks = flow.arrow_marks([(0, 0), end], 100)
                self.assertEqual([round(a) for _, _, a in marks], [expected] * 2)

    def test_angle_changes_where_the_path_turns(self):
        marks = flow.arrow_marks([(0, 0), (200, 0), (200, 200)], 100)
        self.assertEqual([round(a) for _, _, a in marks], [90, 90, 180, 180])

    def test_path_shorter_than_spacing_yields_at_most_one_mark(self):
        for length in (1, 49, 50, 99):
            with self.subTest(length=length):
                marks = flow.arrow_marks([(0, 0), (length, 0)], 100)
                self.assertLessEqual(len(marks), 1)

    def test_degenerate_paths_yield_nothing(self):
        self.assertEqual(flow.arrow_marks([], 100), [])
        self.assertEqual(flow.arrow_marks([(5, 5)], 100), [])
        self.assertEqual(flow.arrow_marks([(5, 5), (5, 5)], 100), [])

    def test_repeated_vertices_do_not_add_marks(self):
        clean = flow.arrow_marks([(0, 0), (300, 0)], 100)
        repeated = flow.arrow_marks([(0, 0), (0, 0), (300, 0), (300, 0)], 100)
        self.assertEqual(repeated, clean)

    def test_two_ways_joined_end_to_end_never_crowd_their_join(self):
        first = flow.arrow_marks([(0, 0), (130, 0)], 100)
        second = flow.arrow_marks([(130, 0), (260, 0)], 100)
        self.assertGreaterEqual(_gap(first[-1], second[0]), 100)


class PinToEdgeTests(unittest.TestCase):
    def test_point_inside_the_margin_box_is_unchanged(self):
        self.assertEqual(flow.pin_to_edge(400, 300, 800, 600, 40), (400, 300, None))

    def test_point_on_the_margin_line_counts_as_inside(self):
        self.assertEqual(flow.pin_to_edge(40, 560, 800, 600, 40), (40, 560, None))

    def test_each_edge_clamps_to_the_margin_box(self):
        for point, expected in (
            ((400, -50), (400, 40, "top")),
            ((400, 900), (400, 560, "bottom")),
            ((-50, 300), (40, 300, "left")),
            ((1200, 300), (760, 300, "right")),
        ):
            with self.subTest(edge=expected[2]):
                self.assertEqual(flow.pin_to_edge(*point, 800, 600, 40), expected)

    def test_corner_point_takes_the_edge_it_overshoots_most(self):
        self.assertEqual(flow.pin_to_edge(-10, -300, 800, 600, 40), (40, 40, "top"))
        self.assertEqual(flow.pin_to_edge(-300, -10, 800, 600, 40), (40, 40, "left"))


class SpreadAlongEdgeTests(unittest.TestCase):
    def test_labels_pinned_to_one_spot_end_up_side_by_side_in_order(self):
        spread = flow.spread_along_edge([500, 500, 505], [100, 100, 100], 0, 1000)
        gaps = [b - a for a, b in zip(sorted(spread), sorted(spread)[1:])]
        self.assertTrue(all(gap >= 100 for gap in gaps))
        self.assertEqual(sorted(range(3), key=spread.__getitem__), [0, 1, 2])

    def test_labels_that_already_clear_each_other_do_not_move(self):
        self.assertEqual(
            flow.spread_along_edge([100, 400, 700], [100, 100, 100], 0, 1000),
            [100, 400, 700],
        )

    def test_a_crowd_against_the_far_end_is_pulled_back_inside(self):
        spread = flow.spread_along_edge([990, 990, 990], [100, 100, 100], 0, 1000)
        self.assertEqual(spread, [750, 850, 950])

    def test_a_crowd_against_the_near_end_is_pushed_inside(self):
        spread = flow.spread_along_edge([0, 0, 0], [100, 100, 100], 0, 1000)
        self.assertEqual(spread, [50, 150, 250])

    def test_input_order_is_kept_in_the_output(self):
        spread = flow.spread_along_edge([700, 100], [100, 100], 0, 1000)
        self.assertEqual(spread, [700, 100])


class ScreenBearingTests(unittest.TestCase):
    def test_cardinal_directions_are_clockwise_from_north(self):
        for target, expected in (
            ((0, -10), 0),
            ((10, 0), 90),
            ((0, 10), 180),
            ((-10, 0), 270),
            ((10, -10), 45),
        ):
            with self.subTest(expected=expected):
                self.assertAlmostEqual(
                    flow.screen_bearing(0, 0, *target), expected, places=6
                )

    def test_bearing_is_measured_from_the_start_point(self):
        self.assertAlmostEqual(flow.screen_bearing(100, 100, 100, 50), 0, places=6)
        self.assertAlmostEqual(flow.screen_bearing(100, 100, 50, 100), 270, places=6)


class SourceArrowPlacementTests(unittest.TestCase):
    def test_arrow_sits_on_the_side_the_water_comes_from(self):
        for angle, expected in ((0, (0, 10)), (90, (-10, 0)), (180, (0, -10))):
            dx, dy = flow.upstream_offset(angle, 10)
            self.assertAlmostEqual(dx, expected[0], places=6, msg=angle)
            self.assertAlmostEqual(dy, expected[1], places=6, msg=angle)

    def test_box_reach_is_half_the_side_the_heading_crosses(self):
        self.assertAlmostEqual(flow.box_reach(200, 60, 0), 30)
        self.assertAlmostEqual(flow.box_reach(200, 60, 90), 100)

    def test_box_reach_on_a_diagonal_stops_at_the_nearer_side(self):
        self.assertAlmostEqual(flow.box_reach(200, 60, 45), 30 * math.sqrt(2))


class WaterwayStyleTests(unittest.TestCase):
    def test_every_class_is_blue_and_thicker_for_bigger_waterways(self):
        styles = {
            fclass: flow.waterway_style(fclass, (), None)
            for fclass in ("river", "canal", "stream", "drain")
        }
        self.assertEqual({s["color"] for s in styles.values()}, {flow.WATERWAY_COLOR})
        weights = [styles[c]["weight"] for c in ("river", "canal", "stream", "drain")]
        self.assertEqual(weights, sorted(weights, reverse=True))
        self.assertGreater(weights[1], weights[2])

    def test_an_unknown_class_is_drawn_like_a_stream(self):
        self.assertEqual(
            flow.waterway_style("ditch", (), None),
            flow.waterway_style("stream", (), None),
        )

    def test_a_corridor_line_looks_like_any_other_line_until_selected(self):
        for system in flow.CORRIDORS:
            for selected in (None, *(set(flow.CORRIDORS) - {system})):
                with self.subTest(system=system, selected=selected):
                    self.assertEqual(
                        flow.waterway_style("canal", (system,), selected),
                        flow.waterway_style("canal", (), selected),
                    )

    def test_the_selected_system_takes_its_colour_and_a_heavier_line(self):
        for system, info in flow.CORRIDORS.items():
            for fclass in ("river", "canal", "stream", "drain"):
                with self.subTest(system=system, fclass=fclass):
                    base = flow.waterway_style(fclass, (), system)
                    picked = flow.waterway_style(fclass, (system,), system)
                    self.assertEqual(picked["color"], info["color"])
                    self.assertGreater(picked["weight"], base["weight"])

    def test_a_line_in_two_systems_lights_up_for_either(self):
        for selected in ("khuanlang", "lake"):
            with self.subTest(selected=selected):
                style = flow.waterway_style("canal", ("khuanlang", "lake"), selected)
                self.assertEqual(style["color"], flow.CORRIDORS[selected]["color"])

    def test_arrows_are_blue_until_their_system_is_selected(self):
        self.assertEqual(flow.arrow_color(("khohong",), None), flow.WATERWAY_COLOR)
        self.assertEqual(flow.arrow_color(("khohong",), "utapao"), flow.WATERWAY_COLOR)
        self.assertEqual(
            flow.arrow_color(("khohong",), "khohong"),
            flow.CORRIDORS["khohong"]["color"],
        )

    def test_the_base_blue_is_not_any_system_colour(self):
        self.assertNotIn(
            flow.WATERWAY_COLOR, [info["color"] for info in flow.CORRIDORS.values()]
        )


class SystemColourTests(unittest.TestCase):
    WATER_LEVEL_HUES = ((0, 65), (75, 165), (340, 360))

    def test_no_system_colour_uses_a_water_level_hue(self):
        import colorsys

        for system, info in flow.CORRIDORS.items():
            r, g, b = (int(info["color"][i : i + 2], 16) / 255 for i in (1, 3, 5))
            hue = colorsys.rgb_to_hls(r, g, b)[0] * 360
            with self.subTest(system=system, hue=round(hue)):
                self.assertFalse(
                    any(low <= hue <= high for low, high in self.WATER_LEVEL_HUES)
                )


class SystemFitTests(unittest.TestCase):
    def test_a_system_that_fits_at_this_zoom_or_closer_is_fitted(self):
        self.assertTrue(flow.fits_without_zooming_out(13, 12))
        self.assertTrue(flow.fits_without_zooming_out(12, 12))

    def test_a_system_bigger_than_the_view_is_not_fitted(self):
        self.assertFalse(flow.fits_without_zooming_out(9, 11))


class FlowDataTests(unittest.TestCase):
    def test_every_corridor_has_a_thai_name_and_a_colour_readable_under_white_text(
        self,
    ):
        def luminance(colour):
            channels = []
            for i in (1, 3, 5):
                c = int(colour[i : i + 2], 16) / 255
                channels.append(
                    c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
                )
            return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]

        data = json.loads(
            (BRYTHON_ROOT.parent / "resources" / "hatyai_waterways.geojson").read_text(
                encoding="utf-8"
            )
        )
        drawn = {
            system
            for f in data["features"]
            for system in f["properties"].get("systems", [])
        }
        self.assertEqual(set(flow.CORRIDORS), drawn)
        for corridor, info in flow.CORRIDORS.items():
            with self.subTest(corridor=corridor):
                self.assertTrue(info["name"])
                self.assertGreaterEqual(1.05 / (luminance(info["color"]) + 0.05), 4.5)
        colours = [info["color"] for info in flow.CORRIDORS.values()]
        self.assertEqual(len(set(colours)), len(colours))

    def test_each_source_selects_its_own_system(self):
        systems = {s["id"]: s["system"] for s in flow.FLOW_SOURCES}
        self.assertEqual(
            systems,
            {
                "sadao": "utapao",
                "khuanlang": "khuanlang",
                "khohong": "khohong",
                "lake": "lake",
            },
        )
        for source in flow.FLOW_SOURCES:
            if source["system"]:
                self.assertEqual(
                    source["color"], flow.CORRIDORS[source["system"]]["color"]
                )

    def test_sources_are_readable_under_white_text_and_point_at_a_destination(self):
        self.assertEqual(
            [s["id"] for s in flow.FLOW_SOURCES],
            ["sadao", "khuanlang", "khohong", "lake"],
        )
        for source in flow.FLOW_SOURCES:
            with self.subTest(source=source["id"]):
                self.assertGreater(source["dest_lat"], source["lat"] - 0.2)
                self.assertNotEqual(
                    (source["lat"], source["lng"]),
                    (source["dest_lat"], source["dest_lng"]),
                )


if __name__ == "__main__":
    unittest.main()
