import asyncio
import datetime
import json
import time
import unittest

from sindhu.services.cctv_cache import CacheError, CctvCache

UTC = datetime.timezone.utc


class MutableClock:
    def __init__(self) -> None:
        self.value = datetime.datetime(2026, 9, 3, 4, 0, tzinfo=UTC)

    def __call__(self) -> datetime.datetime:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += datetime.timedelta(seconds=seconds)


class FakeRedis:
    """Minimal async Redis double, including NX/TTL and compare-delete EVAL."""

    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.expires: dict[str, float] = {}
        self.set_calls: list[tuple[str, object, object, object]] = []
        self.fail_get = False
        self.fail_data_set = False

    def _purge(self, key: str) -> None:
        expiry = self.expires.get(key)
        if expiry is not None and expiry <= time.monotonic():
            self.values.pop(key, None)
            self.expires.pop(key, None)

    async def get(self, key: str) -> str | None:
        await asyncio.sleep(0)
        if self.fail_get:
            raise ConnectionError("redis outage must not escape")
        self._purge(key)
        return self.values.get(key)

    async def set(
        self,
        key: str,
        value: object,
        *,
        ex: int | None = None,
        nx: bool = False,
        **_: object,
    ) -> bool:
        await asyncio.sleep(0)
        self.set_calls.append((key, value, ex, nx))
        self._purge(key)
        if (
            self.fail_data_set
            and not key.endswith(":lock")
            and not key.endswith(":error")
        ):
            return False
        if nx and key in self.values:
            return False
        self.values[key] = str(value)
        if ex is not None:
            self.expires[key] = time.monotonic() + ex
        else:
            self.expires.pop(key, None)
        return True

    async def delete(self, key: str) -> int:
        await asyncio.sleep(0)
        self._purge(key)
        existed = key in self.values
        self.values.pop(key, None)
        self.expires.pop(key, None)
        return int(existed)

    async def eval(self, _script: str, numkeys: int, *args: object) -> int:
        await asyncio.sleep(0)
        self._purge(str(args[0]))
        key = str(args[0])
        token = str(args[1])
        if numkeys == 1 and self.values.get(key) == token:
            await self.delete(key)
            return 1
        return 0


class BrokenRedis:
    async def get(self, _key: str) -> None:
        raise ConnectionError("redis exception text must not escape")


class HangingRedis:
    async def get(self, _key: str) -> None:
        await asyncio.Event().wait()


class CctvCacheTests(unittest.IsolatedAsyncioTestCase):
    async def test_round_trip_stores_only_json_metadata_and_returns_fresh_value(
        self,
    ) -> None:
        redis = FakeRedis()
        clock = MutableClock()
        cache = CctvCache(redis, clock=clock)
        calls = 0

        async def loader() -> list[dict[str, str]]:
            nonlocal calls
            calls += 1
            return [{"source": "hatyai_city_climate", "image_url": "https://x"}]

        first = await cache.get("sindhu:cctv:v1:latest:hatyai", loader)
        second = await cache.get("sindhu:cctv:v1:latest:hatyai", loader)

        self.assertEqual(first.value, second.value)
        self.assertIsNotNone(first.fetched_at)
        self.assertFalse(first.stale)
        self.assertIsNone(first.error)
        self.assertEqual(calls, 1)
        self.assertEqual(
            set(json.loads(redis.values["sindhu:cctv:v1:latest:hatyai"])),
            {"version", "fetched_at", "value"},
        )

    async def test_cold_callers_singleflight_and_recheck_after_lock(self) -> None:
        redis = FakeRedis()
        cache = CctvCache(redis)
        started = asyncio.Event()
        finish = asyncio.Event()
        calls = 0

        async def loader() -> list[str]:
            nonlocal calls
            calls += 1
            started.set()
            await finish.wait()
            return ["loaded"]

        owner = asyncio.create_task(cache.get("sindhu:cctv:v1:latest:dwr", loader))
        await started.wait()
        loser = asyncio.create_task(cache.get("sindhu:cctv:v1:latest:dwr", loader))
        await asyncio.sleep(0.05)
        self.assertFalse(loser.done())
        finish.set()
        owner_result, loser_result = await asyncio.gather(owner, loser)

        self.assertEqual(owner_result.value, ["loaded"])
        self.assertEqual(loser_result.value, ["loaded"])
        self.assertEqual(calls, 1)

    async def test_stale_value_is_served_while_refresh_runs(self) -> None:
        redis = FakeRedis()
        clock = MutableClock()
        cache = CctvCache(redis, clock=clock)
        calls = 0
        started = asyncio.Event()
        finish = asyncio.Event()

        async def initial_loader() -> list[str]:
            return ["old"]

        await cache.get("sindhu:cctv:v1:latest:hatyai", initial_loader)
        clock.advance(121)

        async def refresh_loader() -> list[str]:
            nonlocal calls
            calls += 1
            started.set()
            await finish.wait()
            return ["new"]

        owner = asyncio.create_task(
            cache.get("sindhu:cctv:v1:latest:hatyai", refresh_loader)
        )
        await started.wait()
        stale = await cache.get("sindhu:cctv:v1:latest:hatyai", refresh_loader)
        self.assertEqual(stale.value, ["old"])
        self.assertTrue(stale.stale)
        self.assertIsNone(stale.error)
        self.assertEqual(calls, 1)
        finish.set()
        refreshed = await owner
        self.assertEqual(refreshed.value, ["new"])
        self.assertFalse(refreshed.stale)

    async def test_loader_failure_keeps_original_age_and_error_cooldown(self) -> None:
        redis = FakeRedis()
        clock = MutableClock()
        cache = CctvCache(redis, clock=clock)
        calls = 0

        async def good_loader() -> list[str]:
            return ["old"]

        original = await cache.get(
            "sindhu:cctv:v1:history:hatyai:2026-09-02", good_loader
        )
        clock.advance(121)

        async def failing_loader() -> list[str]:
            nonlocal calls
            calls += 1
            raise RuntimeError("provider secret and HTML must not be returned")

        failed = await cache.get(
            "sindhu:cctv:v1:history:hatyai:2026-09-02",
            failing_loader,
            stale_seconds=900,
        )
        self.assertEqual(failed.value, ["old"])
        self.assertTrue(failed.stale)
        self.assertEqual(failed.error, "loader_failed")
        self.assertEqual(failed.fetched_at, original.fetched_at)

        again = await cache.get(
            "sindhu:cctv:v1:history:hatyai:2026-09-02",
            failing_loader,
            stale_seconds=900,
        )
        self.assertEqual(again.error, "loader_failed")
        self.assertEqual(calls, 1)
        self.assertNotIn(
            "secret",
            redis.values["sindhu:cctv:v1:history:hatyai:2026-09-02:error"],
        )

    async def test_loader_failure_does_not_return_fallback_after_total_age_expires(
        self,
    ) -> None:
        redis = FakeRedis()
        clock = MutableClock()
        cache = CctvCache(redis, clock=clock)
        key = "sindhu:cctv:v1:latest:age-bound"

        await cache.get(key, lambda: ["old"])
        clock.advance(121)

        async def failing_loader() -> list[str]:
            clock.advance(1_800)
            raise RuntimeError("failure after the stale horizon")

        with self.assertRaises(CacheError) as error:
            await cache.get(key, failing_loader)
        self.assertEqual(error.exception.code, "loader_failed")

    async def test_empty_history_uses_120_second_total_ttl(self) -> None:
        redis = FakeRedis()
        clock = MutableClock()
        cache = CctvCache(redis, clock=clock)
        key = "sindhu:cctv:v1:history:hatyai:2026-09-02"
        calls = 0

        async def loader() -> dict[str, object]:
            nonlocal calls
            calls += 1
            return {"frames": [], "possibly_truncated": False}

        result = await cache.get(key, loader, fresh_seconds=900, stale_seconds=900)
        self.assertEqual(result.value, {"frames": [], "possibly_truncated": False})
        data_sets = [call for call in redis.set_calls if call[0] == key]
        self.assertEqual(data_sets[-1][2], 120)

        clock.advance(121)
        await cache.get(key, loader, fresh_seconds=900, stale_seconds=900)
        self.assertEqual(calls, 2)

    async def test_hanging_redis_command_times_out_to_direct_fallback(self) -> None:
        cache = CctvCache(HangingRedis())

        result = await asyncio.wait_for(
            cache.get("sindhu:cctv:v1:latest:hanging", lambda: ["direct"]),
            timeout=2,
        )

        self.assertEqual(result.value, ["direct"])
        self.assertEqual(result.error, "redis_unavailable")

    async def test_redis_outage_direct_fallback_is_bounded_and_fail_fast(self) -> None:
        cache = CctvCache(BrokenRedis())
        started = asyncio.Event()
        finish = asyncio.Event()
        active = 0

        async def loader() -> list[str]:
            nonlocal active
            active += 1
            started.set()
            await finish.wait()
            active -= 1
            return ["direct"]

        tasks = [
            asyncio.create_task(cache.get("sindhu:cctv:v1:latest:outage", loader))
            for _ in range(3)
        ]
        await started.wait()
        await asyncio.sleep(0.05)
        self.assertEqual(active, 2)
        self.assertTrue(any(task.done() for task in tasks))
        finish.set()
        results = await asyncio.gather(*tasks, return_exceptions=True)

        direct_results = [
            result for result in results if not isinstance(result, Exception)
        ]
        errors = [result for result in results if isinstance(result, CacheError)]
        self.assertEqual(len(direct_results), 2)
        self.assertTrue(
            all(result.error == "redis_unavailable" for result in direct_results)
        )
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0].code, "redis_unavailable")

    async def test_set_failure_returns_loader_once_and_keeps_lock_lease(self) -> None:
        redis = FakeRedis()
        redis.fail_data_set = True
        cache = CctvCache(redis)
        calls = 0

        async def loader() -> list[str]:
            nonlocal calls
            calls += 1
            return ["one"]

        result = await cache.get("sindhu:cctv:v1:latest:set-failure", loader)
        self.assertEqual(result.value, ["one"])
        self.assertEqual(result.error, "redis_unavailable")
        self.assertEqual(calls, 1)
        self.assertIn("sindhu:cctv:v1:latest:set-failure:lock", redis.values)

        with self.assertRaises(CacheError) as error:
            await cache.get("sindhu:cctv:v1:latest:set-failure", loader)
        self.assertEqual(error.exception.code, "cold_miss")
        self.assertEqual(calls, 1)

    async def test_cancellation_releases_only_current_owner_token(self) -> None:
        redis = FakeRedis()
        cache = CctvCache(redis)
        started = asyncio.Event()
        finish = asyncio.Event()

        async def loader() -> list[str]:
            started.set()
            await finish.wait()
            return ["cancelled"]

        task = asyncio.create_task(cache.get("sindhu:cctv:v1:latest:cancel", loader))
        await started.wait()
        lock_key = "sindhu:cctv:v1:latest:cancel:lock"
        owner_token = redis.values[lock_key]
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertNotIn(lock_key, redis.values)

        await cache.get("sindhu:cctv:v1:latest:cancel", lambda: ["new-owner"])
        self.assertNotEqual(redis.values.get(lock_key), owner_token)

    async def test_oversized_history_is_an_error_not_an_empty_success(self) -> None:
        redis = FakeRedis()
        cache = CctvCache(redis)
        calls = 0

        async def loader() -> dict[str, object]:
            nonlocal calls
            calls += 1
            return {"frames": [{"image_url": "x" * 70_000}]}

        key = "sindhu:cctv:v1:history:dwr:2026-09-02"
        with self.assertRaises(CacheError) as error:
            await cache.get(key, loader, max_bytes=262_144, stale_seconds=900)
        self.assertEqual(error.exception.code, "value_too_large")
        self.assertEqual(calls, 1)
        self.assertNotIn(key, redis.values)

        with self.assertRaises(CacheError) as cooldown_error:
            await cache.get(key, loader, max_bytes=262_144, stale_seconds=900)
        self.assertEqual(cooldown_error.exception.code, "value_too_large")
        self.assertEqual(calls, 1)


if __name__ == "__main__":
    unittest.main()
