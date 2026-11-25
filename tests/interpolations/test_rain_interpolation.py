import json
import unittest
from pathlib import Path

import numpy
import shapely

from sindhu.services import interpolations

# Latest 24h rain from all sources on 2026-11-19, as [lon, lat, mm]. It holds
# gauges that both thaiwater_rain and rid report a few metres apart with
# different readings, which made kriging blow up into striped contours
SNAPSHOT_PATH = Path(__file__).with_name("rain_24h_2026-11-19.json")


def _snapshot_points():
    rows = numpy.array(json.loads(SNAPSHOT_PATH.read_text()), dtype=float)
    return rows[:, 0], rows[:, 1], rows[:, 2]


def _highest_band_start(geojson):
    return max(
        float(feature["properties"]["title"].split("-")[0])
        for feature in geojson["features"]
    )


class RainSurfaceStaysInMeasuredRangeTest(unittest.TestCase):
    def test_kriging_fits_a_snapshot_with_cross_source_twins(self):
        lons, lats, values = _snapshot_points()

        geojson, method = interpolations.interpolate_rain_contours(
            lons, lats, values, "ordinary"
        )

        self.assertEqual(method, "ordinary")
        self.assertLessEqual(_highest_band_start(geojson), values.max())

    def test_every_method_stays_in_range(self):
        lons, lats, values = _snapshot_points()

        for method in interpolations.METHODS:
            with self.subTest(method=method):
                geojson, _ = interpolations.interpolate_rain_contours(
                    lons, lats, values, method
                )
                self.assertLessEqual(_highest_band_start(geojson), values.max())


class RainSurfaceCoversSongkhlaTest(unittest.TestCase):
    def test_bands_fill_the_province_and_stay_on_land(self):
        lons, lats, values = _snapshot_points()

        geojson, _ = interpolations.interpolate_rain_contours(lons, lats, values)

        surface = shapely.union_all(
            [shapely.geometry.shape(f["geometry"]) for f in geojson["features"]]
        )
        province = interpolations.RAIN_AREA
        self.assertTrue(province.buffer(1e-4).contains(surface))
        self.assertGreater(surface.area / province.area, 0.99)

    def test_province_holds_hat_yai(self):
        district = shapely.geometry.shape(
            json.loads(
                (
                    Path(interpolations.__file__).parent.parent
                    / "web/static/resources/hatyai_boundary.geojson"
                ).read_text()
            )
        )
        self.assertTrue(interpolations.RAIN_AREA.buffer(2e-3).contains(district))


class MergeColocatedPointsTest(unittest.TestCase):
    def test_twins_become_one_point_at_their_mean(self):
        lons = numpy.array([100.5, 100.50001, 100.6])
        lats = numpy.array([7.0, 7.00001, 7.1])
        values = numpy.array([6.0, 0.0, 10.0])

        lons, lats, values = interpolations.merge_colocated_points(lons, lats, values)

        self.assertEqual(sorted(values.tolist()), [3.0, 10.0])
        self.assertEqual((lons.size, lats.size), (2, 2))

    def test_no_points(self):
        empty = numpy.array([])

        _, _, values = interpolations.merge_colocated_points(empty, empty, empty)

        self.assertEqual(values.size, 0)


if __name__ == "__main__":
    unittest.main()
