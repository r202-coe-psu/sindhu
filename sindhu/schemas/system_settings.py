import datetime

from pydantic import BaseModel, EmailStr, Field
from typing import List
from beanie import PydanticObjectId

# from ..models import GeoObject
from . import bases
from . import tokens


class BaseSystemSetting(BaseModel):
    center: bases.GeoObject | None = None
    interpolation_coordinate_1: bases.GeoObject | None = None
    interpolation_coordinate_2: bases.GeoObject | None = None
    zoom: int | None = None
    min_zoom: int | None = None


class SystemSetting(BaseSystemSetting):
    pass


class SystemSettingResponse(SystemSetting):
    api_tokens: List[tokens.ApiToken]
    created_date: datetime.datetime
    updated_date: datetime.datetime


class CreateSystemSetting(BaseSystemSetting):
    pass


class UpdateSystemSetting(BaseSystemSetting):
    pass