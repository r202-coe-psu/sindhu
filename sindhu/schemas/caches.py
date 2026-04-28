import datetime
import enum
import string
from typing import Any
from pydantic import BaseModel


class CacheType(str, enum.Enum):
    string = "string"
    geojson = "geojson"


class BaseCache(BaseModel):
    key: str
    type: CacheType
    value: dict
    created_date: datetime.datetime
    updated_date: datetime.datetime
