import datetime
from typing import List

from pydantic import Field
from beanie import Document, PydanticObjectId, Link
import pymongo

from sindhu.schemas.zones import Zone as ZoneSchema
from .stations import Station as StationModel


class Zone(ZoneSchema, Document):
    id: PydanticObjectId = Field(
        default_factory=PydanticObjectId,
        alias="_id",
    )

    stations: List[Link[StationModel]] = []

    created_date: datetime.datetime = Field(default_factory=datetime.datetime.now)
    updated_date: datetime.datetime = Field(default_factory=datetime.datetime.now)

    class Settings:
        name = "zones"
        indexes = [[("boundary", pymongo.GEOSPHERE)]]
