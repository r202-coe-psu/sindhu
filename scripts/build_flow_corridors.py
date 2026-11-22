"""Build the drainage-corridor waterways drawn with flow arrows on the map.

The source is an OSM waterway export.  OSM draws a waterway in the direction
the water flows, so the vertex order of each line is its flow direction.

Only the lines listed in CORRIDOR_LINES are kept: drawing all 807 source lines
cluttered the map.

    python scripts/build_flow_corridors.py
"""

import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE = ROOT / "fixtures" / "waterways" / "songkhla_waterways_osm.geojson"
OUTPUT = (
    ROOT / "sindhu" / "web" / "static" / "resources" / "hatyai_flow_corridors.geojson"
)

CORRIDOR_LINES = {
    "utapao-main": [
        "321674114",
        "453743011",
        "453743013",
        "502095132",
        "502095133",
        "878600518",
        "1504011383",
        "1504011384",
    ],
    "khlong-r1": ["125942385"],
    "khlong-toei": [
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
    "kho-hong": [
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
    ],
    "khlong-non": ["154729158"],
    "phawong": ["449329363"],
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


def render(collection):
    return json.dumps(collection, ensure_ascii=False, separators=(",", ":")) + "\n"


def main():
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    OUTPUT.write_text(render(build(source)), encoding="utf-8")
    print(f"wrote {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
