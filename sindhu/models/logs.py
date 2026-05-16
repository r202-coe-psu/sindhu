from beanie import Document, Link
from pydantic import Field
from datetime import datetime, timezone
from typing import Optional
from .users import User

class RequestLog(Document):
    user: Optional[Link[User]] = None
    ip_address: str
    action: str
    user_agent: str
    created_date: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "request_logs"
