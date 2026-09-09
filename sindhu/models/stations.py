from typing import Optional, Tuple
from pydantic import Field
from beanie import Document, Indexed, PydanticObjectId

import datetime
import pymongo
from sindhu.schemas.stations import Station as StationSchema


class Station(StationSchema, Document):
    id: PydanticObjectId = Field(
        default_factory=PydanticObjectId,
        alias="_id",
    )

    created_date: datetime.datetime = Field(default_factory=datetime.datetime.now)
    updated_date: datetime.datetime = Field(default_factory=datetime.datetime.now)

    class Settings:
        name = "stations"
        indexes = [[("coordinates", pymongo.GEOSPHERE)]]  # GEO index
