from typing import List
from pydantic import BaseModel, Field
from beanie import PydanticObjectId

from sindhu.schemas import bases
from sindhu.schemas.stations import Station as StationSchema


class BaseZone(BaseModel):
    name: str
    name_th: str | None = None
    code: str
    boundary: bases.GeoPolygon
    status: str = Field("active")
    metadata: dict | None = None


class CreateUpdateZone(BaseZone):
    station_ids: List[PydanticObjectId] = Field(default_factory=list)


class Zone(bases.BaseSchema, BaseZone):
    pass


class ZoneWithStations(Zone):
    stations: List[StationSchema] = Field(default_factory=list)


class ZoneList(BaseModel):
    zones: List[ZoneWithStations]


class LocateRequest(BaseModel):
    latitude: float
    longitude: float


class LocateResponse(BaseModel):
    zone: Zone | None = None
    nearby_stations: list = Field(default_factory=list)
    user_location: List[float]
