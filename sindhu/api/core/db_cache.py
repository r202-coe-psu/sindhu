"""
Database cache decorator for wrapping async functions with automatic caching logic.

Usage:
    @db_cache(cache_type="geojson", expire_hours=6)
    async def my_function(arg1, arg2, ...):
        # Your logic here
        return result
"""

import functools
import inspect
import datetime
from typing import Callable, Any, Optional, Type
from loguru import logger
import json


def db_cache(
    cache_type: str = "geojson",
    expire_hours: int = 24,
    key_builder: Optional[Callable] = None,
):
    """
    Decorator for caching async function results in the database.

    Args:
        cache_type: Type of cache (e.g., "geojson", "string"). Default: "geojson"
        expire_hours: Cache expiration time in hours. Default: 24
        key_builder: Optional callable to build cache key from function args.
                    If None, auto-generates key from function name and args.

    Example:
        @db_cache(cache_type="geojson", expire_hours=6)
        async def get_interpolated_data(source: str, formula: str):
            # Your expensive computation here
            return result
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # Import here to avoid circular imports
            from sindhu import models

            # Generate cache key
            if key_builder:
                cache_key = key_builder(*args, **kwargs)
            else:
                cache_key = _default_key_builder(func.__name__, *args, **kwargs)

            try:
                # Check if cache exists and is not expired
                cached = await models.Caches.find_one(
                    {
                        "key": cache_key,
                        "updated_date": {
                            "$gte": datetime.datetime.now(datetime.timezone.utc)
                            - datetime.timedelta(hours=expire_hours)
                        },
                    }
                )

                if cached:
                    logger.debug(f"Cache hit for key: {cache_key}")
                    return cached.value

                # Cache miss - call the actual function
                logger.debug(f"Cache miss for key: {cache_key}, computing...")
                result = await func(*args, **kwargs)

                # Store/update cache
                await _update_or_create_cache(cache_key, result, cache_type.lower())

                return result

            except Exception as e:
                logger.warning(
                    f"Cache operation failed for key: {cache_key}. Error: {e}"
                )
                # If cache fails, still try to call the function
                return await func(*args, **kwargs)

        return wrapper

    return decorator


def db_cache_conditional(
    cache_type: str = "geojson",
    expire_hours: int = 24,
    key_builder: Optional[Callable] = None,
    should_cache: Optional[Callable] = None,
):
    """
    Decorator with conditional caching logic.

    Args:
        cache_type: Type of cache (e.g., "geojson", "string"). Default: "geojson"
        expire_hours: Cache expiration time in hours. Default: 24
        key_builder: Optional callable to build cache key from function args.
        should_cache: Optional condition function(result, *args, **kwargs) -> bool
                     If provided, only caches result if returns True.

    Example:
        def cache_if_valid(result, **kwargs):
            return result is not None

        @db_cache_conditional(
            cache_type="geojson",
            expire_hours=6,
            should_cache=cache_if_valid
        )
        async def get_data(source: str):
            return result
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # Import here to avoid circular imports
            from sindhu import models

            # Generate cache key
            if key_builder:
                cache_key = key_builder(*args, **kwargs)
            else:
                cache_key = _default_key_builder(func.__name__, *args, **kwargs)

            try:
                # Check if cache exists and is not expired
                cached = await models.Caches.find_one(
                    {
                        "key": cache_key,
                        "updated_date": {
                            "$gte": datetime.datetime.now(datetime.timezone.utc)
                            - datetime.timedelta(hours=expire_hours)
                        },
                    }
                )

                if cached:
                    logger.debug(f"Cache hit for key: {cache_key}")
                    return cached.value

                # Cache miss - call the actual function
                logger.debug(f"Cache miss for key: {cache_key}, computing...")
                result = await func(*args, **kwargs)

                # Decide whether to cache based on should_cache callable
                should_cache_result = True
                if should_cache:
                    should_cache_result = should_cache(result, *args, **kwargs)

                if should_cache_result:
                    await _update_or_create_cache(cache_key, result, cache_type.lower())

                return result

            except Exception as e:
                logger.warning(
                    f"Cache operation failed for key: {cache_key}. Error: {e}"
                )
                return await func(*args, **kwargs)

        return wrapper

    return decorator


def _default_key_builder(func_name: str, *args, **kwargs) -> str:
    """
    Build a cache key from function name and arguments.
    Filters out 'self' and 'cls' parameters.
    """
    key_parts = [func_name]

    # Add positional arguments (skip 'self' and 'cls')
    for i, arg in enumerate(args):
        if i == 0 and (isinstance(arg, type) or hasattr(arg, "__dict__")):
            # Skip self/cls
            continue
        key_parts.append(str(arg))

    # Add keyword arguments
    for k, v in sorted(kwargs.items()):
        key_parts.append(f"{k}:{v}")

    return ":".join(key_parts)


async def _update_or_create_cache(
    cache_key: str,
    value: Any,
    cache_type: str,
) -> None:
    """
    Update existing cache or create a new one.
    """
    from sindhu import models

    try:
        # Check if cache already exists
        existing_cache = await models.Caches.find_one(models.Caches.key == cache_key)

        if existing_cache:
            # Update existing cache
            logger.debug(f"Updating existing cache: {cache_key}")
            await existing_cache.update(
                {
                    "$set": {
                        "value": value,
                        "type": cache_type,
                        "updated_date": datetime.datetime.now(datetime.timezone.utc),
                    }
                }
            )
        else:
            # Create new cache entry
            logger.debug(f"Creating new cache entry: {cache_key}")
            new_cache = models.Caches(
                key=cache_key,
                value=value,
                type=cache_type,
                updated_date=datetime.datetime.now(datetime.timezone.utc),
            )
            await new_cache.insert()

        logger.debug(f"Successfully cached/updated: {cache_key}")

    except Exception as e:
        logger.error(f"Failed to update/create cache for key: {cache_key}. Error: {e}")
        raise


async def invalidate_cache(cache_key: str) -> bool:
    """
    Manually invalidate (delete) a cache entry by key.

    Args:
        cache_key: The cache key to invalidate

    Returns:
        True if cache was deleted, False if not found
    """
    from sindhu import models

    try:
        result = await models.Caches.find_one(models.Caches.key == cache_key)
        if result:
            await result.delete()
            logger.debug(f"Invalidated cache: {cache_key}")
            return True
        return False
    except Exception as e:
        logger.error(f"Failed to invalidate cache for key: {cache_key}. Error: {e}")
        return False


async def invalidate_cache_pattern(pattern: str) -> int:
    """
    Invalidate multiple cache entries matching a pattern (regex).

    Args:
        pattern: Regex pattern to match cache keys

    Returns:
        Number of cache entries deleted
    """
    from sindhu import models

    try:
        result = await models.Caches.find({"key": {"$regex": pattern}}).delete()
        logger.debug(f"Invalidated {result} cache entries matching pattern: {pattern}")
        return result
    except Exception as e:
        logger.error(f"Failed to invalidate cache with pattern: {pattern}. Error: {e}")
        return 0
