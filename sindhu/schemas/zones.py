from typing import List
from pydantic import BaseModel, Field

from sindhu.schemas import bases


class BaseZone(BaseModel):
    name: str
    name_th: str | None = None
    code: str
    boundary: bases.GeoPolygon
    station_codes: List[str] = Field(default_factory=list)
    status: str = Field("active")
    metadata: dict | None = None


class CreateUpdateZone(BaseZone):
    pass


class Zone(bases.BaseSchema, BaseZone):
    pass


class ZoneList(BaseModel):
    zones: List[Zone]


class ZoneWithStations(Zone):
    stations: list = Field(default_factory=list)


class LocateRequest(BaseModel):
    latitude: float
    longitude: float


class LocateResponse(BaseModel):
    zone: Zone | None = None
    nearby_stations: list = Field(default_factory=list)
    user_location: List[float]
