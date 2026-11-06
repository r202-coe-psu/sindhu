import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from beanie import PydanticObjectId
from fastapi import HTTPException

from sindhu import models, schemas, services
from sindhu.api.core import deps
from sindhu.api.routers.v1 import tambons as tambons_router
from sindhu.api.routers.v1 import zones as zones_router
from sindhu.schemas.tambons import TambonRef, TambonSummary

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
        "tambons": [{"code": "1", "name_th": "ควนรู", "amphoe_th": "หาดใหญ่"}],
    }
    data.update(overrides)
    return schemas.zones.ZoneWithStations(**data)


class GetZonesTests(unittest.IsolatedAsyncioTestCase):
    async def test_get_all_output_includes_tambons(self):
        zone = _zone_schema()

        with patch.object(models.Zone, "find", Mock(return_value=_FakeQuery([zone]))):
            result = await zones_router.get_all(status="active")

        dumped = result.model_dump()
        self.assertEqual(
            dumped["zones"][0]["tambons"],
            [{"code": "1", "name_th": "ควนรู", "amphoe_th": "หาดใหญ่"}],
        )


class LocateTests(unittest.IsolatedAsyncioTestCase):
    async def test_inside_zone_populates_zone_and_tambon(self):
        zone = _zone_schema()
        tambon = {"code": "1", "name_th": "ควนรู", "amphoe_th": "หาดใหญ่", "zone_ids": ["z"]}
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
            patch.object(
                services.tambons,
                "find_tambon_by_location",
                AsyncMock(return_value=tambon),
            ) as find_tambon,
        ):
            result = await zones_router.locate(body)

        find_zone.assert_awaited_once_with(100.05, 7.05)
        find_tambon.assert_awaited_once_with(100.05, 7.05)
        find_stations.assert_awaited_once_with(zone, 100.05, 7.05)
        self.assertIsNotNone(result.zone)
        self.assertEqual(result.zone.code, "zone-a")
        self.assertIsInstance(result.tambon, TambonSummary)
        self.assertEqual(result.tambon.code, "1")
        self.assertEqual(result.tambon.zone_ids, ["z"])
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
            patch.object(
                services.tambons, "find_tambon_by_location", AsyncMock(return_value=None)
            ),
        ):
            result = await zones_router.locate(body)

        self.assertIsNone(result.zone)
        self.assertIsNone(result.tambon)
        self.assertEqual(result.nearby_stations, [])


def _db_zone(**overrides):
    values = {
        "id": PydanticObjectId(),
        "zone_kind": "flood",
        "name": "Zone A",
        "code": "zone-a",
        "tambons": [TambonRef(code="old", name_th="Old", amphoe_th=None)],
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
        self.assertEqual(
            db_zone.tambons, [TambonRef(code="old", name_th="Old", amphoe_th=None)]
        )
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

        with patch.object(
            services.tambons, "sync_tambon_zone_links", AsyncMock()
        ):
            await self._update(
                db_zone,
                self._base_payload(
                    tambons=[{"code": "9", "name_th": "New", "amphoe_th": "X"}]
                ),
            )

        self.assertEqual(
            db_zone.tambons, [TambonRef(code="9", name_th="New", amphoe_th="X")]
        )

    async def test_tambon_update_syncs_zone_links_with_before_and_after(self):
        db_zone = _db_zone()
        sync = AsyncMock()
        old = TambonRef(code="old", name_th="Old", amphoe_th=None)
        new = TambonRef(code="9", name_th="New", amphoe_th="X")

        with patch.object(services.tambons, "sync_tambon_zone_links", sync):
            await self._update(
                db_zone,
                self._base_payload(
                    tambons=[{"code": "9", "name_th": "New", "amphoe_th": "X"}]
                ),
            )

        sync.assert_awaited_once_with(db_zone.id, [old], [new])

    async def test_update_without_tambons_does_not_sync_zone_links(self):
        db_zone = _db_zone()
        sync = AsyncMock()

        with patch.object(services.tambons, "sync_tambon_zone_links", sync):
            await self._update(db_zone, self._base_payload(name="Renamed"))

        sync.assert_not_awaited()

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


def _import_body(features, dry_run=True, **overrides):
    payload = {
        "feature_collection": {"type": "FeatureCollection", "features": features},
        "code_property": "tc",
        "name_property": "tn",
        "dry_run": dry_run,
    }
    payload.update(overrides)
    return json.dumps(payload).encode("utf-8")


def _feature(code, x0, y0):
    return {
        "type": "Feature",
        "properties": {"tc": code, "tn": f"T{code}"},
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[x0, y0], [x0 + 0.05, y0], [x0 + 0.05, y0 + 0.05], [x0, y0]]],
        },
    }


class FakeRequest:
    """Starlette-like request: headers plus an async stream of byte chunks."""

    def __init__(self, chunks=(), content_length=None):
        self.headers = {}
        if content_length is not None:
            self.headers["content-length"] = str(content_length)
        self._chunks = list(chunks)

    async def stream(self):
        for chunk in self._chunks:
            yield chunk


def _request_with_body(body, content_length=None):
    return FakeRequest(chunks=[body], content_length=content_length)


class ImportTambonsRouteTests(unittest.IsolatedAsyncioTestCase):
    async def test_dry_run_writes_nothing(self):
        zone = SimpleNamespace(
            id=PydanticObjectId(),
            code="zone-a",
            name=None,
            name_th="โซน A",
            zone_kind="flood",
            status="active",
            tambons=[],
            boundary=SimpleNamespace(model_dump=lambda: SQUARE),
            save=AsyncMock(),
        )
        request = _request_with_body(_import_body([_feature("1", 100.01, 7.01)], dry_run=True))

        insert_many = AsyncMock()
        tambon_find = Mock()
        get_collection = Mock()
        with (
            patch.object(models.Zone, "find", Mock(return_value=_FakeQuery([zone]))),
            patch.object(models.Tambon, "insert_many", insert_many),
            patch.object(models.Tambon, "find", tambon_find),
            patch.object(models.Zone, "get_pymongo_collection", get_collection),
        ):
            result = await tambons_router.import_(request, current_user=CURRENT_USER)

        self.assertTrue(result.dry_run)
        self.assertEqual(result.imported, 1)
        insert_many.assert_not_called()
        tambon_find.assert_not_called()
        get_collection.assert_not_called()
        zone.save.assert_not_called()

    async def test_content_length_over_limit_returns_413(self):
        request = _request_with_body(
            _import_body([]),
            content_length=tambons_router.MAX_IMPORT_BYTES + 1,
        )

        with self.assertRaises(HTTPException) as ctx:
            await tambons_router.import_(request, current_user=CURRENT_USER)
        self.assertEqual(ctx.exception.status_code, 413)

    async def test_chunked_body_over_limit_returns_413_without_content_length(self):
        chunks = [b"x" * 60, b"x" * 60]

        with patch.object(tambons_router, "MAX_IMPORT_BYTES", 100):
            with self.assertRaises(HTTPException) as ctx:
                await tambons_router.import_(
                    FakeRequest(chunks=chunks), current_user=CURRENT_USER
                )
        self.assertEqual(ctx.exception.status_code, 413)

    async def test_invalid_json_returns_422(self):
        with self.assertRaises(HTTPException) as ctx:
            await tambons_router.import_(
                _request_with_body(b"{not json"), current_user=CURRENT_USER
            )
        self.assertEqual(ctx.exception.status_code, 422)

    async def test_schema_violation_returns_422(self):
        body = json.dumps({"feature_collection": {}}).encode("utf-8")

        with self.assertRaises(HTTPException) as ctx:
            await tambons_router.import_(
                _request_with_body(body), current_user=CURRENT_USER
            )
        self.assertEqual(ctx.exception.status_code, 422)

    async def test_too_many_features_returns_422(self):
        body = _import_body([{"type": "Feature"}] * (tambons_router.MAX_IMPORT_FEATURES + 1))

        with self.assertRaises(HTTPException) as ctx:
            await tambons_router.import_(
                _request_with_body(body), current_user=CURRENT_USER
            )
        self.assertEqual(ctx.exception.status_code, 422)

    def test_import_route_requires_get_current_user(self):
        routes = [
            r for r in tambons_router.router.routes if getattr(r, "path", "").endswith("/import")
        ]
        self.assertEqual(len(routes), 1)
        calls = [d.call for d in routes[0].dependant.dependencies]
        self.assertIn(deps.get_current_user, calls)


if __name__ == "__main__":
    unittest.main()
