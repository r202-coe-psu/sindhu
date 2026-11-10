import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from beanie import PydanticObjectId
from fastapi import HTTPException

from sindhu import models, schemas, services
from sindhu.api.routers.v1 import zones as zones_router

SQUARE = {
    "type": "Polygon",
    "coordinates": [[[100.0, 7.0], [100.1, 7.0], [100.1, 7.1], [100.0, 7.1], [100.0, 7.0]]],
}
CURRENT_USER = SimpleNamespace(id="admin")


class _FakeQuery:
    def __init__(self, items):
        self._items = items

    async def to_list(self):
        return list(self._items)

    def sort(self, *args):
        return self


def _zone_schema(**overrides):
    data = {
        "name": "Zone A",
        "name_th": "โซน A",
        "code": "zone-a",
        "boundary": SQUARE,
        "tambons": ["ควนรู", "คอหงส์"],
    }
    data.update(overrides)
    return schemas.zones.ZoneWithStations(**data)


class GetZonesTests(unittest.IsolatedAsyncioTestCase):
    async def test_get_all_output_includes_tambons(self):
        zone = _zone_schema()

        with patch.object(models.Zone, "find", Mock(return_value=_FakeQuery([zone]))):
            result = await zones_router.get_all(status="active")

        dumped = result.model_dump()
        self.assertEqual(dumped["zones"][0]["tambons"], ["ควนรู", "คอหงส์"])


class TambonTagTests(unittest.TestCase):
    def test_names_are_trimmed_unprefixed_and_deduplicated(self):
        zone = _zone_schema(tambons=[" ต.ควนรู", "ตำบลคอหงส์", "ควนรู", "", "  "])

        self.assertEqual(zone.tambons, ["ควนรู", "คอหงส์"])

    def test_none_is_an_empty_list(self):
        self.assertEqual(_zone_schema(tambons=None).tambons, [])

    def test_legacy_ref_dicts_become_names(self):
        zone = _zone_schema(
            tambons=[{"code": "1", "name_th": "ควนรู", "amphoe_th": "หาดใหญ่"}]
        )

        self.assertEqual(zone.tambons, ["ควนรู"])

    def test_create_form_accepts_names(self):
        form = schemas.zones.CreateUpdateZone(
            name="Z", code="z", boundary=SQUARE, tambons=["คลองแห"]
        )

        self.assertEqual(form.tambons, ["คลองแห"])


class LocateTests(unittest.IsolatedAsyncioTestCase):
    async def test_inside_zone_populates_zone_and_its_tambons(self):
        zone = _zone_schema()
        body = schemas.zones.LocateRequest(latitude=7.05, longitude=100.05)

        with (
            patch.object(
                services.zones, "find_zone_by_location", AsyncMock(return_value=zone)
            ) as find_zone,
            patch.object(
                services.zones,
                "find_stations_by_zone",
                AsyncMock(return_value=[{"code": "S1"}]),
            ) as find_stations,
        ):
            result = await zones_router.locate(body)

        find_zone.assert_awaited_once_with(100.05, 7.05)
        find_stations.assert_awaited_once_with(zone, 100.05, 7.05)
        self.assertIsNotNone(result.zone)
        self.assertEqual(result.zone.code, "zone-a")
        self.assertEqual(result.zone.tambons, ["ควนรู", "คอหงส์"])
        self.assertNotIn("tambon", result.model_dump())
        self.assertEqual(result.nearby_stations, [{"code": "S1"}])

    async def test_outside_zone_returns_zone_none(self):
        body = schemas.zones.LocateRequest(latitude=1.0, longitude=1.0)

        with (
            patch.object(
                services.zones, "find_zone_by_location", AsyncMock(return_value=None)
            ),
            patch.object(
                services.zones, "find_stations_by_zone", AsyncMock(return_value=[])
            ),
        ):
            result = await zones_router.locate(body)

        self.assertIsNone(result.zone)
        self.assertEqual(result.nearby_stations, [])


def _db_zone(**overrides):
    values = {
        "id": PydanticObjectId(),
        "zone_kind": "flood",
        "name": "Zone A",
        "code": "zone-a",
        "tambons": ["Old"],
        "stations": ["station-kept"],
        "updated_date": None,
        "saved": 0,
    }
    values.update(overrides)
    db = SimpleNamespace(**values)

    async def save():
        db.saved += 1

    db.save = save
    return db


class UpdateZoneTests(unittest.IsolatedAsyncioTestCase):
    def _base_payload(self, **extra):
        payload = {"name": "Zone A", "code": "zone-a", "boundary": SQUARE}
        payload.update(extra)
        return payload

    async def _update(self, db_zone, payload):
        form = schemas.zones.CreateUpdateZone(**payload)
        # models.Zone.id is only a query expression after Beanie init; the
        # fake find_one ignores the query, so a placeholder is enough here.
        with patch.object(
            models.Zone, "find_one", AsyncMock(return_value=db_zone)
        ), patch.object(models.Zone, "id", new=object(), create=True), patch.object(
            models.Station, "find", Mock(return_value=_FakeQuery(["new-station"]))
        ):
            return await zones_router.update(
                db_zone.id, form, current_user=CURRENT_USER
            )

    async def test_update_without_tambons_keeps_existing_tambons(self):
        db_zone = _db_zone()

        await self._update(db_zone, self._base_payload(name="Renamed"))

        self.assertEqual(db_zone.name, "Renamed")
        self.assertEqual(db_zone.tambons, ["Old"])
        self.assertEqual(db_zone.saved, 1)

    async def test_update_without_station_ids_keeps_stations(self):
        db_zone = _db_zone()

        await self._update(db_zone, self._base_payload(name="Renamed"))

        self.assertEqual(db_zone.stations, ["station-kept"])

    async def test_update_with_station_ids_replaces_stations(self):
        db_zone = _db_zone()

        await self._update(
            db_zone, self._base_payload(station_ids=[str(PydanticObjectId())])
        )

        self.assertEqual(db_zone.stations, ["new-station"])

    async def test_update_with_tambons_replaces_them(self):
        db_zone = _db_zone()

        await self._update(db_zone, self._base_payload(tambons=["ต.New", "Other"]))

        self.assertEqual(db_zone.tambons, ["New", "Other"])

    async def test_update_with_empty_tambons_clears_them(self):
        db_zone = _db_zone()

        await self._update(db_zone, self._base_payload(tambons=[]))

        self.assertEqual(db_zone.tambons, [])

    async def test_update_missing_zone_is_404(self):
        form = schemas.zones.CreateUpdateZone(**self._base_payload())
        with patch.object(
            models.Zone, "find_one", AsyncMock(return_value=None)
        ), patch.object(models.Zone, "id", new=object(), create=True):
            with self.assertRaises(HTTPException) as ctx:
                await zones_router.update(
                    PydanticObjectId(), form, current_user=CURRENT_USER
                )
        self.assertEqual(ctx.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
