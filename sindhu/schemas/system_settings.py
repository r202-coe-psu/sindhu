import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
from typing import List, Optional
from beanie import PydanticObjectId

# from ..models import GeoObject
from . import bases
from . import tokens
from sindhu.config.provider_urls import validate_allowed_api_base_url


class BaseSystemSetting(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    center: Optional[bases.GeoObject] = None
    interpolation_coordinate_1: Optional[bases.GeoObject] = None
    interpolation_coordinate_2: Optional[bases.GeoObject] = None
    zoom: Optional[int] = None
    min_zoom: Optional[int] = None
    hatyai_cctv_api_base_url: Optional[str] = None
    dwr_cctv_api_base_url: Optional[str] = None
    rid_cctv_api_base_url: Optional[str] = None

    @field_validator(
        "hatyai_cctv_api_base_url",
        "dwr_cctv_api_base_url",
        "rid_cctv_api_base_url",
        mode="before",
    )
    @classmethod
    def validate_provider_base_urls(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        return validate_allowed_api_base_url(value)


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
