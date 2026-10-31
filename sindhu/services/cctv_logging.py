"""Server-side log lines for CCTV failures.

Callers keep returning the same stable public error codes; these helpers only
record why on the server.  Provider exception messages can echo request URLs,
so a log line carries the context, the public code, the original exception
type and, for bugs, where it was raised — never an exception message.  Repeats
of the same failure are held back so an outage cannot flood the log.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
import traceback

import httpx
from pydantic import ValidationError
from redis.exceptions import RedisError

from sindhu.services.cctv_errors import SourceError

logger = logging.getLogger(__name__)

# An outage fails every request the same way; log each distinct failure at most
# once per interval, with how many repeats were held back.
REPEAT_INTERVAL_SECONDS = 60.0
_last_logged: dict[tuple[str, ...], float] = {}
_held_back: dict[tuple[str, ...], int] = {}

# Failures of a provider or of Redis, as opposed to a bug in this code.
EXTERNAL_ERRORS: tuple[type[BaseException], ...] = (
    httpx.HTTPError,
    OSError,
    TimeoutError,
    RedisError,
    ValidationError,
)


def root_cause(error: BaseException) -> BaseException:
    """Follow ``raise ... from`` and implicit chaining to the first exception.

    ``raise SourceError(...) from None`` only hides the chain when printed;
    ``__context__`` still holds the original exception.  Cancellation is a
    signal, not a cause: a timed-out ``wait_for`` chains to it.
    """

    seen = {id(error)}
    while True:
        cause = error.__cause__ or error.__context__
        if (
            cause is None
            or id(cause) in seen
            or isinstance(cause, asyncio.CancelledError)
        ):
            return error
        seen.add(id(cause))
        error = cause


def raised_at(error: BaseException) -> str:
    frames = traceback.extract_tb(error.__traceback__)
    if not frames:
        return "unknown"
    frame = frames[-1]
    return f"{os.path.basename(frame.filename)}:{frame.lineno} in {frame.name}"


def is_external(error: BaseException) -> bool:
    return isinstance(error, (SourceError, *EXTERNAL_ERRORS))


def _repeats_since_last_log(signature: tuple[str, ...]) -> int | None:
    """None while ``signature`` was logged recently, else the repeats held back."""

    now = time.monotonic()
    last = _last_logged.get(signature)
    if last is not None and now - last < REPEAT_INTERVAL_SECONDS:
        _held_back[signature] = _held_back.get(signature, 0) + 1
        return None
    _last_logged[signature] = now
    return _held_back.pop(signature, 0)


def reset_repeat_limit() -> None:
    _last_logged.clear()
    _held_back.clear()


def log_failure(context: str, code: str, error: BaseException) -> None:
    """Log one failure that is about to become the public error ``code``."""

    code = getattr(error, "code", code)
    cause = root_cause(error)
    external = is_external(cause)
    location = "" if external else raised_at(cause)
    repeats = _repeats_since_last_log((code, type(cause).__name__, location))
    if repeats is None:
        return
    if external:
        logger.warning(
            "CCTV %s failed: code=%s cause=%s repeats=%d",
            context,
            code,
            type(cause).__name__,
            repeats,
        )
    else:
        logger.error(
            "CCTV %s hit a bug: code=%s cause=%s raised_at=%s repeats=%d",
            context,
            code,
            type(cause).__name__,
            location,
            repeats,
        )


__all__ = [
    "is_external",
    "log_failure",
    "raised_at",
    "reset_repeat_limit",
    "root_cause",
]
