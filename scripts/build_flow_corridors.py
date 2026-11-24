"""Build the Songkhla waterway network drawn on the map.

The sources are OSM waterway exports, merged by osm_id (the first source
wins).  scripts/fetch_osm_waterways.py refreshes the second one.  OSM draws a
waterway in the direction the water flows, so the vertex order of each line is
its flow direction.

Every line is written simplified, with its fclass.  The lines listed in
CORRIDOR_LINES also carry the drainage systems they belong to as ``systems``
(a line can feed one system and be another's outlet): the map draws direction
arrows on them and highlights a system when its label is picked.

    python scripts/build_flow_corridors.py
"""

import json
import math
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCES = [
    ROOT / "fixtures" / "waterways" / "songkhla_waterways_osm.geojson",
    ROOT / "fixtures" / "waterways" / "songkhla_south_osm.geojson",
]
OUTPUT = ROOT / "sindhu" / "web" / "static" / "resources" / "hatyai_waterways.geojson"
# About 9 m: below a pixel at city zoom.
SIMPLIFY_TOLERANCE_DEG = 0.00008
COORD_DECIMALS = 5

# One drainage system per "water comes from" label on the map: Sadao water
# runs down Khlong U-Taphao; Khuan Lang water runs down Khlong Wat into the
# Khlong R.1 bypass; Kho Hong water runs down Khlong Rian and the R.3-R.6
# canals into Khlong Toei.
CORRIDOR_LINES = {
    "utapao": [
        # Upstream main stem towards Sadao, traced from the U-Taphao head.
        "128549054",
        "244973765",
        "1055050832",
        "1051632070",
        "219800884",
        "321674114",
        "453743011",
        "453743013",
        "502095132",
        "502095133",
        "878600518",
        "1504011383",
        "1504011384",
    ],
    "khuanlang": ["154729158", "125942385"],
    "khohong": [
        "127078194",
        "127078223",
        "127078306",
        "243187986",
        "243187987",
        "243314049",
        "243314054",
        "243314055",
        "243314057",
        "1453266366",
        "1453266367",
        "1453266368",
        "1453266369",
        "1453266370",
        "155690223",
        "155690226",
        "155690230",
        "155690251",
        "155690256",
        "155690262",
        "243187985",
        "243187989",
        "243314048",
        "243314050",
        "243314052",
        "243314058",
        "243314059",
        "243453749",
        "243453761",
        "1453828236",
        "1453828237",
        "1453828238",
        "1453828239",
        "1453828240",
        "1453828241",
        "1453828244",
        "1453828245",
        "1453828246",
        "1453828247",
        "1453828248",
        "1453828249",
    ],
    # Where the water leaves for the lake: U-Taphao from the Khlong R.1 split
    # to its mouth, Khlong R.1 and Khlong R.3.
    "lake": ["453743013", "125942385", "243187986"],
}


def load_source():
    features, seen = [], set()
    for path in SOURCES:
        for feature in json.loads(path.read_text(encoding="utf-8"))["features"]:
            osm_id = feature["properties"]["osm_id"]
            if osm_id not in seen:
                seen.add(osm_id)
                features.append(feature)
    return {"type": "FeatureCollection", "features": features}


def simplify(points, tolerance):
    """Douglas-Peucker: drop vertices closer than ``tolerance`` to the chord."""
    if len(points) < 3:
        return list(points)
    (x1, y1), (x2, y2) = points[0], points[-1]
    chord = math.hypot(x2 - x1, y2 - y1)
    worst, worst_at = -1.0, 0
    for i in range(1, len(points) - 1):
        x, y = points[i]
        if chord == 0:
            distance = math.hypot(x - x1, y - y1)
        else:
            distance = abs((x2 - x1) * (y1 - y) - (x1 - x) * (y2 - y1)) / chord
        if distance > worst:
            worst, worst_at = distance, i
    if worst <= tolerance:
        return [points[0], points[-1]]
    head = simplify(points[: worst_at + 1], tolerance)
    return head[:-1] + simplify(points[worst_at:], tolerance)


def build(source):
    systems_of = {}
    for system, osm_ids in CORRIDOR_LINES.items():
        for osm_id in osm_ids:
            systems_of.setdefault(osm_id, []).append(system)
    missing = sorted(
        set(systems_of) - {f["properties"]["osm_id"] for f in source["features"]}
    )
    if missing:
        raise SystemExit(f"osm_id not in source: {', '.join(missing)}")

    features = []
    for feature in source["features"]:
        properties = {"fclass": feature["properties"]["fclass"]}
        systems = systems_of.get(feature["properties"]["osm_id"])
        if systems:
            properties["systems"] = sorted(systems)
        points = simplify(feature["geometry"]["coordinates"], SIMPLIFY_TOLERANCE_DEG)
        features.append(
            {
                "type": "Feature",
                "properties": properties,
                "geometry": {
                    "type": "LineString",
                    "coordinates": [
                        [round(x, COORD_DECIMALS), round(y, COORD_DECIMALS)]
                        for x, y in points
                    ],
                },
            }
        )
    return {"type": "FeatureCollection", "features": features}


def render(collection):
    return json.dumps(collection, ensure_ascii=False, separators=(",", ":")) + "\n"


def main():
    OUTPUT.write_text(render(build(load_source())), encoding="utf-8")
    print(f"wrote {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
