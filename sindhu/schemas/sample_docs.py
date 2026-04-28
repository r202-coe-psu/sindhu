import datetime

from pydantic import BaseModel, EmailStr, Field
from typing import List, Optional
from beanie import PydanticObjectId

# from ..models import GeoObject
from . import bases


class BaseSampleDocs(BaseModel):
    pass


class SampleDocs(bases.BaseSchema, BaseSampleDocs):
    created_date: datetime.datetime
    updated_date: datetime.datetime
