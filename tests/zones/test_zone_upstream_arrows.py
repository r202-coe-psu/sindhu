import json
import sys
import unittest
from pathlib import Path
from unittest import mock

from .test_zone_upstream_map import (
    BRYTHON_ROOT,
    Map,
    _Container,
    _Document,
    _Layer,
    _LeafletMap,
)

if str(BRYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(BRYTHON_ROOT))

from maps.zone_flow import (  # noqa: E402
    ring_centroid,
    shared_border_anchor,
    upstream_arrow,
    zone_rings,
)

DEV_ZONES = Path(__file__).with_name("dev_zones.json")


def square(west, south, east, north):
    return [[west, south], [east, south], [east, north], [west, north], [west, south]]


def polygon(*rings):
    return {"type": "Polygon", "coordinates": list(rings)}


class ZoneRingsTests(unittest.TestCase):
    def test_polygon_gives_its_outer_ring(self):
        outer = square(0, 0, 1, 1)
        hole = square(0.2, 0.2, 0.4, 0.4)

        self.assertEqual(zone_rings(polygon(outer, hole)), [outer])

    def test_multipolygon_gives_every_outer_ring(self):
        first, second = square(0, 0, 1, 1), square(2, 0, 3, 1)
        boundary = {
            "type": "MultiPolygon",
            "coordinates": [[first], [second, square(2.2, 0.2, 2.4, 0.4)]],
        }

        self.assertEqual(zone_rings(boundary), [first, second])

    def test_feature_and_feature_collection_are_unwrapped(self):
        ring = square(0, 0, 1, 1)
        feature = {"type": "Feature", "geometry": polygon(ring)}

        self.assertEqual(zone_rings(feature), [ring])
        self.assertEqual(
            zone_rings({"type": "FeatureCollection", "features": [feature, feature]}),
            [ring, ring],
        )

    def test_missing_or_unknown_boundary_has_no_rings(self):
        self.assertEqual(zone_rings(None), [])
        self.assertEqual(zone_rings({"type": "Point", "coordinates": [0, 0]}), [])


class RingCentroidTests(unittest.TestCase):
    def test_square_centroid_is_its_centre(self):
        self.assertEqual(ring_centroid(square(0, 0, 2, 4)), (1, 2))

    def test_centroid_is_area_weighted_not_a_vertex_average(self):
        # Many vertices crowd the left edge; the centroid stays at the middle.
        ring = [[0, 0], [2, 0], [2, 2], [0, 2]] + [[0, 1.9 - i * 0.1] for i in range(5)]
        self.assertAlmostEqual(ring_centroid(ring)[0], 1, places=6)

    def test_winding_direction_does_not_matter(self):
        self.assertEqual(
            ring_centroid(square(0, 0, 2, 4)),
            ring_centroid(list(reversed(square(0, 0, 2, 4)))),
        )


class SharedBorderAnchorTests(unittest.TestCase):
    def test_anchor_is_the_middle_of_a_shared_edge(self):
        south = [square(0, 0, 4, 1)]
        north = [square(0, 1, 4, 2)]

        lng, lat = shared_border_anchor(south, north, 0.01)

        self.assertAlmostEqual(lng, 2, places=6)
        self.assertAlmostEqual(lat, 1, places=6)

    def test_anchor_is_the_middle_of_the_longest_shared_run(self):
        tall = [square(0, 0, 1, 10)]
        # Touches the tall zone along x=1 for y in 2..8 only.
        neighbour = [[[1, 2], [3, 2], [3, 8], [1, 8], [1, 2]]]

        lng, lat = shared_border_anchor(tall, neighbour, 0.01)

        self.assertAlmostEqual(lng, 1, places=6)
        self.assertAlmostEqual(lat, 5, places=6)

    def test_borders_a_few_metres_apart_still_count_as_shared(self):
        south = [square(0, 0, 4, 1)]
        north = [square(0, 1.0004, 4, 2)]

        self.assertIsNotNone(shared_border_anchor(south, north, 0.002))

    def test_distant_zones_share_no_border(self):
        self.assertIsNone(
            shared_border_anchor([square(0, 0, 1, 1)], [square(5, 5, 6, 6)], 0.01)
        )

    def test_anchor_is_found_whichever_zone_has_the_extra_vertices(self):
        coarse = [square(0, 0, 4, 1)]
        dense = [
            [[0, 1], [1, 1], [2, 1], [3, 1], [4, 1], [4, 2], [0, 2], [0, 1]],
        ]

        forward = shared_border_anchor(coarse, dense, 0.01)
        backward = shared_border_anchor(dense, coarse, 0.01)

        for anchor in (forward, backward):
            self.assertAlmostEqual(anchor[0], 2, places=6)
            self.assertAlmostEqual(anchor[1], 1, places=6)


class UpstreamArrowTests(unittest.TestCase):
    def arrow(self, upstream, selected):
        return upstream_arrow([upstream], [selected])

    def test_south_upstream_points_north_from_the_shared_edge(self):
        arrow = self.arrow(square(0, 0, 4, 1), square(0, 1, 4, 2))

        self.assertAlmostEqual(arrow["angle"], 0, places=3)
        self.assertAlmostEqual(arrow["lng"], 2, places=6)
        self.assertAlmostEqual(arrow["lat"], 1, places=6)

    def test_west_upstream_points_east(self):
        arrow = self.arrow(square(0, 0, 1, 4), square(1, 0, 2, 4))

        self.assertAlmostEqual(arrow["angle"], 90, places=3)
        self.assertAlmostEqual(arrow["lng"], 1, places=6)
        self.assertAlmostEqual(arrow["lat"], 2, places=6)

    def test_north_and_east_upstream_point_south_and_west(self):
        self.assertAlmostEqual(
            self.arrow(square(0, 1, 4, 2), square(0, 0, 4, 1))["angle"], 180, places=3
        )
        self.assertAlmostEqual(
            self.arrow(square(1, 0, 2, 4), square(0, 0, 1, 4))["angle"], 270, places=3
        )

    def test_zones_that_do_not_touch_use_the_midpoint_of_their_centroids(self):
        arrow = self.arrow(square(0, 0, 2, 2), square(10, 0, 12, 2))

        self.assertAlmostEqual(arrow["lng"], 6, places=6)
        self.assertAlmostEqual(arrow["lat"], 1, places=6)
        self.assertAlmostEqual(arrow["angle"], 90, places=3)

    def test_multipolygon_zone_uses_the_combined_area(self):
        upstream = zone_rings(
            {
                "type": "MultiPolygon",
                "coordinates": [[square(0, 0, 1, 1)], [square(0, 1, 1, 2)]],
            }
        )
        selected = zone_rings(
            {"type": "Feature", "geometry": polygon(square(1, 0, 2, 2))}
        )

        arrow = upstream_arrow(upstream, selected)

        self.assertAlmostEqual(arrow["angle"], 90, places=3)
        self.assertAlmostEqual(arrow["lng"], 1, places=6)
        self.assertAlmostEqual(arrow["lat"], 1, places=6)


class DevZonesTests(unittest.TestCase):
    """Real zones from the dev API: Zone 3 sits north of Zone 1 and east of Zone 2."""

    @classmethod
    def setUpClass(cls):
        zones = json.loads(DEV_ZONES.read_text())
        cls.rings = {
            zone["name"].split(" - ")[0]: zone_rings(zone["boundary"]) for zone in zones
        }

    def angle(self, upstream, selected):
        return upstream_arrow(self.rings[upstream], self.rings[selected])["angle"]

    def assertBearing(self, angle, expected, spread=25):
        offset = (angle - expected + 180) % 360 - 180
        self.assertLess(abs(offset), spread, f"{angle:.1f} is not near {expected}")

    def test_zone_1_flows_north_into_zone_3(self):
        self.assertBearing(self.angle("Zone 1", "Zone 3"), 0)

    def test_zone_2_flows_east_into_zone_3(self):
        self.assertBearing(self.angle("Zone 2", "Zone 3"), 90, spread=30)

    def test_zone_3_flows_north_into_zone_4(self):
        self.assertBearing(self.angle("Zone 3", "Zone 4"), 0)

    def test_arrows_sit_on_the_border_of_the_selected_zone(self):
        for upstream, selected in (("Zone 1", "Zone 3"), ("Zone 2", "Zone 3")):
            arrow = upstream_arrow(self.rings[upstream], self.rings[selected])
            anchor = shared_border_anchor(
                self.rings[upstream], self.rings[selected], 0.002
            )
            self.assertEqual((arrow["lng"], arrow["lat"]), anchor)


class _DrawnMap(_LeafletMap):
    def hasLayer(self, layer):
        return False


class _FakeMarker:
    def __init__(self, latlng, options):
        self.latlng = latlng
        self.options = options


class _FakeLayerGroup:
    def __init__(self):
        self.layers = []

    def addLayer(self, layer):
        self.layers.append(layer)

    def clearLayers(self):
        self.layers = []


class _FakeLeaflet:
    def divIcon(self, options):
        return options

    def marker(self, latlng, options):
        return _FakeMarker(latlng, options)


def zone(zone_id, boundary, upstream=()):
    return {
        "id": zone_id,
        "name": zone_id,
        "boundary": boundary,
        "upstream_zone_ids": list(upstream),
    }


ARROW_ZONES = [
    zone("south", polygon(square(0, 0, 4, 1))),
    zone("west", polygon(square(-4, 1, 0, 2))),
    zone("middle", polygon(square(0, 1, 4, 2)), upstream=["south", "west"]),
    zone("north", polygon(square(0, 2, 4, 3)), upstream=["middle"]),
    zone("hidden-upstream", polygon(square(0, 3, 4, 4)), upstream=["not-drawn"]),
]


class ZoneUpstreamArrowMapTests(unittest.TestCase):
    def setUp(self):
        self.container = _Container()
        self.arrows = _FakeLayerGroup()
        self.map_view = Map.__new__(Map)
        self.map_view.map = _DrawnMap(self.container)
        self.map_view.leaflet = _FakeLeaflet()
        self.map_view._zone_arrow_layer = self.arrows
        self.map_view.zone_layers_by_id = {
            item["id"]: {"layer": _Layer(), "zone": item, "risk": None, "style": {}}
            for item in ARROW_ZONES
        }
        self.map_view._selected_zone_id = None
        self.map_view._reset_btn_container = None

        patcher = mock.patch.object(sys.modules["browser"], "document", _Document())
        patcher.start()
        self.addCleanup(patcher.stop)

    def faded(self):
        return self.container.classList.contains("flow-faded")

    def test_each_drawn_upstream_zone_gets_one_arrow(self):
        self.map_view.select_zone("middle", fit_bounds=False)

        self.assertEqual(len(self.arrows.layers), 2)

    def test_arrows_are_non_interactive_markers(self):
        self.map_view.select_zone("middle", fit_bounds=False)

        for arrow in self.arrows.layers:
            self.assertFalse(arrow.options["interactive"])
            self.assertFalse(arrow.options["keyboard"])

    def test_arrows_point_into_the_selected_zone_from_the_shared_border(self):
        self.map_view.select_zone("middle", fit_bounds=False)

        placed = {
            (round(arrow.latlng[0], 3), round(arrow.latlng[1], 3))
            for arrow in self.arrows.layers
        }
        self.assertEqual(placed, {(1.0, 2.0), (1.5, 0.0)})
        html = "".join(arrow.options["icon"]["html"] for arrow in self.arrows.layers)
        self.assertIn("rotate(0.0deg)", html)
        self.assertIn("rotate(90.0deg)", html)

    def test_zone_without_upstream_has_no_arrows(self):
        self.map_view.select_zone("south", fit_bounds=False)

        self.assertEqual(self.arrows.layers, [])

    def test_upstream_zone_that_is_not_drawn_has_no_arrow(self):
        self.map_view.select_zone("hidden-upstream", fit_bounds=False)

        self.assertEqual(self.arrows.layers, [])

    def test_selecting_another_zone_replaces_the_arrows(self):
        self.map_view.select_zone("middle", fit_bounds=False)
        self.map_view.select_zone("north", fit_bounds=False)

        self.assertEqual(len(self.arrows.layers), 1)

    def test_clearing_selection_removes_arrows_and_restores_flow_labels(self):
        self.map_view.select_zone("middle", fit_bounds=False)

        self.map_view.clear_zone_selection()

        self.assertEqual(self.arrows.layers, [])
        self.assertFalse(self.faded())

    def test_clearing_all_zones_removes_arrows_and_restores_flow_labels(self):
        self.map_view.select_zone("middle", fit_bounds=False)

        self.map_view.clear_all_zones()

        self.assertEqual(self.arrows.layers, [])
        self.assertFalse(self.faded())

    def test_flow_labels_fade_while_any_zone_is_selected(self):
        self.map_view.select_zone("south", fit_bounds=False)
        self.assertTrue(self.faded())

        self.map_view.select_zone("middle", fit_bounds=False)
        self.assertTrue(self.faded())


if __name__ == "__main__":
    unittest.main()
