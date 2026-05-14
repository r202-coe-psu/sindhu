from beanie import Document, PydanticObjectId
from datetime import datetime, timezone
from pydantic import Field

from sindhu import schemas


class ApiToken(schemas.tokens.ApiToken, Document):
    id: PydanticObjectId = Field(
        default_factory=PydanticObjectId,
        alias="_id",
    )

    created_date: datetime | None = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_date: datetime | None = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "api_tokens"