from pydantic import Field
from beanie import Document, PydanticObjectId
import datetime
from .. import schemas


class Caches(schemas.caches.BaseCache, Document):
    id: PydanticObjectId = Field(
        default_factory=PydanticObjectId,
        alias="_id",
    )
    created_date: datetime.datetime = Field(default_factory=datetime.datetime.now)
    updated_date: datetime.datetime = Field(default_factory=datetime.datetime.now)

    class Settings:
        name = "caches"
