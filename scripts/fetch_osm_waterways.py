"""Fetch OSM waterways south of Hat Yai into a fixture for build_flow_corridors.

The original export stops at the head of Khlong U-Taphao; this area holds
its upstream main stem.  Output uses the same properties as the original
export (osm_id, fclass, name) so both sources merge by osm_id.

    python scripts/fetch_osm_waterways.py
"""

import json
import pathlib
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "fixtures" / "waterways" / "songkhla_south_osm.geojson"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
# south, west, north, east
BBOX = (6.40, 100.30, 6.75, 100.70)
QUERY = (
    "[out:json][timeout:90];"
    'way["waterway"~"^(river|canal|stream|drain)$"]({},{},{},{});'
    "out tags geom;"
).format(*BBOX)


def to_geojson(overpass):
    features = [
        {
            "type": "Feature",
            "properties": {
                "osm_id": str(way["id"]),
                "fclass": way["tags"]["waterway"],
                "name": way["tags"].get("name"),
            },
            "geometry": {
                "type": "LineString",
                "coordinates": [[p["lon"], p["lat"]] for p in way["geometry"]],
            },
        }
        for way in sorted(overpass["elements"], key=lambda e: e["id"])
        if way["type"] == "way"
    ]
    return {"type": "FeatureCollection", "features": features}


def main():
    request = urllib.request.Request(
        OVERPASS_URL,
        data=urllib.parse.urlencode({"data": QUERY}).encode(),
        headers={"User-Agent": "osm-waterway-fetch/1.0"},
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        overpass = json.load(response)
    collection = to_geojson(overpass)
    OUTPUT.write_text(
        json.dumps(collection, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {len(collection['features'])} ways to {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
