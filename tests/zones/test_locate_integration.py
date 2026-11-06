"""Real-MongoDB checks for zone/tambon location lookup and the import swap.

Uses its own database (TEST_DB) and drops it in tearDownClass. Skipped when no
MongoDB answers at MONGO_URI within one second.
"""

import unittest
from unittest.mock import patch

import beanie
import pymongo

from sindhu import models, schemas
from sindhu.services import tambons as tambon_service
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


def tambon_feature(code, name, geometry, amphoe="หาดใหญ่"):
    return {
        "type": "Feature",
        "properties": {"tc": code, "tn": name, "ap": amphoe},
        "geometry": geometry,
    }


def fc(*features):
    return {"type": "FeatureCollection", "features": list(features)}


def import_request(features, dry_run=False):
    return schemas.tambons.ImportTambonRequest(
        feature_collection=fc(*features),
        code_property="tc",
        name_property="tn",
        amphoe_property="ap",
        dry_run=dry_run,
    )


# Flood zone A: lng 100.0-100.1, lat 7.0-7.1. Flood zone B: lng 100.2-100.3.
# Reference boundary covers both (lng 99.9-100.5, lat 6.9-7.5) and is clipping.
ZONE_A = square(100.0, 7.0, 0.1)
ZONE_B = square(100.2, 7.0, 0.1)
REFERENCE = square(99.9, 6.9, 0.6)

FIRST_BATCH = [
    tambon_feature("1", "ควนรู", square(100.02, 7.02, 0.03)),
    tambon_feature("2", "ท่าช้าง", square(100.22, 7.02, 0.03)),
    # MultiPolygon: part 1 in zone A, part 2 in zone B.
    tambon_feature(
        "3",
        "คลองแห",
        {
            "type": "MultiPolygon",
            "coordinates": [
                square(100.05, 7.06, 0.02)["coordinates"],
                square(100.25, 7.06, 0.02)["coordinates"],
            ],
        },
    ),
    # Outside the reference boundary: clipped out.
    tambon_feature("9", "นอกเขต", square(101.0, 8.0, 0.02)),
]

SECOND_BATCH = [
    tambon_feature("2", "ท่าช้าง", square(100.22, 7.02, 0.03)),
    tambon_feature("5", "ทุ่งใหญ่", square(100.01, 7.08, 0.02)),
]


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
            document_models=[models.Zone, models.Tambon, models.Station],
        )
        await self.db.zones.delete_many({})
        await self.db.tambons.delete_many({})
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

    async def _tambon_codes(self):
        docs = await models.Tambon.find_all().to_list()
        return sorted(d.code for d in docs), {d.batch_id for d in docs}

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

    async def test_find_tambon_before_any_import_is_none(self):
        self.assertIsNone(await tambon_service.find_tambon_by_location(100.03, 7.03))

    # Import

    async def test_import_then_find_tambon_including_multipolygon(self):
        result = await tambon_service.import_tambons(import_request(FIRST_BATCH, dry_run=False), dry_run=False)
        self.assertFalse(result["dry_run"])
        self.assertEqual(result["imported"], 3)
        self.assertEqual(result["clipped_out"], 1)

        found = await tambon_service.find_tambon_by_location(100.03, 7.03)
        self.assertEqual(found["code"], "1")
        self.assertEqual(found["name_th"], "ควนรู")

        found = await tambon_service.find_tambon_by_location(100.23, 7.03)
        self.assertEqual(found["code"], "2")

        # Second part of the MultiPolygon, and the first part.
        found = await tambon_service.find_tambon_by_location(100.26, 7.07)
        self.assertEqual(found["code"], "3")
        self.assertEqual(sorted(found["zone_ids"]), sorted([str(self.zone_a.id), str(self.zone_b.id)]))
        found = await tambon_service.find_tambon_by_location(100.06, 7.07)
        self.assertEqual(found["code"], "3")

        self.assertIsNone(await tambon_service.find_tambon_by_location(100.15, 7.05))

    async def test_import_updates_zone_tambons(self):
        await tambon_service.import_tambons(import_request(FIRST_BATCH, dry_run=False), dry_run=False)

        zone_a = await self._zone("zone-a")
        zone_b = await self._zone("zone-b")
        reference = await self._zone("hatyai-boundary")
        self.assertEqual([t.code for t in zone_a.tambons], ["1", "3"])
        self.assertEqual([t.code for t in zone_b.tambons], ["2", "3"])
        self.assertEqual(reference.tambons, [])
        self.assertEqual(zone_a.tambons[0].name_th, "ควนรู")

    async def test_second_import_keeps_only_the_newest_batch(self):
        await tambon_service.import_tambons(import_request(FIRST_BATCH, dry_run=False), dry_run=False)
        codes_1, batches_1 = await self._tambon_codes()
        self.assertEqual(codes_1, ["1", "2", "3"])

        result = await tambon_service.import_tambons(import_request(SECOND_BATCH, dry_run=False), dry_run=False)
        self.assertEqual(result["imported"], 2)

        codes_2, batches_2 = await self._tambon_codes()
        self.assertEqual(codes_2, ["2", "5"])
        self.assertEqual(len(batches_2), 1)
        self.assertTrue(batches_2.isdisjoint(batches_1))

        self.assertIsNone(await tambon_service.find_tambon_by_location(100.03, 7.03))
        found = await tambon_service.find_tambon_by_location(100.02, 7.09)
        self.assertEqual(found["code"], "5")

        self.assertEqual([t.code for t in (await self._zone("zone-a")).tambons], ["5"])
        self.assertEqual([t.code for t in (await self._zone("zone-b")).tambons], ["2"])

    async def test_failed_insert_leaves_the_old_batch_intact(self):
        await tambon_service.import_tambons(import_request(FIRST_BATCH, dry_run=False), dry_run=False)
        codes_before, batches_before = await self._tambon_codes()
        zone_a_before = [t.code for t in (await self._zone("zone-a")).tambons]

        real_insert_many = models.Tambon.insert_many

        async def partial_then_fail(docs):
            # Write one document of the new batch, then fail mid-way.
            await real_insert_many(docs[:1])
            raise RuntimeError("simulated insert failure")

        with patch.object(models.Tambon, "insert_many", new=partial_then_fail):
            with self.assertRaisesRegex(RuntimeError, "simulated insert failure"):
                await tambon_service.import_tambons(import_request(SECOND_BATCH, dry_run=False), dry_run=False)

        codes_after, batches_after = await self._tambon_codes()
        self.assertEqual(codes_after, codes_before)
        self.assertEqual(batches_after, batches_before)
        self.assertEqual(
            [t.code for t in (await self._zone("zone-a")).tambons], zone_a_before
        )
        found = await tambon_service.find_tambon_by_location(100.23, 7.03)
        self.assertEqual(found["code"], "2")

    async def test_dry_run_against_real_db_writes_nothing(self):
        result = await tambon_service.import_tambons(import_request(FIRST_BATCH, dry_run=True), dry_run=True)
        self.assertTrue(result["dry_run"])
        codes, _ = await self._tambon_codes()
        self.assertEqual(codes, [])
        zone_a = await self._zone("zone-a")
        self.assertEqual(zone_a.tambons, [])


    async def test_failed_zone_bulk_write_restores_zones_and_old_batch(self):
        await tambon_service.import_tambons(import_request(FIRST_BATCH), dry_run=False)
        codes_before, batches_before = await self._tambon_codes()
        zones_before = {
            code: [t.code for t in (await self._zone(code)).tambons]
            for code in ("zone-a", "zone-b", "hatyai-boundary")
        }

        original_get_collection = models.Zone.get_pymongo_collection
        real_collection = original_get_collection()
        calls = []

        class FlakyCollection:
            # Beanie also reads through this method, so delegate everything
            # except bulk_write to the real collection.
            def __getattr__(self, name):
                return getattr(real_collection, name)

            async def bulk_write(self, ops, ordered=True):
                calls.append(len(ops))
                if len(calls) == 1:
                    # A partial write lands, then the bulk write fails.
                    await real_collection.bulk_write(ops[:1], ordered=True)
                    raise RuntimeError("simulated zone bulk_write failure")
                return await real_collection.bulk_write(ops, ordered=ordered)

        with patch.object(
            models.Zone,
            "get_pymongo_collection",
            new=classmethod(lambda cls: FlakyCollection()),
        ):
            with self.assertRaisesRegex(RuntimeError, "zone bulk_write failure"):
                await tambon_service.import_tambons(
                    import_request(SECOND_BATCH), dry_run=False
                )

        # One failing bulk write, then one restore write.
        self.assertEqual(len(calls), 2)
        codes_after, batches_after = await self._tambon_codes()
        self.assertEqual(codes_after, codes_before)
        self.assertEqual(batches_after, batches_before)
        zones_after = {
            code: [t.code for t in (await self._zone(code)).tambons]
            for code in ("zone-a", "zone-b", "hatyai-boundary")
        }
        self.assertEqual(zones_after, zones_before)

    # sync_tambon_zone_links

    async def _tambon_zone_ids(self, code):
        doc = await models.Tambon.find_one({"code": code})
        return sorted(doc.zone_ids) if doc else None

    async def test_sync_adds_zone_id_to_matching_tambon(self):
        await tambon_service.import_tambons(import_request(FIRST_BATCH), dry_run=False)
        self.assertEqual(await self._tambon_zone_ids("1"), [str(self.zone_a.id)])

        await tambon_service.sync_tambon_zone_links(
            self.zone_b.id, [], [{"code": "1", "name_th": "ควนรู"}]
        )

        self.assertEqual(
            await self._tambon_zone_ids("1"),
            sorted([str(self.zone_a.id), str(self.zone_b.id)]),
        )

    async def test_sync_removes_zone_id_from_dropped_tambon(self):
        await tambon_service.import_tambons(import_request(FIRST_BATCH), dry_run=False)
        self.assertEqual(
            await self._tambon_zone_ids("3"),
            sorted([str(self.zone_a.id), str(self.zone_b.id)]),
        )

        await tambon_service.sync_tambon_zone_links(
            self.zone_a.id, [{"code": "3", "name_th": "คลองแห"}], []
        )

        self.assertEqual(await self._tambon_zone_ids("3"), [str(self.zone_b.id)])

    async def test_sync_unchanged_codes_leave_links_alone(self):
        await tambon_service.import_tambons(import_request(FIRST_BATCH), dry_run=False)
        before = await self._tambon_zone_ids("3")

        # Legacy string on one side and a ref on the other: same code, no change.
        await tambon_service.sync_tambon_zone_links(
            self.zone_a.id, ["3"], [{"code": "3", "name_th": "คลองแห"}]
        )

        self.assertEqual(await self._tambon_zone_ids("3"), before)

    async def test_sync_without_any_batch_is_a_noop(self):
        await tambon_service.sync_tambon_zone_links(
            self.zone_a.id, [], [{"code": "1", "name_th": "ควนรู"}]
        )

        codes, _ = await self._tambon_codes()
        self.assertEqual(codes, [])

    async def test_sync_ignores_codes_missing_from_the_newest_batch(self):
        await tambon_service.import_tambons(import_request(FIRST_BATCH), dry_run=False)
        await tambon_service.import_tambons(import_request(SECOND_BATCH), dry_run=False)
        codes_before, _ = await self._tambon_codes()
        zone_ids_2 = await self._tambon_zone_ids("2")

        # Code "1" was only in the replaced batch; it must not be created or linked.
        await tambon_service.sync_tambon_zone_links(
            self.zone_a.id, [], [{"code": "1", "name_th": "ควนรู"}]
        )

        codes_after, _ = await self._tambon_codes()
        self.assertEqual(codes_after, codes_before)
        self.assertIsNone(await self._tambon_zone_ids("1"))
        self.assertEqual(await self._tambon_zone_ids("2"), zone_ids_2)


if __name__ == "__main__":
    unittest.main()
