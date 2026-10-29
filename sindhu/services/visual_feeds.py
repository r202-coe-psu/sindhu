"""Request-driven CCTV viewer. No Mongo reads/writes or periodic jobs."""

from __future__ import annotations

import asyncio
import datetime as dt
from collections import Counter
from zoneinfo import ZoneInfo

import httpx
from pydantic import ValidationError

from sindhu.schemas.visual_feeds import (
    Availability,
    HistoryFrame,
    ImageFreshness,
    MediaType,
    PublicSourceHealth,
    PublicVisualFeed,
    SourceHealthStatus,
    VisualFeedHistory,
)
from sindhu.services.cctv_cache import CacheError, CctvCache
from sindhu.services.cctv_logging import log_failure
from sindhu.services.cctv_catalog import (
    DWR_SOURCE,
    RID_SOURCE,
    get_camera,
    HATYAI_REGISTRY_VERSION,  # noqa: F401  (re-exported; tests read service.HATYAI_REGISTRY_VERSION)
)
from sindhu.services.cctv_providers import PROVIDER_BY_SOURCE, SOURCES
from sindhu.services.cctv_sources import (
    MAX_HISTORY_FRAMES,
    STALE_AFTER,
    CctvSources,
    SourceError,
)

UTC = dt.timezone.utc
BANGKOK = ZoneInfo("Asia/Bangkok")
PREFIX = "sindhu:cctv:v1"
# Hatyai photographs every 30 minutes, DWR and RID more often: a camera that
# has missed an hour of updates is not online, whatever its provider says.
IMAGE_FRESHNESS_WINDOW = dt.timedelta(hours=1)
# Camera clocks can run a little ahead of ours; such an image is still fresh.
CLOCK_SKEW_ALLOWANCE = dt.timedelta(minutes=5)
SNAPSHOT_CONCURRENCY = 2
HISTORY_CACHE_SECONDS = 600  # the provider adds a photo every 30 minutes
SNAPSHOT_REQUEST_TIMEOUT_SECONDS = 30


class ViewerError(Exception):
    def __init__(self, code: str, status_code: int = 503):
        self.code, self.status_code = code, status_code
        super().__init__(code)


def is_recent(captured_at: dt.datetime | None, now: dt.datetime | None = None) -> bool:
    """The one rule for "still updating", shared by badges and history.

    Only the capture time of an image counts; provider health labels
    (Hatyai's flag stays green for cameras that stopped months ago) do not.
    """
    if captured_at is None or captured_at.utcoffset() is None:
        return False
    current_time = now or dt.datetime.now(UTC)
    if current_time.utcoffset() is None:
        return False
    age = current_time.astimezone(UTC) - captured_at.astimezone(UTC)
    return -CLOCK_SKEW_ALLOWANCE <= age <= IMAGE_FRESHNESS_WINDOW


def image_freshness_for(
    feed: PublicVisualFeed, now: dt.datetime | None = None
) -> ImageFreshness:
    """A camera is online when it has an image captured recently."""
    if not feed.image_url or not feed.image_url.strip():
        return ImageFreshness.STALE
    if is_recent(feed.captured_at, now):
        return ImageFreshness.FRESH
    return ImageFreshness.STALE


def validate_history_date(value: dt.date, now: dt.datetime | None = None) -> None:
    today = (now or dt.datetime.now(UTC)).astimezone(BANGKOK).date()
    if value > today:
        raise ViewerError("history_date_out_of_range", 422)


def build_source_health(feeds: list[PublicVisualFeed]) -> dict[str, PublicSourceHealth]:
    result = {}
    for source in dict.fromkeys(feed.source for feed in feeds):
        group = [feed for feed in feeds if feed.source == source]
        counts = Counter(feed.availability.value for feed in group)
        if counts["unknown"] == len(group):
            status = SourceHealthStatus.UNKNOWN
        elif counts["offline"] == len(group):
            status = SourceHealthStatus.OFFLINE
        elif counts["online"] == len(group):
            status = SourceHealthStatus.HEALTHY
        else:
            status = SourceHealthStatus.DEGRADED
        result[source] = PublicSourceHealth(
            source=source,
            status=status,
            total=len(group),
            **counts,
            latest_fetched_at=max(feed.fetched_at for feed in group),
        )
    return result


class VisualFeedService:
    def __init__(
        self,
        client: httpx.AsyncClient,
        redis_client,
        *,
        sources=None,
        cache=None,
        hatyai_base_url: str | None = None,
        dwr_base_url: str | None = None,
        hatyai_api_base_url: str | None = None,
        dwr_api_base_url: str | None = None,
        rid_base_url: str | None = None,
        rid_api_base_url: str | None = None,
    ):
        self.sources = (
            sources
            if sources is not None
            else CctvSources(
                client,
                hatyai_base_url=hatyai_base_url,
                dwr_base_url=dwr_base_url,
                hatyai_api_base_url=hatyai_api_base_url,
                dwr_api_base_url=dwr_api_base_url,
                rid_base_url=rid_base_url,
                rid_api_base_url=rid_api_base_url,
            )
        )
        self.cache = cache if cache is not None else CctvCache(redis_client)
        self._snapshot_semaphore = asyncio.Semaphore(SNAPSHOT_CONCURRENCY)
        self._source_config_revision = 0

    def reconfigure_sources(
        self,
        *,
        hatyai_base_url: str | None = None,
        dwr_base_url: str | None = None,
        rid_base_url: str | None = None,
    ) -> None:
        """Apply provider base URL overrides without replacing the HTTP client."""
        if not isinstance(self.sources, CctvSources):
            raise RuntimeError("cannot reconfigure custom visual feed sources")
        self.sources = CctvSources(
            self.sources.client,
            clock=self.sources.clock,
            deadline_seconds=self.sources.deadline_seconds,
            hatyai_base_url=hatyai_base_url,
            dwr_base_url=dwr_base_url,
            rid_base_url=rid_base_url,
        )
        # Avoid serving catalog data fetched from the previous provider URL.
        self._source_config_revision += 1

    async def _catalog(self, source: str):
        async def load():
            try:
                records = await self.sources.latest(source)
                normalized = [PublicVisualFeed.model_validate(r) for r in records]
                if not normalized or any(
                    feed.source != source
                    or get_camera(source, feed.upstream_id) is None
                    for feed in normalized
                ):
                    raise SourceError("invalid_source_identity")
                if len({feed.upstream_id for feed in normalized}) != len(normalized):
                    raise SourceError("duplicate_source_identity")
                return [feed.model_dump(mode="json") for feed in normalized]
            except ValidationError:
                raise SourceError("invalid_source_contract") from None

        provider = PROVIDER_BY_SOURCE[source]
        registry_version = provider.registry_version
        cached = await self.cache.get(
            f"{PREFIX}:latest:{source}:{registry_version}:r{self._source_config_revision}",
            load,
            fresh_seconds=120,
            stale_seconds=1800,
            max_bytes=262144,
        )
        now = dt.datetime.now(UTC)
        try:
            feeds = [PublicVisualFeed.model_validate(r) for r in cached.value]
        except (ValidationError, TypeError):
            raise ViewerError("invalid_cache_data") from None
        for feed in feeds:
            # Judged when the provider was asked, so time spent in our cache
            # does not turn a working camera offline.
            feed.image_freshness = image_freshness_for(feed, feed.fetched_at)
            if feed.availability == Availability.OFFLINE:
                continue
            if feed.captured_at is None or feed.captured_at > now + dt.timedelta(
                minutes=5
            ):
                feed.availability = Availability.UNKNOWN
            elif now - feed.captured_at > STALE_AFTER:
                feed.availability = Availability.STALE
        health = build_source_health(feeds).get(
            source,
            PublicSourceHealth(
                source=source,
                status=SourceHealthStatus.UNKNOWN,
                total=0,
            ),
        )
        health.cache_stale = cached.stale
        if cached.error:
            health.error = "source_refresh_failed"
        if cached.stale or cached.error:
            health.status = SourceHealthStatus.DEGRADED
        return feeds, health

    async def list(
        self,
        *,
        media_type=None,
        coverage_group=None,
        availability=None,
        has_coordinates=None,
    ):
        if media_type is not None and media_type != MediaType.CCTV:
            return [], {}
        results = await asyncio.gather(
            *(self._catalog(s) for s in SOURCES), return_exceptions=True
        )
        feeds, health = [], {}
        succeeded = False
        for source, outcome in zip(SOURCES, results):
            if isinstance(outcome, BaseException):
                if isinstance(outcome, asyncio.CancelledError):
                    raise outcome
                health[source] = PublicSourceHealth(
                    source=source,
                    total=0,
                    status=SourceHealthStatus.DEGRADED,
                    error="source_unavailable",
                )
                continue
            group, state = outcome
            feeds.extend(group)
            health[source] = state
            succeeded = True
        if not succeeded:
            raise ViewerError("cctv_sources_unavailable")
        filtered = [
            f
            for f in feeds
            if (coverage_group is None or f.coverage_group == coverage_group)
            and (availability is None or f.availability == availability)
            and (
                has_coordinates is None
                or (f.coordinates is not None) == has_coordinates
            )
        ]
        return sorted(filtered, key=lambda f: (f.source, f.slug)), health

    async def get(self, source: str, upstream_id: str):
        if get_camera(source, upstream_id) is None:
            return None
        try:
            feeds, _ = await self._catalog(source)
        except (SourceError, CacheError) as error:
            log_failure(f"{source} catalog", "cctv_source_unavailable", error)
            raise ViewerError("cctv_source_unavailable") from None
        return next((f for f in feeds if f.upstream_id == upstream_id), None)

    async def history(
        self, source: str, upstream_id: str, date: dt.date | None = None
    ) -> VisualFeedHistory:
        """Return one camera's latest photo set, optionally narrowed to a day."""
        if get_camera(source, upstream_id) is None:
            raise ViewerError("visual_feed_not_found", 404)
        if not PROVIDER_BY_SOURCE[source].history_supported:
            raise ViewerError("history_not_supported", 400)
        if date is not None:
            validate_history_date(date)

        async def load():
            try:
                data = await self.sources.history(source, upstream_id)
                frames = [HistoryFrame.model_validate(f) for f in data["frames"]]
                if len(frames) > MAX_HISTORY_FRAMES:
                    raise SourceError("history_frame_limit")
                return {
                    "frames": [
                        f.model_dump(mode="json")
                        for f in sorted(frames, key=lambda f: f.captured_at)
                    ],
                    "available_dates": data.get("available_dates", []),
                    "possibly_truncated": bool(data.get("possibly_truncated", False)),
                }
            except (ValidationError, KeyError, TypeError):
                raise SourceError("invalid_history_contract") from None

        try:
            # One provider call per camera serves every day in its photo set.
            cached = await self.cache.get(
                f"{PREFIX}:history:{source}:{upstream_id}",
                load,
                fresh_seconds=HISTORY_CACHE_SECONDS,
                stale_seconds=HISTORY_CACHE_SECONDS,
                max_bytes=CctvCache.HISTORY_MAX_BYTES,
            )
            value = cached.value
            frames = value["frames"]
            # Range of everything the provider returned, before the day filter.
            oldest = frames[0]["captured_at"] if frames else None
            latest = frames[-1]["captured_at"] if frames else None
            history_stale = latest is not None and not is_recent(
                dt.datetime.fromisoformat(latest), cached.fetched_at
            )
            if date is not None:
                frames = [
                    frame
                    for frame in frames
                    if dt.datetime.fromisoformat(frame["captured_at"])
                    .astimezone(BANGKOK)
                    .date()
                    == date
                ]
            return VisualFeedHistory(
                source=source,
                upstream_id=upstream_id,
                date=date,
                fetched_at=cached.fetched_at,
                frames=frames,
                available_dates=value["available_dates"],
                oldest_captured_at=oldest,
                latest_captured_at=latest,
                history_stale=history_stale,
                possibly_truncated=value["possibly_truncated"],
            )
        except (SourceError, CacheError, ValidationError, KeyError, ValueError) as error:
            log_failure(f"{source} history", "cctv_history_unavailable", error)
            raise ViewerError("cctv_history_unavailable") from None

    async def snapshot_token(self, upstream_id: str) -> str | None:
        """Identity of the current DWR image (its dated path); one cheap upstream call."""
        if get_camera(DWR_SOURCE, upstream_id) is None:
            raise ViewerError("visual_feed_not_found", 404)
        try:
            async with asyncio.timeout(SNAPSHOT_REQUEST_TIMEOUT_SECONDS):
                async with self._snapshot_semaphore:
                    return await self.sources.snapshot_token(upstream_id)
        except (SourceError, TimeoutError) as error:
            log_failure(f"{DWR_SOURCE} snapshot token", "snapshot_unavailable", error)
            raise ViewerError("snapshot_unavailable") from None

    async def snapshot(self, upstream_id: str, token: str | None = None) -> bytes:
        if get_camera(DWR_SOURCE, upstream_id) is None:
            raise ViewerError("visual_feed_not_found", 404)
        try:
            async with asyncio.timeout(SNAPSHOT_REQUEST_TIMEOUT_SECONDS):
                async with self._snapshot_semaphore:
                    return await self.sources.snapshot(upstream_id, token)
        except (SourceError, TimeoutError) as error:
            log_failure(f"{DWR_SOURCE} snapshot", "snapshot_unavailable", error)
            raise ViewerError("snapshot_unavailable") from None

    async def rid_snapshot(self, upstream_id: str) -> tuple[bytes, str]:
        if get_camera(RID_SOURCE, upstream_id) is None:
            raise ViewerError("visual_feed_not_found", 404)
        try:
            async with asyncio.timeout(SNAPSHOT_REQUEST_TIMEOUT_SECONDS):
                async with self._snapshot_semaphore:
                    payload, media_type = await self.sources.rid_snapshot(upstream_id)
        except (SourceError, TimeoutError) as error:
            log_failure(f"{RID_SOURCE} snapshot", "snapshot_unavailable", error)
            raise ViewerError("snapshot_unavailable") from None
        return payload, media_type


_service: VisualFeedService | None = None


def configure_visual_feeds(
    client: httpx.AsyncClient,
    redis_client,
    *,
    hatyai_base_url: str | None = None,
    dwr_base_url: str | None = None,
    hatyai_api_base_url: str | None = None,
    dwr_api_base_url: str | None = None,
    rid_base_url: str | None = None,
    rid_api_base_url: str | None = None,
) -> None:
    global _service
    _service = VisualFeedService(
        client,
        redis_client,
        hatyai_base_url=hatyai_base_url,
        dwr_base_url=dwr_base_url,
        hatyai_api_base_url=hatyai_api_base_url,
        dwr_api_base_url=dwr_api_base_url,
        rid_base_url=rid_base_url,
        rid_api_base_url=rid_api_base_url,
    )


def close_visual_feeds() -> None:
    global _service
    _service = None


def reconfigure_visual_feeds(
    *,
    hatyai_api_base_url: str | None = None,
    dwr_api_base_url: str | None = None,
    rid_api_base_url: str | None = None,
) -> None:
    service = get_service()
    service.reconfigure_sources(
        hatyai_base_url=hatyai_api_base_url,
        dwr_base_url=dwr_api_base_url,
        rid_base_url=rid_api_base_url,
    )


def get_service() -> VisualFeedService:
    if _service is None:
        raise ViewerError("cctv_not_initialized")
    return _service


async def list_visual_feeds(**kwargs):
    return await get_service().list(**kwargs)


async def get_visual_feed(source, upstream_id):
    return await get_service().get(source, upstream_id)


async def get_history(source, upstream_id, date):
    return await get_service().history(source, upstream_id, date)


async def get_snapshot_token(upstream_id):
    return await get_service().snapshot_token(upstream_id)


async def get_snapshot(upstream_id, token=None):
    return await get_service().snapshot(upstream_id, token)


async def get_rid_snapshot(upstream_id):
    return await get_service().rid_snapshot(upstream_id)
