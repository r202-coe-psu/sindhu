import asyncio
import os
import unittest
import uuid

try:
    import redis.asyncio as redis
except ImportError:  # pragma: no cover - dependency is part of the app install
    redis = None

from sindhu.services.cctv_cache import CctvCache

REDIS_URL = os.environ.get("CCTV_TEST_REDIS_URL")


@unittest.skipUnless(
    REDIS_URL and redis is not None,
    "set CCTV_TEST_REDIS_URL to run the optional Redis integration test",
)
class CctvCacheRedisIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        assert REDIS_URL is not None
        assert redis is not None
        self.redis = redis.from_url(REDIS_URL, decode_responses=False)
        try:
            await self.redis.ping()
        except Exception:
            await self.redis.aclose()
            self.skipTest("CCTV_TEST_REDIS_URL is set but Redis is unavailable")
        self.prefix = f"sindhu:cctv:integration:{uuid.uuid4().hex}:"

    async def asyncTearDown(self) -> None:
        # Delete only this test's unique namespace; never flush the selected DB.
        try:
            keys = [key async for key in self.redis.scan_iter(match=f"{self.prefix}*")]
            if keys:
                await self.redis.delete(*keys)
        finally:
            await self.redis.aclose()

    async def test_two_cache_instances_share_one_loader_refresh(self) -> None:
        key = f"{self.prefix}latest:hatyai_city_climate"
        first = CctvCache(self.redis)
        second = CctvCache(self.redis)
        started = asyncio.Event()
        finish = asyncio.Event()
        calls = 0

        async def loader() -> list[dict[str, str]]:
            nonlocal calls
            calls += 1
            started.set()
            await finish.wait()
            return [{"source": "hatyai_city_climate", "upstream_id": "1"}]

        owner = asyncio.create_task(first.get(key, loader))
        await started.wait()
        waiter = asyncio.create_task(second.get(key, loader))
        await asyncio.sleep(0.05)
        finish.set()
        owner_result, waiter_result = await asyncio.gather(owner, waiter)

        self.assertEqual(owner_result.value, waiter_result.value)
        self.assertEqual(calls, 1)
        self.assertFalse(owner_result.stale)
        self.assertFalse(waiter_result.stale)


if __name__ == "__main__":
    unittest.main()
