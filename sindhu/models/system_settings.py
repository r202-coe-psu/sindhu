import datetime
from typing import Optional, Tuple


from beanie import Document, Indexed, PydanticObjectId, Link
from pydantic import Field, BaseModel
from typing import List

from ..schemas.system_settings import SystemSetting as SystemSettingSchema
from . import tokens


class SystemSetting(SystemSettingSchema, Document):
    created_date: datetime.datetime = Field(default_factory=datetime.datetime.now)
    updated_date: datetime.datetime = Field(default_factory=datetime.datetime.now)
    api_tokens: List[Link[tokens.ApiToken]] = []

    class Settings:
        name = "system_settings"
