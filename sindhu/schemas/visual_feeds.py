from __future__ import annotations

import datetime
from enum import Enum
import re
from typing import Any, Dict, List, Literal
from urllib.parse import parse_qsl, urlsplit

from typing_extensions import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from sindhu.schemas import bases

UTC = datetime.timezone.utc
HATYAI_IMAGE_HOSTS = {
    "hatyaicityclimate.org",
    "www.hatyaicityclimate.org",
    "photo.hatyaicityclimate.org",
}


class MediaType(str, Enum):
    CCTV = "cctv"
    RADAR = "radar"
    SATELLITE = "satellite"
    WEATHER_MAP = "weather_map"


class CoordinateStatus(str, Enum):
    VERIFIED = "verified"
    UNVERIFIED = "unverified"
    NOT_APPLICABLE = "not_applicable"


class Availability(str, Enum):
    ONLINE = "online"
    STALE = "stale"
    DEGRADED = "degraded"
    OFFLINE = "offline"
    UNKNOWN = "unknown"


class SourceHealthStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    OFFLINE = "offline"
    UNKNOWN = "unknown"


def _as_utc(value: datetime.datetime | str | None) -> datetime.datetime | None:
    if value is None:
        return None

    if isinstance(value, str):
        value = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))

    if not isinstance(value, datetime.datetime):
        raise TypeError("timestamp must be a datetime or ISO-8601 string")

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must include an explicit timezone")

    return value.astimezone(UTC)


class GeoJSONPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str = Field(default="Point", pattern="^Point$")
    coordinates: List[float] = Field(min_length=2, max_length=2)

    @field_validator("coordinates")
    @classmethod
    def validate_coordinates(cls, value: List[float]) -> List[float]:
        longitude, latitude = value
        if not -180 <= longitude <= 180:
            raise ValueError("longitude must be between -180 and 180")
        if not -90 <= latitude <= 90:
            raise ValueError("latitude must be between -90 and 90")
        return value


class CoordinateProvenance(BaseModel):
    """Auditable evidence for a verified feed coordinate."""

    model_config = ConfigDict(extra="forbid")

    source: str = Field(min_length=1, max_length=200)
    method: str = Field(min_length=1, max_length=500)
    effective_date: datetime.date
    registry_version: str = Field(min_length=1, max_length=100)
    evidence_url: str | None = Field(default=None, max_length=2048)
    reference_url: str | None = Field(default=None, max_length=2048)

    @field_validator("evidence_url", "reference_url")
    @classmethod
    def validate_reference_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("reference URL must use http or https")
        return value

    @model_validator(mode="after")
    def require_auditable_reference(self) -> Self:
        if self.evidence_url is None and self.reference_url is None:
            raise ValueError(
                "coordinate provenance requires an evidence_url or reference_url"
            )
        return self


class VisualFeed(bases.BaseSchema):
    """A provider visual feed, independent from hydrological stations."""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        validate_default=True,
        extra="forbid",
    )

    source: str = Field(min_length=1, max_length=100)
    upstream_id: str = Field(min_length=1, max_length=200)
    code: str | None = Field(default=None, max_length=200)
    slug: str = Field(min_length=1, max_length=200)
    title_th: str = Field(min_length=1, max_length=500)
    coverage_group: str | None = Field(default=None, max_length=200)

    media_type: MediaType
    coordinate_status: CoordinateStatus = CoordinateStatus.UNVERIFIED
    coordinates: GeoJSONPoint | None = None
    coordinate_provenance: CoordinateProvenance | None = None

    availability: Availability = Availability.UNKNOWN
    image_url: str | None = None
    detail_url: str | None = None
    captured_at: datetime.datetime | None = None
    fetched_at: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(UTC)
    )
    provider_status: str | None = Field(default=None, max_length=500)
    attribution: Dict[str, Any] = Field(default_factory=dict)
    raw_payload: Dict[str, Any] = Field(default_factory=dict)
    registry_version: str | None = Field(default=None, max_length=100)
    last_seen_at: datetime.datetime | None = None
    created_at: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(UTC)
    )
    updated_at: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(UTC)
    )

    @field_validator("upstream_id", mode="before")
    @classmethod
    def normalize_upstream_id(cls, value: Any) -> str:
        if value is None:
            raise ValueError("upstream_id is required")
        return str(value)

    @field_validator("image_url", "detail_url")
    @classmethod
    def validate_http_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("URL must use http or https")
        return value

    @model_validator(mode="after")
    def validate_visual_feed_contract(self) -> Self:
        if self.coordinate_status == CoordinateStatus.VERIFIED:
            if self.coordinates is None or not self.coordinate_provenance:
                raise ValueError(
                    "verified coordinates require coordinates and provenance"
                )
            if not self.registry_version:
                raise ValueError("verified coordinates require registry_version")
            if self.coordinate_provenance.registry_version != self.registry_version:
                raise ValueError(
                    "coordinate provenance registry_version must match feed registry_version"
                )
        elif self.coordinates is not None:
            raise ValueError("unverified coordinates must not be published")

        if self.media_type != MediaType.CCTV:
            if self.coordinate_status != CoordinateStatus.NOT_APPLICABLE:
                raise ValueError("non-CCTV feeds must use not_applicable coordinates")
            if self.coordinates is not None:
                raise ValueError("non-CCTV feeds must not publish coordinates")

        if self.source == "hatyai_city_climate" and self.image_url:
            if (
                urlsplit(self.image_url).hostname or ""
            ).lower() not in HATYAI_IMAGE_HOSTS:
                raise ValueError("Hatyai image URL host is not allowlisted")
        return self

    @field_validator(
        "captured_at",
        "fetched_at",
        "last_seen_at",
        "created_at",
        "updated_at",
        mode="before",
    )
    @classmethod
    def normalize_timestamps(
        cls, value: datetime.datetime | str | None
    ) -> datetime.datetime | None:
        return _as_utc(value)


class SourceHealth(BaseModel):
    source: str
    status: SourceHealthStatus
    total: int = Field(ge=0)
    online: int = Field(default=0, ge=0)
    stale: int = Field(default=0, ge=0)
    degraded: int = Field(default=0, ge=0)
    offline: int = Field(default=0, ge=0)
    unknown: int = Field(default=0, ge=0)
    latest_fetched_at: datetime.datetime | None = None

    @field_validator("latest_fetched_at", mode="before")
    @classmethod
    def normalize_latest_fetched_at(
        cls, value: datetime.datetime | str | None
    ) -> datetime.datetime | None:
        return _as_utc(value)


class VisualFeedList(BaseModel):
    visual_feeds: List[VisualFeed] = Field(default_factory=list)
    count: int = Field(ge=0)
    generated_at: datetime.datetime
    source_health: Dict[str, SourceHealth] = Field(default_factory=dict)

    @field_validator("generated_at", mode="before")
    @classmethod
    def normalize_generated_at(
        cls, value: datetime.datetime | str
    ) -> datetime.datetime:
        normalized = _as_utc(value)
        if normalized is None:
            raise ValueError("generated_at is required")
        return normalized


# Public request-driven DTOs intentionally do not inherit the legacy Mongo
# schema: raw_payload, open-ended attribution and storage IDs must not escape.
def public_cctv_url(value: str | None, *, image: bool = False) -> str | None:
    if value is None:
        return None
    if len(value) > 2048 or any(ord(c) < 33 for c in value) or "\\" in value:
        raise ValueError("invalid CCTV URL")
    parsed = urlsplit(value)
    if parsed.username is not None or parsed.password is not None or parsed.fragment:
        raise ValueError("CCTV URL must not contain credentials or a fragment")
    if any(
        k != "v" or not v.isdigit()
        for k, v in parse_qsl(parsed.query, keep_blank_values=True)
    ):
        raise ValueError("CCTV URL query is not allowlisted")
    if not parsed.scheme and not parsed.netloc:
        if image and re.fullmatch(
            r"/v1/visual-feeds/dwr/[0-9a-fA-F-]{36}/snapshot", parsed.path
        ):
            return value
        raise ValueError("relative CCTV URL is not allowed")
    allowed_hosts = (
        HATYAI_IMAGE_HOSTS if image else HATYAI_IMAGE_HOSTS | {"telemetry.dwr.go.th"}
    )
    if (
        parsed.scheme != "https"
        or parsed.hostname not in allowed_hosts
        or parsed.port not in (None, 443)
    ):
        raise ValueError("CCTV URL host is not allowlisted")
    return value


class PublicAttribution(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: str = Field(max_length=200)
    source_url: str

    @field_validator("source_url")
    @classmethod
    def safe_source(cls, value: str) -> str:
        return public_cctv_url(value)


class PublicVisualFeed(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: Literal["hatyai_city_climate", "dwr"]
    upstream_id: str = Field(min_length=1, max_length=200)
    slug: str = Field(min_length=1, max_length=200)
    title_th: str = Field(min_length=1, max_length=500)
    code: str | None = Field(default=None, max_length=200)
    coverage_group: str | None = Field(default=None, max_length=200)
    media_type: Literal["cctv"] = "cctv"
    coordinate_status: CoordinateStatus = CoordinateStatus.UNVERIFIED
    coordinates: GeoJSONPoint | None = None
    coordinate_provenance: CoordinateProvenance | None = None
    registry_version: str | None = None
    availability: Availability = Availability.UNKNOWN
    provider_status: str | None = Field(default=None, max_length=100)
    image_url: str | None = None
    detail_url: str | None = None
    captured_at: datetime.datetime | None = None
    fetched_at: datetime.datetime
    history_supported: bool = False
    attribution: PublicAttribution

    @field_validator("captured_at", "fetched_at", mode="before")
    @classmethod
    def utc_time(cls, value):
        return _as_utc(value)

    @field_validator("image_url")
    @classmethod
    def safe_image(cls, value):
        return public_cctv_url(value, image=True)

    @field_validator("detail_url")
    @classmethod
    def safe_detail(cls, value):
        return public_cctv_url(value)

    @model_validator(mode="after")
    def public_contract(self) -> Self:
        if self.history_supported and self.source != "hatyai_city_climate":
            raise ValueError("only Hatyai history is supported")
        if self.coordinate_status == CoordinateStatus.VERIFIED:
            if self.coordinates is None or self.coordinate_provenance is None:
                raise ValueError("verified coordinates need evidence")
            if (
                not self.registry_version
                or self.registry_version != self.coordinate_provenance.registry_version
            ):
                raise ValueError("coordinate registry version mismatch")
            for url in (
                self.coordinate_provenance.evidence_url,
                self.coordinate_provenance.reference_url,
            ):
                public_cctv_url(url)
        elif self.coordinates is not None:
            raise ValueError("unverified coordinates must not be published")
        if self.image_url:
            path = urlsplit(self.image_url).path
            if (
                self.source == "dwr"
                and path != f"/v1/visual-feeds/dwr/{self.upstream_id}/snapshot"
            ):
                raise ValueError("DWR images must use this camera's proxy")
            if self.source == "hatyai_city_climate" and not self.image_url.startswith(
                "https://"
            ):
                raise ValueError("Hatyai image must be upstream HTTPS")
        return self


class PublicSourceHealth(SourceHealth):
    cache_stale: bool = False
    error: str | None = Field(default=None, max_length=100, pattern=r"^[a-z0-9_]+$")


class PublicVisualFeedList(BaseModel):
    model_config = ConfigDict(extra="forbid")
    visual_feeds: List[PublicVisualFeed] = Field(default_factory=list)
    count: int = Field(ge=0)
    generated_at: datetime.datetime
    source_health: Dict[str, PublicSourceHealth] = Field(default_factory=dict)

    @field_validator("generated_at", mode="before")
    @classmethod
    def utc_time(cls, value):
        return _as_utc(value)


class HistoryFrame(BaseModel):
    model_config = ConfigDict(extra="forbid")
    captured_at: datetime.datetime
    image_url: str
    thumbnail_url: str | None = None

    @field_validator("captured_at", mode="before")
    @classmethod
    def utc_time(cls, value):
        return _as_utc(value)

    @field_validator("image_url", "thumbnail_url")
    @classmethod
    def safe_image(cls, value):
        value = public_cctv_url(value, image=True)
        if value is not None and not value.startswith("https://"):
            raise ValueError("history must use upstream Hatyai images")
        return value


class VisualFeedHistory(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: Literal["hatyai_city_climate"]
    upstream_id: str
    date: datetime.date
    timezone: Literal["Asia/Bangkok"] = "Asia/Bangkok"
    frames: List[HistoryFrame] = Field(default_factory=list, max_length=144)
    fetched_at: datetime.datetime
    possibly_truncated: bool = False

    @field_validator("fetched_at", mode="before")
    @classmethod
    def utc_time(cls, value):
        return _as_utc(value)


__all__ = [
    "Availability",
    "CoordinateProvenance",
    "CoordinateStatus",
    "GeoJSONPoint",
    "MediaType",
    "SourceHealth",
    "SourceHealthStatus",
    "VisualFeed",
    "VisualFeedList",
]
