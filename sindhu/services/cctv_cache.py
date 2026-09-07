"""Small, request-driven cache for normalized CCTV metadata.

The cache deliberately stores only JSON metadata.  Images, provider payloads,
credentials, and exception text never enter Redis.  ``redis_client`` is
injected by the application; this class does not create connections or start
background work.
"""

from __future__ import annotations

import asyncio
import datetime as _datetime
import inspect
import json
import math
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TypeAlias

UTC = _datetime.timezone.utc
JSONValue: TypeAlias = list[Any] | dict[str, Any]
Clock: TypeAlias = Callable[[], _datetime.datetime]


ERROR_LOADER_FAILED = "loader_failed"
ERROR_REFRESH_TIMEOUT = "refresh_timeout"
ERROR_REDIS_UNAVAILABLE = "redis_unavailable"
ERROR_COLD_MISS = "cold_miss"
ERROR_VALUE_TOO_LARGE = "value_too_large"
ERROR_INVALID_VALUE = "invalid_value"
ERROR_CACHE_ERROR = "cache_error"

_SAFE_ERRORS = frozenset(
    {
        ERROR_LOADER_FAILED,
        ERROR_REFRESH_TIMEOUT,
        ERROR_REDIS_UNAVAILABLE,
        ERROR_COLD_MISS,
        ERROR_VALUE_TOO_LARGE,
        ERROR_INVALID_VALUE,
        ERROR_CACHE_ERROR,
    }
)

_ENVELOPE_VERSION = 1
_RELEASE_LOCK_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
end
return 0
"""


@dataclass(frozen=True, slots=True)
class CacheResult:
    """The result of a cache read or refresh.

    ``value`` is a JSON list or object when data is available.  A result with
    ``error`` and a value is an explicitly stale/error fallback; callers must
    not interpret it as a healthy refresh.  Cold failures raise
    :class:`CacheError` instead of returning ``None`` as a successful value.
    """

    value: JSONValue | None
    fetched_at: _datetime.datetime | None
    stale: bool = False
    error: str | None = None


class CacheError(RuntimeError):
    """A fixed, safe cache error code with no provider exception text."""

    def __init__(self, code: str):
        safe_code = code if code in _SAFE_ERRORS else ERROR_CACHE_ERROR
        self.code = safe_code
        super().__init__(safe_code)


@dataclass(frozen=True, slots=True)
class _Entry:
    value: JSONValue
    fetched_at: _datetime.datetime


@dataclass(frozen=True, slots=True)
class _Observation:
    redis_ok: bool
    entry: _Entry | None = None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class _LockHandle:
    key: str
    token: str | None = None
    redis_lock: Any | None = None


@dataclass(frozen=True, slots=True)
class _LoadOutcome:
    value: JSONValue | None = None
    fetched_at: _datetime.datetime | None = None
    error: str | None = None


class CctvCache:
    """Redis-backed stale-while-revalidate cache for CCTV JSON metadata.

    Constructor options are intentionally minimal and frozen by the service
    contract.  ``clock`` is the only optional keyword argument; it is a
    zero-argument callable returning an aware UTC ``datetime`` and exists for
    deterministic age tests.  Lock, deadline, cooldown, and direct-fallback
    limits are fixed constants below.
    """

    LOCK_TTL_SECONDS = 15
    REFRESH_DEADLINE_SECONDS = 10
    COLD_WAIT_SECONDS = 1.0
    ERROR_COOLDOWN_SECONDS = 30
    DIRECT_CAPACITY = 2
    HISTORY_MAX_BYTES = 65_536
    EMPTY_HISTORY_TTL_SECONDS = 120
    REDIS_OPERATION_TIMEOUT_SECONDS = 0.5

    def __init__(self, redis_client: Any, *, clock: Clock | None = None):
        self._redis = redis_client
        self._clock = clock or (lambda: _datetime.datetime.now(tz=UTC))
        self._direct_guard = asyncio.Lock()
        self._direct_inflight = 0

    async def get(
        self,
        key: str,
        loader: Callable[[], Any],
        fresh_seconds: float = 120,
        stale_seconds: float = 1800,
        max_bytes: int = 262_144,
    ) -> CacheResult:
        """Return fresh data, stale data while refreshing, or a loaded value.

        ``loader`` may return a JSON list/object.  For deterministic tests it
        may also return ``(value, fetched_at)`` or a successful
        :class:`CacheResult`; otherwise the cache clock supplies
        ``fetched_at``.  Loader exceptions are deliberately reduced to fixed
        error codes.
        """

        self._validate_request(key, fresh_seconds, stale_seconds, max_bytes)
        effective_max_bytes = self._effective_max_bytes(key, max_bytes)

        observation = await self._read(key)
        if not observation.redis_ok:
            return await self._direct_fetch(loader, effective_max_bytes)

        now = self._now()
        state = self._entry_state(
            observation.entry,
            now,
            fresh_seconds=fresh_seconds,
            stale_seconds=self._entry_stale_seconds(
                key, observation.entry, stale_seconds
            ),
        )
        if state == "fresh":
            return self._result(observation.entry, stale=False)
        if state == "stale" and observation.error is not None:
            return self._result(observation.entry, stale=True, error=observation.error)
        if state in {"cold", "expired"} and observation.error is not None:
            raise CacheError(observation.error)

        lock_status, lock_handle = await self._acquire_lock(key)
        if lock_status == "unavailable":
            return await self._direct_fetch(loader, effective_max_bytes)
        if lock_handle is None:
            if state == "stale":
                return self._result(observation.entry, stale=True)
            return await self._wait_for_cold(
                key,
                loader,
                fresh_seconds=fresh_seconds,
                stale_seconds=stale_seconds,
                max_bytes=effective_max_bytes,
            )

        release_lock = True
        try:
            # The first caller may have populated the key between the initial
            # read and SET NX.  Recheck after ownership is established.
            recheck = await self._read(key)
            if not recheck.redis_ok:
                # Keep the lock lease on a write/read outage.  This prevents a
                # second worker from running the same cold loader while Redis
                # is failing.  Cancellation still takes the normal release
                # path in finally.
                release_lock = False
                return await self._direct_fetch(loader, effective_max_bytes)

            now = self._now()
            rechecked_state = self._entry_state(
                recheck.entry,
                now,
                fresh_seconds=fresh_seconds,
                stale_seconds=self._entry_stale_seconds(
                    key, recheck.entry, stale_seconds
                ),
            )
            if rechecked_state == "fresh":
                return self._result(recheck.entry, stale=False)
            if rechecked_state == "stale" and recheck.error is not None:
                return self._result(recheck.entry, stale=True, error=recheck.error)
            if rechecked_state in {"cold", "expired"} and recheck.error is not None:
                raise CacheError(recheck.error)

            outcome = await self._run_loader(loader)
            if outcome.error is not None:
                marker_written = await self._write_error(key, outcome.error)
                if not marker_written:
                    # With no cooldown marker, retain the lease until its
                    # bounded TTL rather than allowing an immediate duplicate.
                    release_lock = False
                fallback_state = self._entry_state(
                    recheck.entry,
                    self._now(),
                    fresh_seconds=fresh_seconds,
                    stale_seconds=self._entry_stale_seconds(
                        key, recheck.entry, stale_seconds
                    ),
                )
                if fallback_state == "stale":
                    return self._result(recheck.entry, stale=True, error=outcome.error)
                raise CacheError(outcome.error)

            assert outcome.value is not None
            assert outcome.fetched_at is not None
            encoded = self._encode_data(
                outcome.value,
                outcome.fetched_at,
                max_bytes=effective_max_bytes,
            )
            if encoded is None:
                marker_written = await self._write_error(key, ERROR_VALUE_TOO_LARGE)
                if not marker_written:
                    release_lock = False
                fallback_state = self._entry_state(
                    recheck.entry,
                    self._now(),
                    fresh_seconds=fresh_seconds,
                    stale_seconds=self._entry_stale_seconds(
                        key, recheck.entry, stale_seconds
                    ),
                )
                if fallback_state == "stale":
                    return self._result(
                        recheck.entry,
                        stale=True,
                        error=ERROR_VALUE_TOO_LARGE,
                    )
                raise CacheError(ERROR_VALUE_TOO_LARGE)

            stored = await self._store_data(
                key,
                encoded,
                value=outcome.value,
                fetched_at=outcome.fetched_at,
                stale_seconds=stale_seconds,
            )
            if not stored:
                # The successful loader result is returned once.  Do not
                # release a possibly-live lease after SET failure: another
                # caller must not execute the loader a second time.
                release_lock = False
                return CacheResult(
                    value=outcome.value,
                    fetched_at=outcome.fetched_at,
                    stale=False,
                    error=ERROR_REDIS_UNAVAILABLE,
                )

            # A prior refresh failure must not survive a successful write.
            # Failure to delete it is surfaced as a safe cache warning, while
            # the newly written value remains a genuine fresh result.
            marker_deleted = await self._delete_error(key)
            return CacheResult(
                value=outcome.value,
                fetched_at=outcome.fetched_at,
                stale=False,
                error=None if marker_deleted else ERROR_REDIS_UNAVAILABLE,
            )
        finally:
            if release_lock:
                await self._release_lock(lock_handle)

    async def _wait_for_cold(
        self,
        key: str,
        loader: Callable[[], Any],
        *,
        fresh_seconds: float,
        stale_seconds: float,
        max_bytes: int,
    ) -> CacheResult:
        deadline = asyncio.get_running_loop().time() + self.COLD_WAIT_SECONDS
        while True:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                raise CacheError(ERROR_COLD_MISS)

            # Polling is bounded and creates no background task.  The owner
            # either publishes a value/error marker or its lock TTL expires.
            await asyncio.sleep(min(0.05, remaining))
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                raise CacheError(ERROR_COLD_MISS)
            try:
                observation = await asyncio.wait_for(self._read(key), timeout=remaining)
            except asyncio.TimeoutError:
                return await self._direct_fetch(loader, max_bytes)
            if not observation.redis_ok:
                return await self._direct_fetch(loader, max_bytes)

            state = self._entry_state(
                observation.entry,
                self._now(),
                fresh_seconds=fresh_seconds,
                stale_seconds=self._entry_stale_seconds(
                    key, observation.entry, stale_seconds
                ),
            )
            if state == "fresh":
                return self._result(observation.entry, stale=False)
            if state == "stale":
                return self._result(
                    observation.entry,
                    stale=True,
                    error=observation.error,
                )
            if observation.error is not None:
                raise CacheError(observation.error)

    async def _direct_fetch(
        self,
        loader: Callable[[], Any],
        max_bytes: int,
    ) -> CacheResult:
        entered = await self._try_enter_direct()
        if not entered:
            raise CacheError(ERROR_REDIS_UNAVAILABLE)
        try:
            outcome = await self._run_loader(loader)
            if outcome.error is not None:
                raise CacheError(outcome.error)
            assert outcome.value is not None
            assert outcome.fetched_at is not None
            if self._encode_data(outcome.value, outcome.fetched_at, max_bytes) is None:
                raise CacheError(ERROR_VALUE_TOO_LARGE)
            return CacheResult(
                value=outcome.value,
                fetched_at=outcome.fetched_at,
                stale=False,
                error=ERROR_REDIS_UNAVAILABLE,
            )
        finally:
            await self._leave_direct()

    async def _run_loader(self, loader: Callable[[], Any]) -> _LoadOutcome:
        try:
            loaded = loader()
            if inspect.isawaitable(loaded):
                loaded = await asyncio.wait_for(
                    loaded,
                    timeout=self.REFRESH_DEADLINE_SECONDS,
                )
        except asyncio.TimeoutError:
            return _LoadOutcome(error=ERROR_REFRESH_TIMEOUT)
        except Exception:
            return _LoadOutcome(error=ERROR_LOADER_FAILED)

        try:
            value, fetched_at = self._unpack_loader_result(loaded)
            self._json_bytes(value)
        except Exception:
            return _LoadOutcome(error=ERROR_INVALID_VALUE)
        return _LoadOutcome(value=value, fetched_at=fetched_at)

    def _unpack_loader_result(
        self, loaded: Any
    ) -> tuple[JSONValue, _datetime.datetime]:
        fetched_at: Any = self._now()
        value = loaded
        if isinstance(loaded, CacheResult):
            if loaded.error is not None or loaded.value is None:
                raise ValueError("loader result was not successful")
            value = loaded.value
            fetched_at = loaded.fetched_at or self._now()
        elif isinstance(loaded, tuple) and len(loaded) == 2:
            value, fetched_at = loaded

        if not isinstance(value, (list, dict)):
            raise ValueError("cache values must be JSON lists or objects")
        return value, self._as_utc(fetched_at)

    async def _read(self, key: str) -> _Observation:
        try:
            raw_data = await self._redis_call("get", key)
            raw_error = await self._redis_call("get", self._error_key(key))
        except Exception:
            return _Observation(redis_ok=False)

        entry = self._decode_data(raw_data)
        error = self._decode_error(raw_error)
        return _Observation(redis_ok=True, entry=entry, error=error)

    async def _acquire_lock(self, key: str) -> tuple[str, _LockHandle | None]:
        lock_key = self._lock_key(key)
        token = secrets.token_urlsafe(24)
        eval_method = getattr(self._redis, "eval", None)
        if callable(eval_method):
            try:
                acquired = await self._redis_call(
                    "set",
                    lock_key,
                    token,
                    nx=True,
                    ex=self.LOCK_TTL_SECONDS,
                )
            except Exception:
                return "unavailable", None
            if acquired:
                return "acquired", _LockHandle(key=lock_key, token=token)
            return "busy", None

        # Some small test doubles expose redis-py Lock but not EVAL.  The
        # redis-py implementation uses an owner-token compare/delete script.
        lock_factory = getattr(self._redis, "lock", None)
        if not callable(lock_factory):
            return "unavailable", None
        try:
            redis_lock = lock_factory(
                lock_key,
                timeout=self.LOCK_TTL_SECONDS,
                blocking=False,
                thread_local=False,
            )
            acquired = await self._maybe_await(
                redis_lock.acquire(blocking=False),
                timeout=self.REDIS_OPERATION_TIMEOUT_SECONDS,
            )
        except Exception:
            return "unavailable", None
        if acquired:
            return "acquired", _LockHandle(key=lock_key, redis_lock=redis_lock)
        return "busy", None

    async def _release_lock(self, handle: _LockHandle) -> None:
        try:
            if handle.redis_lock is not None:
                await self._maybe_await(
                    handle.redis_lock.release(),
                    timeout=self.REDIS_OPERATION_TIMEOUT_SECONDS,
                )
            elif handle.token is not None:
                await self._redis_call(
                    "eval",
                    _RELEASE_LOCK_SCRIPT,
                    1,
                    handle.key,
                    handle.token,
                )
        except Exception:
            # Expiry is safe: the compare/delete script (or redis-py Lock)
            # leaves a newer owner's lock untouched.
            return

    async def _store_data(
        self,
        key: str,
        encoded: str,
        *,
        value: JSONValue,
        fetched_at: _datetime.datetime,
        stale_seconds: float,
    ) -> bool:
        age = max(0.0, (self._now() - fetched_at).total_seconds())
        if self._is_empty_history(key, value):
            stale_seconds = min(stale_seconds, self.EMPTY_HISTORY_TTL_SECONDS)
        ttl = math.ceil(stale_seconds - age)
        if ttl <= 0:
            return False
        try:
            stored = await self._redis_call("set", key, encoded, ex=ttl)
        except Exception:
            return False
        return stored is not False

    async def _write_error(self, key: str, error: str) -> bool:
        if error not in _SAFE_ERRORS:
            error = ERROR_CACHE_ERROR
        payload = json.dumps(
            {"version": _ENVELOPE_VERSION, "error": error},
            separators=(",", ":"),
        )
        try:
            written = await self._redis_call(
                "set",
                self._error_key(key),
                payload,
                ex=self.ERROR_COOLDOWN_SECONDS,
            )
        except Exception:
            return False
        return written is not False

    async def _delete_error(self, key: str) -> bool:
        try:
            deleted = await self._redis_call("delete", self._error_key(key))
        except Exception:
            return False
        return deleted is not False

    async def _try_enter_direct(self) -> bool:
        async with self._direct_guard:
            if self._direct_inflight >= self.DIRECT_CAPACITY:
                return False
            self._direct_inflight += 1
            return True

    async def _leave_direct(self) -> None:
        async with self._direct_guard:
            self._direct_inflight = max(0, self._direct_inflight - 1)

    async def _redis_call(self, method_name: str, *args: Any, **kwargs: Any) -> Any:
        method = getattr(self._redis, method_name)
        return await self._maybe_await(
            method(*args, **kwargs),
            timeout=self.REDIS_OPERATION_TIMEOUT_SECONDS,
        )

    @staticmethod
    async def _maybe_await(value: Any, *, timeout: float | None = None) -> Any:
        if inspect.isawaitable(value):
            if timeout is None:
                return await value
            return await asyncio.wait_for(value, timeout=timeout)
        return value

    def _now(self) -> _datetime.datetime:
        return self._as_utc(self._clock())

    @staticmethod
    def _as_utc(value: Any) -> _datetime.datetime:
        if not isinstance(value, _datetime.datetime):
            raise ValueError("clock must return datetime")
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("clock datetime must be timezone-aware")
        return value.astimezone(UTC)

    @staticmethod
    def _validate_request(
        key: str,
        fresh_seconds: float,
        stale_seconds: float,
        max_bytes: int,
    ) -> None:
        if not isinstance(key, str) or not key:
            raise ValueError("key must be a non-empty canonical string")
        if fresh_seconds < 0 or stale_seconds < 0 or fresh_seconds > stale_seconds:
            raise ValueError("fresh_seconds must be between zero and stale_seconds")
        if not isinstance(max_bytes, int) or max_bytes <= 0:
            raise ValueError("max_bytes must be a positive integer")

    @classmethod
    def _effective_max_bytes(cls, key: str, max_bytes: int) -> int:
        parts = key.replace("/", ":").split(":")
        if "history" in {part.lower() for part in parts}:
            return min(max_bytes, cls.HISTORY_MAX_BYTES)
        return max_bytes

    @classmethod
    def _entry_stale_seconds(
        cls,
        key: str,
        entry: _Entry | None,
        stale_seconds: float,
    ) -> float:
        if entry is not None and cls._is_empty_history(key, entry.value):
            return min(stale_seconds, cls.EMPTY_HISTORY_TTL_SECONDS)
        return stale_seconds

    @classmethod
    def _is_empty_history(cls, key: str, value: JSONValue) -> bool:
        if "history" not in {part.lower() for part in key.replace("/", ":").split(":")}:
            return False
        return (
            isinstance(value, dict)
            and isinstance(value.get("frames"), list)
            and not value["frames"]
        )

    @staticmethod
    def _entry_state(
        entry: _Entry | None,
        now: _datetime.datetime,
        *,
        fresh_seconds: float,
        stale_seconds: float,
    ) -> str:
        if entry is None:
            return "cold"
        age = max(0.0, (now - entry.fetched_at).total_seconds())
        fresh_seconds = min(fresh_seconds, stale_seconds)
        if age < fresh_seconds:
            return "fresh"
        if age < stale_seconds:
            return "stale"
        return "expired"

    @staticmethod
    def _result(
        entry: _Entry | None,
        *,
        stale: bool,
        error: str | None = None,
    ) -> CacheResult:
        if entry is None:
            raise CacheError(ERROR_CACHE_ERROR)
        return CacheResult(
            value=entry.value,
            fetched_at=entry.fetched_at,
            stale=stale,
            error=error,
        )

    @staticmethod
    def _json_bytes(value: JSONValue) -> bytes:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")

    @classmethod
    def _encode_data(
        cls,
        value: JSONValue,
        fetched_at: _datetime.datetime,
        max_bytes: int,
    ) -> str | None:
        try:
            payload = {
                "version": _ENVELOPE_VERSION,
                "fetched_at": cls._timestamp(fetched_at),
                "value": value,
            }
            encoded = json.dumps(
                payload,
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
            ).encode("utf-8")
        except (TypeError, ValueError, OverflowError):
            return None
        if len(encoded) > max_bytes:
            return None
        return encoded.decode("utf-8")

    @staticmethod
    def _timestamp(value: _datetime.datetime) -> str:
        aware = CctvCache._as_utc(value)
        return aware.isoformat().replace("+00:00", "Z")

    @staticmethod
    def _decode_data(raw: Any) -> _Entry | None:
        try:
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            if not isinstance(raw, str) or not raw:
                return None
            payload = json.loads(raw)
            if not isinstance(payload, dict):
                return None
            if payload.get("version") != _ENVELOPE_VERSION:
                return None
            value = payload.get("value")
            if not isinstance(value, (list, dict)):
                return None
            fetched_at = CctvCache._as_utc(
                _datetime.datetime.fromisoformat(
                    payload["fetched_at"].replace("Z", "+00:00")
                )
            )
        except Exception:
            return None
        return _Entry(value=value, fetched_at=fetched_at)

    @staticmethod
    def _decode_error(raw: Any) -> str | None:
        try:
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            if not isinstance(raw, str) or not raw:
                return None
            payload = json.loads(raw)
            error = payload.get("error") if isinstance(payload, dict) else None
        except (TypeError, ValueError, UnicodeError, json.JSONDecodeError):
            return None
        return error if isinstance(error, str) and error in _SAFE_ERRORS else None

    @staticmethod
    def _lock_key(key: str) -> str:
        return f"{key}:lock"

    @staticmethod
    def _error_key(key: str) -> str:
        return f"{key}:error"


__all__ = [
    "CacheError",
    "CacheResult",
    "CctvCache",
]
