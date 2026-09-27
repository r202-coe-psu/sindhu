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
from sindhu.services.cctv_catalog import (
    DWR_SOURCE,
    HATYAI_SOURCE,
    RID_SOURCE,
    get_camera,
    HATYAI_REGISTRY_VERSION,
    DWR_REGISTRY_VERSION,
    RID_REGISTRY_VERSION,
)
from sindhu.services.cctv_sources import CctvSources, SourceError, STALE_AFTER

UTC = dt.timezone.utc
BANGKOK = ZoneInfo("Asia/Bangkok")
SOURCES = (HATYAI_SOURCE, DWR_SOURCE, RID_SOURCE)
PREFIX = "sindhu:cctv:v1"
HISTORY_DAYS = 7
IMAGE_FRESHNESS_WINDOW = dt.timedelta(hours=24)
IMAGE_CHECK_TTL_SECONDS = int(IMAGE_FRESHNESS_WINDOW.total_seconds()) + 1
SNAPSHOT_CONCURRENCY = 2
SNAPSHOT_REQUEST_TIMEOUT_SECONDS = 30


class ViewerError(Exception):
    def __init__(self, code: str, status_code: int = 503):
        self.code, self.status_code = code, status_code
        super().__init__(code)


def image_freshness_for(
    feed: PublicVisualFeed, now: dt.datetime | None = None
) -> ImageFreshness:
    """Classify image evidence, not the upstream provider's health label."""
    checked_at = (
        feed.image_checked_at if feed.source == RID_SOURCE else feed.captured_at
    )
    image_url = feed.image_url
    if not image_url or not image_url.strip() or checked_at is None:
        return ImageFreshness.STALE
    if checked_at.tzinfo is None or checked_at.utcoffset() is None:
        return ImageFreshness.STALE

    current_time = now or dt.datetime.now(UTC)
    if current_time.tzinfo is None or current_time.utcoffset() is None:
        return ImageFreshness.STALE
    age = current_time.astimezone(UTC) - checked_at.astimezone(UTC)
    if dt.timedelta(0) <= age <= IMAGE_FRESHNESS_WINDOW:
        return ImageFreshness.FRESH
    return ImageFreshness.STALE


def validate_history_date(value: dt.date, now: dt.datetime | None = None) -> None:
    today = (now or dt.datetime.now(UTC)).astimezone(BANGKOK).date()
    if not today - dt.timedelta(days=HISTORY_DAYS - 1) <= value <= today:
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

        registry_version = {
            HATYAI_SOURCE: HATYAI_REGISTRY_VERSION,
            DWR_SOURCE: DWR_REGISTRY_VERSION,
            RID_SOURCE: RID_REGISTRY_VERSION,
        }[source]
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
        if source == RID_SOURCE:
            get_timestamp = getattr(self.cache, "get_timestamp", None)
            checked_at = (
                await asyncio.gather(
                    *(
                        get_timestamp(self._rid_check_key(feed.upstream_id))
                        for feed in feeds
                    ),
                    return_exceptions=True,
                )
                if callable(get_timestamp)
                else []
            )
            for feed, observation in zip(feeds, checked_at):
                feed.image_checked_at = (
                    observation if isinstance(observation, dt.datetime) else None
                )
        for feed in feeds:
            feed.image_freshness = image_freshness_for(feed, now)
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

    def _rid_check_key(self, upstream_id: str) -> str:
        return (
            f"{PREFIX}:image-check:{RID_SOURCE}:{RID_REGISTRY_VERSION}:"
            f"r{self._source_config_revision}:{upstream_id}"
        )

    async def get(self, source: str, upstream_id: str):
        if get_camera(source, upstream_id) is None:
            return None
        try:
            feeds, _ = await self._catalog(source)
        except (SourceError, CacheError):
            raise ViewerError("cctv_source_unavailable") from None
        return next((f for f in feeds if f.upstream_id == upstream_id), None)

    async def history(
        self, source: str, upstream_id: str, date: dt.date
    ) -> VisualFeedHistory:
        if get_camera(source, upstream_id) is None:
            raise ViewerError("visual_feed_not_found", 404)
        if source != HATYAI_SOURCE:
            raise ViewerError("history_not_supported", 400)
        validate_history_date(date)

        async def load():
            try:
                data = await self.sources.history(source, upstream_id, date)
                frames = [HistoryFrame.model_validate(f) for f in data["frames"]]
                if any(
                    f.captured_at.astimezone(BANGKOK).date() != date for f in frames
                ):
                    raise SourceError("history_date_mismatch")
                if len(frames) > 144:
                    raise SourceError("history_frame_limit")
                return {
                    "frames": [
                        f.model_dump(mode="json")
                        for f in sorted(frames, key=lambda f: f.captured_at)
                    ],
                    "possibly_truncated": bool(data.get("possibly_truncated", False)),
                }
            except (ValidationError, KeyError, TypeError):
                raise SourceError("invalid_history_contract") from None

        today = dt.datetime.now(UTC).astimezone(BANGKOK).date()
        ttl = 120 if date == today else 900
        try:
            cached = await self.cache.get(
                f"{PREFIX}:history:{source}:{upstream_id}:{date.isoformat()}",
                load,
                fresh_seconds=ttl,
                stale_seconds=ttl,
                max_bytes=65536,
            )
            return VisualFeedHistory(
                source=source,
                upstream_id=upstream_id,
                date=date,
                fetched_at=cached.fetched_at,
                **cached.value,
            )
        except (SourceError, CacheError, ValidationError):
            raise ViewerError("cctv_history_unavailable") from None

    async def snapshot(self, upstream_id: str) -> bytes:
        if get_camera(DWR_SOURCE, upstream_id) is None:
            raise ViewerError("visual_feed_not_found", 404)
        try:
            async with asyncio.timeout(SNAPSHOT_REQUEST_TIMEOUT_SECONDS):
                async with self._snapshot_semaphore:
                    return await self.sources.snapshot(upstream_id)
        except (SourceError, TimeoutError):
            raise ViewerError("snapshot_unavailable") from None

    async def rid_snapshot(self, upstream_id: str) -> tuple[bytes, str]:
        if get_camera(RID_SOURCE, upstream_id) is None:
            raise ViewerError("visual_feed_not_found", 404)
        try:
            async with asyncio.timeout(SNAPSHOT_REQUEST_TIMEOUT_SECONDS):
                async with self._snapshot_semaphore:
                    payload, media_type = await self.sources.rid_snapshot(upstream_id)
        except (SourceError, TimeoutError):
            raise ViewerError("snapshot_unavailable") from None
        checked_at = dt.datetime.now(UTC)
        set_timestamp = getattr(self.cache, "set_timestamp", None)
        if callable(set_timestamp):
            await set_timestamp(
                self._rid_check_key(upstream_id),
                checked_at,
                ttl_seconds=IMAGE_CHECK_TTL_SECONDS,
            )
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


async def get_snapshot(upstream_id):
    return await get_service().snapshot(upstream_id)


async def get_rid_snapshot(upstream_id):
    return await get_service().rid_snapshot(upstream_id)
