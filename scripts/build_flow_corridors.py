"""Build the drainage-corridor waterways drawn with flow arrows on the map.

The sources are OSM waterway exports, merged by osm_id (the first source
wins).  scripts/fetch_osm_waterways.py refreshes the second one.  OSM draws a waterway in the direction
the water flows, so the vertex order of each line is its flow direction.

The lines listed in CORRIDOR_LINES become the corridors, drawn bold with
arrows.  Every other line goes to a simplified context file drawn thin and
faint: drawing all 807 source lines at full weight cluttered the map.

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
OUTPUT = (
    ROOT / "sindhu" / "web" / "static" / "resources" / "hatyai_flow_corridors.geojson"
)
CONTEXT_OUTPUT = OUTPUT.with_name("hatyai_waterways_context.geojson")
# About 9 m: below a pixel at the zoom the context lines appear.
CONTEXT_TOLERANCE_DEG = 0.00008
CONTEXT_DECIMALS = 5

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
}


def build(source):
    corridor_of = {
        osm_id: corridor
        for corridor, osm_ids in CORRIDOR_LINES.items()
        for osm_id in osm_ids
    }
    by_id = {f["properties"]["osm_id"]: f for f in source["features"]}
    missing = sorted(set(corridor_of) - set(by_id))
    if missing:
        raise SystemExit(f"osm_id not in source: {', '.join(missing)}")

    features = [
        {
            "type": "Feature",
            "properties": {
                "osm_id": osm_id,
                "name": by_id[osm_id]["properties"]["name"],
                "corridor": corridor,
            },
            "geometry": by_id[osm_id]["geometry"],
        }
        for corridor, osm_ids in CORRIDOR_LINES.items()
        for osm_id in osm_ids
    ]
    return {"type": "FeatureCollection", "features": features}


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


def build_context(source):
    corridor_ids = {osm_id for osm_ids in CORRIDOR_LINES.values() for osm_id in osm_ids}
    features = []
    for feature in source["features"]:
        if feature["properties"]["osm_id"] in corridor_ids:
            continue
        points = simplify(feature["geometry"]["coordinates"], CONTEXT_TOLERANCE_DEG)
        features.append(
            {
                "type": "Feature",
                "properties": {"fclass": feature["properties"]["fclass"]},
                "geometry": {
                    "type": "LineString",
                    "coordinates": [
                        [round(x, CONTEXT_DECIMALS), round(y, CONTEXT_DECIMALS)]
                        for x, y in points
                    ],
                },
            }
        )
    return {"type": "FeatureCollection", "features": features}


def render(collection):
    return json.dumps(collection, ensure_ascii=False, separators=(",", ":")) + "\n"


def main():
    source = load_source()
    for path, collection in (
        (OUTPUT, build(source)),
        (CONTEXT_OUTPUT, build_context(source)),
    ):
        path.write_text(render(collection), encoding="utf-8")
        print(f"wrote {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
