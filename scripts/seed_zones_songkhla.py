import sys
import os
from dotenv import load_dotenv
from sindhu import models
import asyncio

load_dotenv()

SONGKHLA_ZONES = [
    {
        "name": "U-Tapao Canal Basin",
        "name_th": "ลุ่มน้ำคลองอู่ตะเภา",
        "code": "songkhla-u-tapao",
        "station_codes": ["1109526", "858", "2590", "2589", "2585", "STN08"],
        "boundary": {
            "type": "Polygon",
            "coordinates": [[
                [100.28, 7.12],
                [100.38, 7.18],
                [100.50, 7.15],
                [100.55, 7.05],
                [100.53, 6.92],
                [100.47, 6.85],
                [100.38, 6.82],
                [100.30, 6.88],
                [100.25, 6.98],
                [100.28, 7.12],
            ]],
        },
    },
    {
        "name": "Songkhla Lake Basin",
        "name_th": "ลุ่มน้ำทะเลสาบสงขลา",
        "code": "songkhla-lake",
        "station_codes": ["1109528", "1109527", "1373689", "740739"],
        "boundary": {
            "type": "Polygon",
            "coordinates": [[
                [100.10, 7.65],
                [100.30, 7.65],
                [100.45, 7.50],
                [100.55, 7.30],
                [100.55, 7.15],
                [100.50, 7.05],
                [100.38, 7.10],
                [100.20, 7.15],
                [100.10, 7.25],
                [100.08, 7.45],
                [100.10, 7.65],
            ]],
        },
    },
    {
        "name": "Rattaphum Canal Basin",
        "name_th": "ลุ่มน้ำคลองรัตภูมิ",
        "code": "songkhla-rattaphum",
        "station_codes": ["726673"],
        "boundary": {
            "type": "Polygon",
            "coordinates": [[
                [100.05, 7.25],
                [100.20, 7.25],
                [100.28, 7.12],
                [100.25, 6.98],
                [100.15, 6.92],
                [100.05, 6.95],
                [99.98, 7.05],
                [99.97, 7.15],
                [100.05, 7.25],
            ]],
        },
    },
    {
        "name": "Nathawi Canal Basin",
        "name_th": "ลุ่มน้ำคลองนาทวี",
        "code": "songkhla-nathawi",
        "station_codes": ["850", "2585"],
        "boundary": {
            "type": "Polygon",
            "coordinates": [[
                [100.47, 6.85],
                [100.60, 6.82],
                [100.68, 6.70],
                [100.65, 6.55],
                [100.55, 6.48],
                [100.42, 6.50],
                [100.35, 6.60],
                [100.33, 6.72],
                [100.38, 6.82],
                [100.47, 6.85],
            ]],
        },
    },
    {
        "name": "Thepha Canal Basin",
        "name_th": "ลุ่มน้ำคลองเทพา",
        "code": "songkhla-thepha",
        "station_codes": ["1109525", "1109524"],
        "boundary": {
            "type": "Polygon",
            "coordinates": [[
                [100.55, 7.05],
                [100.72, 7.00],
                [100.78, 6.88],
                [100.75, 6.72],
                [100.68, 6.65],
                [100.60, 6.68],
                [100.55, 6.78],
                [100.53, 6.92],
                [100.55, 7.05],
            ]],
        },
    },
]


async def seed_zones():
    class Setting:
        def __init__(self):
            self.MONGODB_URI = os.getenv(
                "MONGODB_URI", "mongodb://localhost:27017/sindhudb"
            )

    settings = Setting()
    await models.init_beanie(None, settings)

    for zone_data in SONGKHLA_ZONES:
        existing = await models.Zone.find_one(
            models.Zone.code == zone_data["code"]
        )
        if existing:
            print(f"  skipped (already exists): {zone_data['name_th']}")
            continue

        codes = zone_data["station_codes"]
        db_stations = await models.Station.find({"code": {"$in": codes}}).to_list()
        found = {s.code for s in db_stations}
        missing = [c for c in codes if c not in found]

        zone_fields = {k: v for k, v in zone_data.items() if k != "station_codes"}
        zone = models.Zone(**zone_fields)
        zone.stations = db_stations
        await zone.insert()

        msg = f"  created: {zone_data['name_th']} ({len(db_stations)}/{len(codes)} stations)"
        if missing:
            msg += f" — missing codes: {missing}"
        print(msg)

    total = await models.Zone.find({"status": "active"}).count()
    print(f"\nTotal active zones: {total}")


if __name__ == "__main__":
    asyncio.run(seed_zones())
