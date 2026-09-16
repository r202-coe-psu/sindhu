import datetime
import json
import pathlib

import geojsoncontour
import numpy
import shapely
from loguru import logger
from matplotlib.figure import Figure

from sindhu.services import metrics

# Metric parameters that carry rainfall in mm. Only the DWR rainfall ETL writes
# "rain" today; add other sources' parameter names here once they are ingested
RAIN_PARAMETERS = ["rain"]

# Band edges and colors mirror the "rain" legend in
# sindhu/web/static/brython/stations/metric_infos.py
RAIN_LEVELS = [0, 10, 30, 50, 100]
RAIN_COLORS = ["#cce5ff", "#66b2ff", "#0073e6", "#004080", "#800080"]

GRID_STEP_DEG = 0.005  # ~500 m
IDW_POWER = 2
MIN_POINTS = 3

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


def rain_band_label(title):
    low, high = title.strip().split("-")
    if float(low) >= RAIN_LEVELS[-1]:
        return f"ฝน > {RAIN_LEVELS[-1]} มม."
    return f"ฝน {float(low):g}-{float(high):g} มม."


def interpolate_rain_contours(lons, lats, values):
    xmin, ymin, xmax, ymax = BASIN_AREA.bounds
    xi, yi = numpy.meshgrid(
        numpy.arange(xmin, xmax + GRID_STEP_DEG, GRID_STEP_DEG),
        numpy.arange(ymin, ymax + GRID_STEP_DEG, GRID_STEP_DEG),
    )

    zi = idw_grid(lons, lats, values, xi, yi)
    zi[~shapely.contains_xy(BASIN_AREA, xi, yi)] = numpy.nan

    # contourf needs a finite top edge for the open-ended "> 100 mm" band
    top = max(RAIN_LEVELS[-1], float(numpy.nanmax(zi))) + 1
    levels = RAIN_LEVELS + [top]

    # A private Figure instead of pyplot keeps concurrent requests apart
    ax = Figure().add_subplot()
    contours = ax.contourf(
        xi, yi, numpy.ma.masked_invalid(zi), levels=levels, colors=RAIN_COLORS
    )
    geojson = json.loads(
        geojsoncontour.contourf_to_geojson(
            contourf=contours, ndigits=5, stroke_width=0, fill_opacity=0.5
        )
    )

    for feature in geojson["features"]:
        properties = feature["properties"]
        properties["DES_TH"] = rain_band_label(properties.get("title", "0-0"))

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


async def get_rain_interpolation(source=None):
    lons, lats, values = await get_rain_points(source)

    result = {
        "interpolation": None,
        "points": int(values.size),
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }

    if values.size < MIN_POINTS:
        logger.warning(
            f"[interpolations] Only {values.size} rain stations, need {MIN_POINTS}. Skipping."
        )
        return result

    result["interpolation"] = interpolate_rain_contours(lons, lats, values)
    return result
