from datetime import datetime, timezone
from typing import List

from .. import schemas

from beanie import Document, Indexed, PydanticObjectId
from pydantic import Field

# from passlib.context import CryptContext

# pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class User(schemas.users.User, Document):
    # id: PydanticObjectId = Field(
    #     default_factory=PydanticObjectId,
    #     alias="_id",
    # )

    password: str
    roles: List[str] = ["user"]
    status: str = "active"

    register_date: datetime | None = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_date: datetime | None = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "users"

    async def has_roles(self, roles):
        return any(role in self.roles for role in roles)

    def set_password(self, password):
        from werkzeug.security import generate_password_hash

        self.password = generate_password_hash(password)

    def verify_password(self, password):
        from werkzeug.security import check_password_hash

        if check_password_hash(self.password, password):
            return True
        return False