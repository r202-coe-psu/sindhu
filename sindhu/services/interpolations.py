import datetime
import json
import pathlib

import geojsoncontour
import numpy
import shapely
from loguru import logger
from geokrige.methods import OrdinaryKriging, SimpleKriging
from matplotlib.figure import Figure
from scipy.interpolate import griddata

from sindhu.services import metrics

# Metric parameters that carry rainfall in mm. Only the DWR rainfall ETL writes
# "rain" today; add other sources' parameter names here once they are ingested
RAIN_PARAMETERS = ["rain"]

# Fixed mm -> color bands, so the same color always means the same rainfall.
# Band edges and colors follow the ECMWF "Precipitation, 24h" scale: the steps
# are fine for light rain and coarse for extremes, so they are not linear
RAIN_LEVELS = [
    0, 0.1, 0.5, 1, 2, 3, 5, 7, 10, 15, 20, 25, 30, 35, 40,
    45, 50, 60, 70, 80, 90, 100, 125, 150, 200, 300,
]
RAIN_BAND_COLORS = [
    "#f7fbff", "#e0f0ff", "#c2e2ff", "#9ed3ff", "#6cbcff",
    "#3aa3ff", "#1a7fd4", "#0a5aa8", "#0f7a34", "#22a145",
    "#63c73f", "#c2e03a", "#ffe32e", "#ffc51c", "#ffa015",
    "#ff7a12", "#f5400f", "#d21810", "#ac0913", "#870018",
    "#6b0020", "#8f1f8f", "#bd3fbd", "#d982d9", "#f0c4f0",
]
RAIN_UPPER_BOUND = RAIN_LEVELS[-1]
# Labels to print under the legend bar; the rest of the edges stay unlabeled
RAIN_LEGEND_TICKS = [1, 5, 10, 20, 50, 100, 300]

# Dry ground stays readable under a near-transparent band; heavy rain covers it
RAIN_MIN_FILL_OPACITY = 0.15
RAIN_MAX_FILL_OPACITY = 0.75
RAIN_FULL_OPACITY_AT = 50

GRID_STEP_DEG = 0.005  # ~500 m
IDW_POWER = 1
MIN_POINTS = 3

# "cubic" can overshoot past the measured range, so it is not the default
METHODS = ["idw", "nearest", "cubic", "ordinary", "simple"]
DEFAULT_METHOD = "ordinary"
VARIOGRAM_BINS = 2
VARIOGRAM_MODEL = "exp"

BASINS_GEOJSON_PATH = (
    pathlib.Path(__file__).resolve().parent.parent
    / "web"
    / "static"
    / "resources"
    / "songkhla_basins.geojson"
)


def load_basin_area():
    """Build the interpolation area from the Songkhla river network.

    The basin file only has river and canal lines, so the area is a concave
    hull around them, padded a little so edge stations still get coverage
    """
    with BASINS_GEOJSON_PATH.open("r", encoding="utf-8") as f:
        geojson = json.load(f)

    lines = shapely.GeometryCollection(
        [shapely.geometry.shape(feature["geometry"]) for feature in geojson["features"]]
    )
    area = shapely.concave_hull(lines, ratio=0.3).buffer(0.01)
    shapely.prepare(area)
    return area


BASIN_AREA = load_basin_area()


def idw_grid(lons, lats, values, xi, yi, power=IDW_POWER):
    """Inverse Distance Weighting of station values onto the grid points."""
    dx = xi.ravel()[:, None] - lons[None, :]
    dy = yi.ravel()[:, None] - lats[None, :]
    distances = numpy.hypot(dx, dy)

    exact = distances == 0
    with numpy.errstate(divide="ignore"):
        weights = 1.0 / distances**power
    # A grid point sitting on a station takes that station's value as is
    weights[exact.any(axis=1)] = exact[exact.any(axis=1)]

    zi = (weights @ values) / weights.sum(axis=1)
    return zi.reshape(xi.shape)


def rain_legend():
    """Legend bands are drawn at equal width, like the ECMWF scale, because the
    mm steps they stand for are not evenly spaced."""
    band_count = len(RAIN_BAND_COLORS)
    return {
        "title": "ปริมาณฝนสะสม 24 ชม.",
        "unit": "มม.",
        "bands": [
            {"color": color, "from": RAIN_LEVELS[index], "to": RAIN_LEVELS[index + 1]}
            for index, color in enumerate(RAIN_BAND_COLORS)
        ],
        "ticks": [
            {"value": value, "offset": RAIN_LEVELS.index(value) / band_count}
            for value in RAIN_LEGEND_TICKS
        ],
    }


def kriging_grid(lons, lats, values, xi, yi, method):
    """Statistical interpolation: a variogram sets the weights by distance."""
    kriging = OrdinaryKriging() if method == "ordinary" else SimpleKriging()
    kriging.load(numpy.column_stack([lons, lats]), values)
    kriging.variogram(bins=VARIOGRAM_BINS, plot=False)
    kriging.fit(model=VARIOGRAM_MODEL, plot=False, range_param=1)
    return kriging.predict([xi, yi])


def estimate_rain_grid(lons, lats, values, xi, yi, method):
    if method in ("ordinary", "simple"):
        return kriging_grid(lons, lats, values, xi, yi, method)
    if method in ("nearest", "cubic"):
        return griddata((lons, lats), values, (xi, yi), method=method)
    return idw_grid(lons, lats, values, xi, yi)


def interpolate_rain_contours(lons, lats, values, method=DEFAULT_METHOD):
    xmin, ymin, xmax, ymax = BASIN_AREA.bounds
    xi, yi = numpy.meshgrid(
        numpy.arange(xmin, xmax + GRID_STEP_DEG, GRID_STEP_DEG),
        numpy.arange(ymin, ymax + GRID_STEP_DEG, GRID_STEP_DEG),
    )

    zi = estimate_rain_grid(lons, lats, values, xi, yi, method)
    zi[~shapely.contains_xy(BASIN_AREA, xi, yi)] = numpy.nan
    # Rain above the scale shares the top color instead of falling off the levels
    zi = numpy.clip(zi, 0, RAIN_UPPER_BOUND)

    # A private Figure instead of pyplot keeps concurrent requests apart
    ax = Figure().add_subplot()
    contours = ax.contourf(
        xi, yi, numpy.ma.masked_invalid(zi), levels=RAIN_LEVELS, colors=RAIN_BAND_COLORS
    )
    geojson = json.loads(
        geojsoncontour.contourf_to_geojson(
            contourf=contours, ndigits=5, stroke_width=0, fill_opacity=0.5
        )
    )

    for feature in geojson["features"]:
        properties = feature["properties"]
        band_start = float(properties["title"].split("-")[0])
        ramp = min(band_start / RAIN_FULL_OPACITY_AT, 1.0)
        properties["fill-opacity"] = round(
            RAIN_MIN_FILL_OPACITY
            + (RAIN_MAX_FILL_OPACITY - RAIN_MIN_FILL_OPACITY) * ramp,
            3,
        )

    return geojson


async def get_rain_points(source=None):
    lons, lats, values = [], [], []
    for parameter in RAIN_PARAMETERS:
        stations = await metrics.get_latest_metrics_by_metric_type(
            parameter, source=source
        )
        for station in stations:
            coordinates = (station.get("coordinates") or {}).get("coordinates")
            station_metrics = station.get("metrics") or []
            if not coordinates or not station_metrics:
                continue

            value = station_metrics[0].get("value")
            if value is None or value < 0:
                continue

            lons.append(coordinates[0])
            lats.append(coordinates[1])
            values.append(value)

    return numpy.array(lons), numpy.array(lats), numpy.array(values, dtype=float)


async def get_rain_interpolation(source=None, method=DEFAULT_METHOD):
    if method not in METHODS:
        method = DEFAULT_METHOD

    lons, lats, values = await get_rain_points(source)

    result = {
        "interpolation": None,
        "points": int(values.size),
        "method": method,
        "legend": rain_legend(),
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }

    if values.size < MIN_POINTS:
        logger.warning(
            f"[interpolations] Only {values.size} rain stations, need {MIN_POINTS}. Skipping."
        )
        return result

    result["interpolation"] = interpolate_rain_contours(lons, lats, values, method)
    return result
