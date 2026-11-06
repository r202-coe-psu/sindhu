from typing import List, Literal
from pydantic import BaseModel, Field, field_validator
from beanie import PydanticObjectId

from sindhu.schemas import bases
from sindhu.schemas.stations import Station as StationSchema
from sindhu.schemas.tambons import TambonRef, TambonSummary, coerce_tambon_ref


class BaseZone(BaseModel):
    name: str
    name_th: str | None = None
    code: str
    boundary: bases.GeoPolygon
    zone_kind: Literal["flood", "reference"] = "flood"
    status: str = Field("active")
    tambons: List[TambonRef] = Field(default_factory=list)
    metadata: dict | None = None

    @field_validator("tambons", mode="before")
    @classmethod
    def _legacy_tambons(cls, v):
        if v is None:
            return []
        return [coerce_tambon_ref(t) for t in v]


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
    tambon: TambonSummary | None = None
