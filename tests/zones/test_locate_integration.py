"""Real-MongoDB checks for zone location lookup and stored tambon tags.

Uses its own database (TEST_DB) and drops it in tearDownClass. Skipped when no
MongoDB answers at MONGO_URI within one second.
"""

import unittest
from unittest.mock import patch

import beanie
import pymongo

from types import SimpleNamespace

from sindhu import models, schemas
from sindhu.api.routers.v1 import zones as zones_router
from sindhu.services import zones as zones_service

MONGO_URI = "mongodb://localhost:27017"
TEST_DB = "sindhu_test_zone_tambon"
assert TEST_DB != "sindhudb"


def square(x0, y0, size):
    return {
        "type": "Polygon",
        "coordinates": [
            [
                [x0, y0],
                [x0 + size, y0],
                [x0 + size, y0 + size],
                [x0, y0 + size],
                [x0, y0],
            ]
        ],
    }


# Flood zone A: lng 100.0-100.1, lat 7.0-7.1. Flood zone B: lng 100.2-100.3.
# Reference boundary covers both (lng 99.9-100.5, lat 6.9-7.5).
ZONE_A = square(100.0, 7.0, 0.1)
ZONE_B = square(100.2, 7.0, 0.1)
REFERENCE = square(99.9, 6.9, 0.6)


class LocateIntegrationTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        probe = pymongo.MongoClient(MONGO_URI, serverSelectionTimeoutMS=1000)
        try:
            probe.admin.command("ping")
        except Exception as exc:
            raise unittest.SkipTest(f"MongoDB not reachable at {MONGO_URI}: {exc}")
        finally:
            probe.close()

    @classmethod
    def tearDownClass(cls):
        client = pymongo.MongoClient(MONGO_URI, serverSelectionTimeoutMS=1000)
        try:
            client.drop_database(TEST_DB)
        finally:
            client.close()

    async def asyncSetUp(self):
        self.client = pymongo.AsyncMongoClient(
            MONGO_URI, tz_aware=True, serverSelectionTimeoutMS=2000
        )
        self.db = self.client[TEST_DB]
        await beanie.init_beanie(
            database=self.db,
            document_models=[models.Zone, models.Station],
        )
        await self.db.zones.delete_many({})
        await self.db.stations.delete_many({})

        self.zone_a = await self._insert_zone("zone-a", "Zone A", ZONE_A, "flood")
        self.zone_b = await self._insert_zone("zone-b", "Zone B", ZONE_B, "flood")
        self.reference = await self._insert_zone(
            "hatyai-boundary", "Hat Yai", REFERENCE, "reference"
        )

    async def asyncTearDown(self):
        await self.client.close()

    async def _insert_zone(self, code, name, boundary, kind):
        zone = models.Zone(
            name=name,
            code=code,
            boundary=boundary,
            zone_kind=kind,
            status="active",
        )
        await zone.insert()
        return zone

    async def _zone(self, code):
        return await models.Zone.find_one({"code": code})

    # Lookups

    async def test_find_zone_returns_the_zone_containing_the_point(self):
        zone = await zones_service.find_zone_by_location(100.05, 7.05)
        self.assertEqual(zone.code, "zone-a")

        zone = await zones_service.find_zone_by_location(100.25, 7.05)
        self.assertEqual(zone.code, "zone-b")

    async def test_point_outside_flood_zones_returns_none(self):
        # Inside the reference boundary, between the two flood zones.
        self.assertIsNone(await zones_service.find_zone_by_location(100.15, 7.05))
        # Inside the reference boundary only.
        self.assertIsNone(await zones_service.find_zone_by_location(100.4, 7.4))
        # Far outside everything.
        self.assertIsNone(await zones_service.find_zone_by_location(101.0, 8.0))

    async def test_reference_zone_is_never_returned(self):
        for lng, lat in [(100.4, 7.4), (99.95, 6.95), (100.15, 7.05)]:
            with self.subTest(lng=lng, lat=lat):
                zone = await zones_service.find_zone_by_location(lng, lat)
                self.assertTrue(zone is None or zone.zone_kind == "flood")
                self.assertNotEqual(getattr(zone, "code", None), "hatyai-boundary")

    async def test_stored_tambon_names_round_trip(self):
        zone = await self._zone("zone-a")
        zone.tambons = ["ต.ควนรู", " คอหงส์ ", "ควนรู"]
        await zone.save()

        stored = await self._zone("zone-a")
        self.assertEqual(stored.tambons, ["ควนรู", "คอหงส์"])

    async def test_update_without_station_ids_returns_linked_stations(self):
        station = models.Station(
            name="S1",
            name_th="S1",
            code="S1",
            source="test",
            url="http://example.com",
            coordinates={"type": "Point", "coordinates": [100.05, 7.05]},
            status="active",
        )
        await station.insert()
        zone = await self._zone("zone-a")
        zone.stations = [station]
        await zone.save()

        # The link is not fetched unless update asks for it; the response
        # model then failed with a 500 although the save went through.
        form = schemas.zones.CreateUpdateZone(
            name="Zone A", code="zone-a", boundary=ZONE_A, tambons=["ควนรู"]
        )
        result = await zones_router.update(
            zone.id, form, current_user=SimpleNamespace(id="admin")
        )

        out = schemas.zones.ZoneWithStations.model_validate(result, from_attributes=True)
        self.assertEqual([s.code for s in out.stations], ["S1"])
        self.assertEqual(out.tambons, ["ควนรู"])
