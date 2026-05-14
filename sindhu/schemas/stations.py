import datetime
from typing import Dict
from pydantic import BaseModel, Field, ConfigDict
from beanie import PydanticObjectId

from sindhu.schemas import bases

"""Abstract base class for all station documents."""


class BaseStation(BaseModel):
    name: str
    name_th: str | None

    code: str
    source: str
    url: str

    metadata: dict | None = None
    coordinates: bases.GeoObject
    # coordinates: Point
    status: str = Field("active")


class CreateUpdateStation(BaseStation):
    create_update_metadata: dict | None = Field(None, alias="metadata")


class StationMetaData(BaseModel):
    pass


"""MongoDB document model for a station."""


class Station(bases.BaseSchema, BaseStation):
    station_metadata: dict | None = Field(None, alias="metadata")
    created_date: datetime.datetime
    updated_date: datetime.datetime
    status: str


class StationList(BaseModel):
    stations: list[Station]