from fastapi import APIRouter
from loguru import logger

from sindhu import services
from sindhu.api.core import caching

router = APIRouter(prefix="/interpolations", tags=["interpolations"])

CACHE_EXPIRE_SECONDS = 1800


@router.get("/rain")
async def rain(source: str | None = None, method: str | None = None) -> dict:
    method = method or services.interpolations.DEFAULT_METHOD
    key = f"sindhu:interpolations:rain:{source or 'all'}:{method}"

    result = await caching.redis_client.json().get(key)
    if result:
        logger.info(f"[CACHE] {key} HIT.")
        return result

    logger.info(f"[CACHE] {key} MISS. Calculating....")
    result = await services.interpolations.get_rain_interpolation(source, method)

    # Skip caching an empty surface so new rain data shows up on the next call
    if result["interpolation"]:
        await caching.redis_client.json().set(key, "$", result)
        await caching.redis_client.expire(key, CACHE_EXPIRE_SECONDS)

    return result
