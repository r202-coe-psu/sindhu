"""Seed the Songkhla flood zones, their upstream links and the Hat Yai
reference boundary.

The flood zones live in fixtures/zones/songkhla_zones.json. Upstream links are
stored there as zone codes, because ids differ between databases.

    python scripts/seed_zones_songkhla.py           # write the zones to the database
    python scripts/seed_zones_songkhla.py --export  # refresh the file from the database
"""

import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

from sindhu import models  # noqa: E402
from sindhu.services.zones import upstream_violation  # noqa: E402

load_dotenv()

ZONES_PATH = ROOT / "fixtures" / "zones" / "songkhla_zones.json"
HATYAI_BOUNDARY_PATH = (
    ROOT / "sindhu" / "web" / "static" / "resources" / "hatyai_boundary.geojson"
)


def upstream_problems(zones):
    """Messages for upstream links the API would refuse, keyed by zone code."""
    graph = {zone["code"]: list(zone.get("upstream_codes", [])) for zone in zones}
    problems = []
    for code, upstream_codes in graph.items():
        message = upstream_violation(code, upstream_codes, graph)
        if message:
            problems.append(f"{code}: {message}")
    return problems


def load_flood_zones():
    zones = json.loads(ZONES_PATH.read_text(encoding="utf-8"))
    problems = upstream_problems(zones)
    if problems:
        raise SystemExit("invalid upstream links:\n  " + "\n  ".join(problems))
    return zones


def load_hatyai_zone():
    with HATYAI_BOUNDARY_PATH.open(encoding="utf-8") as boundary_file:
        boundary = json.load(boundary_file)

    if boundary.get("type") != "Polygon":
        raise ValueError("Hat Yai boundary must be a GeoJSON Polygon")

    return {
        "name": "Hat Yai Boundary",
        "name_th": "ขอบเขตหาดใหญ่",
        "code": "hatyai-boundary",
        "zone_kind": "reference",
        "metadata": {"role": "reference_boundary", "always_visible": True},
        "station_codes": [],
        "boundary": boundary,
    }


async def connect():
    class Setting:
        MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017/sindhudb")

    await models.init_beanie(None, Setting())


async def seed_system_settings():
    existing = await models.SystemSetting.find_one(sort=[("_id", -1)])
    if existing:
        print("System settings: kept existing map defaults")
        return

    await models.SystemSetting(
        # Hat Yai municipality is the default focus; the zoom shows the whole
        # of the Songkhla flood zones.
        center={"type": "Point", "coordinates": [100.449937, 6.990255]},
        zoom=12,
        min_zoom=6,
        interpolation_coordinate_1=None,
        interpolation_coordinate_2=None,
    ).insert()
    print("System settings: created Hat Yai map defaults")


async def upsert_zone(zone_data):
    codes = zone_data["station_codes"]
    db_stations = await models.Station.find({"code": {"$in": codes}}).to_list()
    found = {s.code for s in db_stations}
    missing = [c for c in codes if c not in found]

    zone = await models.Zone.find_one(models.Zone.code == zone_data["code"])
    action = "updated" if zone else "created"
    if zone is None:
        zone = models.Zone(
            name=zone_data["name"],
            code=zone_data["code"],
            boundary=zone_data["boundary"],
        )
    zone.name = zone_data["name"]
    zone.name_th = zone_data["name_th"]
    zone.boundary = zone_data["boundary"]
    zone.zone_kind = zone_data.get("zone_kind", "flood")
    if "metadata" in zone_data:
        zone.metadata = zone_data["metadata"]
    zone.stations = db_stations
    zone.status = "active"
    await zone.save()

    msg = (
        f"  {action}: {zone_data['name_th']} ({len(db_stations)}/{len(codes)} stations)"
    )
    if missing:
        msg += f", missing codes: {missing}"
    print(msg)
    return zone


async def seed_zones():
    flood_zones = load_flood_zones()
    await connect()
    await seed_system_settings()

    saved = {}
    for zone_data in [*flood_zones, load_hatyai_zone()]:
        saved[zone_data["code"]] = await upsert_zone(zone_data)

    # Second pass: every zone exists now, so codes resolve to this database's ids.
    for zone_data in flood_zones:
        zone = saved[zone_data["code"]]
        zone.upstream_zone_ids = [
            saved[code].id for code in zone_data.get("upstream_codes", [])
        ]
        await zone.save()
        if zone_data.get("upstream_codes"):
            print(f"  upstream: {zone_data['code']} <- {zone_data['upstream_codes']}")

    seeded = set(saved)
    strays = await models.Zone.find(
        {"status": "active", "zone_kind": "flood", "code": {"$nin": sorted(seeded)}}
    ).to_list()
    for zone in strays:
        print(f"  warning: active flood zone not in the seed file: {zone.code}")

    total = await models.Zone.find({"status": "active"}).count()
    print(f"\nTotal active zones: {total}")


async def export_zones():
    await connect()
    zones = (
        await models.Zone.find({"status": "active", "zone_kind": "flood"})
        .sort("code")
        .to_list()
    )
    code_of = {zone.id: zone.code for zone in zones}

    station_ids = [link.ref.id for zone in zones for link in zone.stations]
    stations = await models.Station.find({"_id": {"$in": station_ids}}).to_list()
    station_code_of = {station.id: station.code for station in stations}

    exported = []
    for zone in zones:
        dangling = [str(i) for i in zone.upstream_zone_ids if i not in code_of]
        if dangling:
            print(
                f"  warning: {zone.code} skips upstream ids that are not active: {dangling}"
            )
        exported.append(
            {
                "code": zone.code,
                "name": zone.name,
                "name_th": zone.name_th,
                "zone_kind": zone.zone_kind,
                "metadata": zone.metadata,
                "station_codes": list(
                    dict.fromkeys(
                        station_code_of[link.ref.id]
                        for link in zone.stations
                        if link.ref.id in station_code_of
                    )
                ),
                "upstream_codes": [
                    code_of[i] for i in zone.upstream_zone_ids if i in code_of
                ],
                "boundary": zone.boundary.model_dump()
                if hasattr(zone.boundary, "model_dump")
                else zone.boundary,
            }
        )

    ZONES_PATH.parent.mkdir(parents=True, exist_ok=True)
    ZONES_PATH.write_text(
        json.dumps(exported, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"wrote {len(exported)} zones to {ZONES_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    asyncio.run(export_zones() if "--export" in sys.argv[1:] else seed_zones())
