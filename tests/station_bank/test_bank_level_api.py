import datetime
import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from beanie import PydanticObjectId
from beanie.odm.fields import ExpressionField
from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError

from sindhu import schemas
from sindhu.api.core import deps
from sindhu.api.routers.errors.validation_error import http422_error_handler
from sindhu.api.routers.v1 import stations as stations_router

STATION_ID = PydanticObjectId()


def _station_payload(**extra):
    now = datetime.datetime(2026, 11, 2)
    return {
        "_id": STATION_ID,
        "name": "Gauge",
        "name_th": "สถานี",
        "code": "X.1",
        "source": "rid",
        "url": "https://example.test",
        "coordinates": {"type": "Point", "coordinates": [100.5, 7.0]},
        "status": "active",
        "created_date": now,
        "updated_date": now,
        **extra,
    }


class BankLevelSchemaTests(unittest.TestCase):
    def test_stations_saved_before_the_field_existed_load_as_none(self):
        station = schemas.stations.Station.model_validate(_station_payload())
        self.assertIsNone(station.bank_level)

    def test_value_is_exported(self):
        station = schemas.stations.Station.model_validate(
            _station_payload(bank_level=12.5)
        )
        self.assertEqual(station.model_dump()["bank_level"], 12.5)

    def test_generic_update_cannot_reset_it(self):
        self.assertNotIn(
            "bank_level", schemas.stations.CreateUpdateStation.model_fields
        )

    def test_update_requires_an_explicit_value(self):
        with self.assertRaises(ValidationError):
            schemas.stations.UpdateStationBankLevel.model_validate({})
        form = schemas.stations.UpdateStationBankLevel(bank_level=None)
        self.assertIsNone(form.bank_level)

    def test_update_rejects_non_finite_values(self):
        for value in (float("nan"), float("inf")):
            with self.assertRaises(ValidationError):
                schemas.stations.UpdateStationBankLevel(bank_level=value)

    def test_update_rejects_implausible_heights(self):
        for value in (-20.01, 3000.01, -999.0):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                schemas.stations.UpdateStationBankLevel(bank_level=value)

    def test_update_rejects_sensor_no_data_codes(self):
        with self.assertRaises(ValidationError) as caught:
            schemas.stations.UpdateStationBankLevel(bank_level=-9.99)
        self.assertIn("ไม่มีข้อมูล", str(caught.exception))

    def test_update_rejects_zero_which_the_map_treats_as_no_value(self):
        with self.assertRaises(ValidationError) as caught:
            schemas.stations.UpdateStationBankLevel(bank_level=0.0)
        self.assertIn("ไม่มีค่า", str(caught.exception))

    def test_update_rejects_booleans_and_strings(self):
        for value in (True, False, "12.5"):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                schemas.stations.UpdateStationBankLevel.model_validate(
                    {"bank_level": value}
                )

    def test_update_accepts_whole_numbers_from_json(self):
        form = schemas.stations.UpdateStationBankLevel.model_validate_json(
            '{"bank_level": 12}'
        )
        self.assertEqual(form.bank_level, 12.0)

    def test_update_accepts_real_heights(self):
        for value in (-1.5, 12.34, 1200.0):
            with self.subTest(value=value):
                form = schemas.stations.UpdateStationBankLevel(bank_level=value)
                self.assertEqual(form.bank_level, value)


class BankLevelEndpointTests(unittest.IsolatedAsyncioTestCase):
    async def _update(self, station, value):
        form = schemas.stations.UpdateStationBankLevel(bank_level=value)
        with (
            patch.object(
                stations_router.models.Station,
                "get",
                AsyncMock(return_value=station),
            ),
            patch.object(
                stations_router.FastAPICache, "clear", AsyncMock()
            ) as clear_cache,
        ):
            result = await stations_router.update_bank_level(
                STATION_ID, form, current_user=SimpleNamespace(roles=["admin"])
            )
        return result, clear_cache

    def _db_station(self, bank_level=None):
        station = SimpleNamespace(
            bank_level=bank_level,
            updated_date=datetime.datetime(2020, 1, 1),
            save=AsyncMock(),
        )

        async def partial_set(values):
            for field, value in values.items():
                setattr(station, str(field), value)

        station.set = AsyncMock(side_effect=partial_set)
        return station

    async def test_saves_the_value_and_drops_the_cached_map_data(self):
        station = self._db_station()
        result, clear_cache = await self._update(station, 12.5)
        self.assertIs(result, station)
        self.assertEqual(station.bank_level, 12.5)
        self.assertGreater(station.updated_date, datetime.datetime(2020, 1, 1))
        clear_cache.assert_awaited_once_with(
            namespace=stations_router.STATION_METRICS_CACHE_NAMESPACE
        )

    async def test_only_the_bank_fields_are_written(self):
        station = self._db_station()
        await self._update(station, 12.5)
        station.save.assert_not_awaited()
        written = {str(field) for field in station.set.await_args.args[0]}
        self.assertEqual(written, {"bank_level", "updated_date"})

    async def test_null_clears_the_value(self):
        station = self._db_station(bank_level=12.5)
        await self._update(station, None)
        self.assertIsNone(station.bank_level)

    async def test_unknown_station_is_404(self):
        with self.assertRaises(HTTPException) as caught:
            await self._update(None, 12.5)
        self.assertEqual(caught.exception.status_code, 404)

    def test_route_is_admin_only(self):
        route = next(
            r
            for r in stations_router.router.routes
            if r.path.endswith("/{station_id}/bank-level")
        )
        self.assertEqual(route.methods, {"PUT"})
        calls = [d.call for d in route.dependant.dependencies]
        self.assertIn(deps.get_current_active_superuser, calls)


def _written_fields(update_call):
    (operator,) = update_call.args
    return {str(field) for field in operator.query["$set"]}


class OtherWritesKeepTheBankLevelTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        id_field = patch.object(
            stations_router.models.Station,
            "id",
            ExpressionField("_id"),
            create=True,
        )
        id_field.start()
        self.addCleanup(id_field.stop)

    def _found_station(self):
        station = SimpleNamespace(
            bank_level=12.5, update=AsyncMock(), set=AsyncMock(), save=AsyncMock()
        )
        return station

    async def test_visibility_writes_only_its_own_fields(self):
        selected = SimpleNamespace(count=AsyncMock(return_value=1), update=AsyncMock())
        reloaded = SimpleNamespace(to_list=AsyncMock(return_value=[]))
        form = schemas.stations.UpdateStationVisibility(
            station_ids=[STATION_ID], is_visible=False
        )
        with (
            patch.object(
                stations_router.models.Station,
                "find",
                side_effect=[selected, reloaded],
            ),
            patch.object(stations_router.FastAPICache, "clear", AsyncMock()),
        ):
            await stations_router.update_visibility(
                form, current_user=SimpleNamespace(roles=["admin"])
            )
        self.assertEqual(
            _written_fields(selected.update.await_args),
            {"is_visible", "updated_date"},
        )

    async def test_unknown_stations_are_404(self):
        selected = SimpleNamespace(count=AsyncMock(return_value=0), update=AsyncMock())
        form = schemas.stations.UpdateStationVisibility(
            station_ids=[STATION_ID], is_visible=False
        )
        with patch.object(
            stations_router.models.Station, "find", return_value=selected
        ):
            with self.assertRaises(HTTPException) as caught:
                await stations_router.update_visibility(
                    form, current_user=SimpleNamespace(roles=["admin"])
                )
        self.assertEqual(caught.exception.status_code, 404)
        selected.update.assert_not_awaited()

    async def test_generic_update_does_not_write_the_bank_level(self):
        station = self._found_station()
        form = schemas.stations.CreateUpdateStation.model_validate(
            {
                key: value
                for key, value in _station_payload().items()
                if key not in ("_id", "status", "created_date", "updated_date")
            }
        )
        with patch.object(
            stations_router.models.Station,
            "find_one",
            AsyncMock(return_value=station),
        ):
            await stations_router.update(
                STATION_ID, form, current_user=SimpleNamespace()
            )
        station.save.assert_not_awaited()
        written = _written_fields(station.update.await_args)
        self.assertIn("updated_date", written)
        self.assertNotIn("bank_level", written)

    async def test_delete_writes_only_the_status(self):
        station = self._found_station()
        with patch.object(
            stations_router.models.Station,
            "find_one",
            AsyncMock(return_value=station),
        ):
            await stations_router.delete(STATION_ID, current_user=SimpleNamespace())
        station.save.assert_not_awaited()
        self.assertEqual(
            set(station.set.await_args.args[0]), {"status", "updated_date"}
        )


class ValidationErrorResponseTests(unittest.IsolatedAsyncioTestCase):
    async def test_rejected_bank_level_comes_back_as_a_readable_422(self):
        for value in (0.0, -9.99):
            with self.subTest(value=value):
                try:
                    schemas.stations.UpdateStationBankLevel(bank_level=value)
                except ValidationError as error:
                    caught = RequestValidationError(error.errors())
                response = await http422_error_handler(None, caught)
                self.assertEqual(response.status_code, 422)
                body = json.loads(response.body)
                self.assertIn("ไม่", body["errors"][0]["msg"])


if __name__ == "__main__":
    unittest.main()
