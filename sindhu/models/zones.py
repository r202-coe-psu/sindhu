import datetime

from pydantic import Field
from beanie import Document, PydanticObjectId
import pymongo

from sindhu import schemas


class Zone(schemas.zones.Zone, Document):
    id: PydanticObjectId = Field(
        default_factory=PydanticObjectId,
        alias="_id",
    )

    created_date: datetime.datetime = Field(default_factory=datetime.datetime.now)
    updated_date: datetime.datetime = Field(default_factory=datetime.datetime.now)

    class Settings:
        name = "zones"
        indexes = [[("boundary", pymongo.GEOSPHERE)]]
