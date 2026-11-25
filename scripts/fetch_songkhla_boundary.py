"""Fetch the land outline of Songkhla province for the rain surface.

OSM's province relation reaches far into the Gulf of Thailand (territorial
sea), so the outline starts from the union of the province's district
relations. Those still stray up to a few kilometres offshore around the mouth
of Songkhla Lake, so the result is cut along OSM's coastline as well.

    python scripts/fetch_songkhla_boundary.py
"""

import json
import pathlib
import urllib.parse
import urllib.request

import shapely
from shapely.ops import polygonize, split

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUTPUT = (
    ROOT / "sindhu" / "web" / "static" / "resources" / "songkhla_boundary.geojson"
)
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
SONGKHLA_RELATION_ID = 1908822
SIMPLIFY_DEG = 0.0001  # ~10 m, so the edge still sits on the shore when zoomed in
# south, west, north, east; wide enough to hold the province's whole coast
COAST_BBOX = (6.2, 100.0, 8.0, 101.2)
SIDE_PROBE_DEG = 1e-6
QUERY = (
    "[out:json][timeout:120];"
    f"rel({SONGKHLA_RELATION_ID});map_to_area->.province;"
    'rel(area.province)["boundary"="administrative"]["admin_level"="6"];'
    "out geom;"
    f"rel({SONGKHLA_RELATION_ID});out geom;"
    'way["natural"="coastline"]({},{},{},{});out geom;'.format(*COAST_BBOX)
)


def relation_polygon(relation):
    outers = [
        shapely.LineString([(p["lon"], p["lat"]) for p in member["geometry"]])
        for member in relation["members"]
        if member["type"] == "way" and member.get("role") == "outer"
    ]
    return shapely.union_all(list(polygonize(shapely.union_all(outers))))


def land_polygon(coastlines):
    """OSM draws coastlines with the land on their left. Cut the bbox along
    them and keep the pieces that the left-hand probes land in."""
    south, west, north, east = COAST_BBOX
    pieces = split(shapely.box(west, south, east, north), shapely.union_all(coastlines))
    left, right = [], []
    for line in coastlines:
        (x0, y0), (x1, y1) = line.coords[0], line.coords[1]
        mx, my = (x0 + x1) / 2, (y0 + y1) / 2
        length = ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5
        nx, ny = -(y1 - y0) / length, (x1 - x0) / length
        left.append(shapely.Point(mx + nx * SIDE_PROBE_DEG, my + ny * SIDE_PROBE_DEG))
        right.append(shapely.Point(mx - nx * SIDE_PROBE_DEG, my - ny * SIDE_PROBE_DEG))
    return shapely.union_all(
        [
            piece
            for piece in pieces.geoms
            if sum(piece.contains(p) for p in left)
            > sum(piece.contains(p) for p in right)
        ]
    )


def main():
    request = urllib.request.Request(
        OVERPASS_URL,
        data=urllib.parse.urlencode({"data": QUERY}).encode(),
        headers={"User-Agent": "osm-boundary-fetch/1.0"},
    )
    with urllib.request.urlopen(request, timeout=180) as response:
        elements = json.load(response)["elements"]
    relations = [e for e in elements if e["type"] == "relation"]
    coastlines = [
        shapely.LineString([(p["lon"], p["lat"]) for p in e["geometry"]])
        for e in elements
        if e["type"] == "way"
    ]

    province = next(r for r in relations if r["id"] == SONGKHLA_RELATION_ID)
    province_area = relation_polygon(province)
    # The area query also returns neighbouring districts that touch the border
    districts = [
        polygon
        for polygon in (
            relation_polygon(r)
            for r in relations
            if r["tags"].get("admin_level") == "6"
        )
        if province_area.contains(polygon.representative_point())
    ]
    land = shapely.intersection(shapely.union_all(districts), land_polygon(coastlines))
    land = land.simplify(SIMPLIFY_DEG)
    land = shapely.set_precision(land, 1e-5)

    OUTPUT.write_text(
        json.dumps(shapely.geometry.mapping(land), separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {len(districts)} districts to {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
