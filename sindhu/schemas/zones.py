from typing import List, Literal
from pydantic import BaseModel, Field, field_validator
from beanie import PydanticObjectId

from sindhu.schemas import bases
from sindhu.schemas.stations import Station as StationSchema


def normalize_tambon_name(value) -> str:
    """A tambon tag as its bare Thai name.

    Strips whitespace and a leading "ต." / "ตำบล" so "ต.คอหงส์" and "คอหงส์"
    are the same tag. A dict from older data contributes its name_th.
    """
    if isinstance(value, dict):
        value = value.get("name_th") or ""
    name = str(value or "").strip()
    for prefix in ("ตำบล", "ต."):
        if name.startswith(prefix):
            name = name[len(prefix) :].strip()
            break
    return name


def normalize_tambon_names(values) -> List[str]:
    """Non-empty, de-duplicated tambon names in their given order."""
    names = []
    for value in values or []:
        name = normalize_tambon_name(value)
        if name and name not in names:
            names.append(name)
    return names


class BaseZone(BaseModel):
    name: str
    name_th: str | None = None
    code: str
    boundary: bases.GeoPolygon
    zone_kind: Literal["flood", "reference"] = "flood"
    status: str = Field("active")
    # Tambon names this zone covers. Plain tags kept by an admin; a tambon
    # that straddles zones is listed in each of them.
    tambons: List[str] = Field(default_factory=list)
    metadata: dict | None = None

    @field_validator("tambons", mode="before")
    @classmethod
    def _normalize_tambons(cls, v):
        return normalize_tambon_names(v)


class CreateUpdateZone(BaseZone):
    station_ids: List[PydanticObjectId] = Field(default_factory=list)


class Zone(bases.BaseSchema, BaseZone):
    pass


class ZoneWithStations(Zone):
    stations: List[StationSchema] = Field(default_factory=list)


class ZoneList(BaseModel):
    zones: List[ZoneWithStations]


class ZoneStationList(BaseModel):
    stations: list = Field(default_factory=list)


class LocateRequest(BaseModel):
    latitude: float
    longitude: float


class LocateResponse(BaseModel):
    zone: Zone | None = None
    nearby_stations: list = Field(default_factory=list)
    user_location: List[float]
