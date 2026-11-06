import datetime
from typing import List

from beanie import Document, PydanticObjectId
from pydantic import Field
import pymongo


class Tambon(Document):
    id: PydanticObjectId = Field(
        default_factory=PydanticObjectId,
        alias="_id",
    )

    code: str
    name_th: str
    amphoe_th: str | None = None
    batch_id: str
    # GeoJSON Polygon or MultiPolygon dict
    boundary: dict
    zone_ids: List[str] = Field(default_factory=list)

    created_date: datetime.datetime = Field(default_factory=datetime.datetime.now)

    class Settings:
        name = "tambons"
        indexes = [
            [("boundary", pymongo.GEOSPHERE)],
            pymongo.IndexModel(
                [("batch_id", pymongo.ASCENDING), ("code", pymongo.ASCENDING)],
                unique=True,
                name="uq_tambons_batch_code",
            ),
        ]
