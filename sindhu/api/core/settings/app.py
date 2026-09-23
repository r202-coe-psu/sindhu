import logging
import os
import sys
from typing import Any, Dict, List, Tuple
import urllib.parse

from loguru import logger
from pydantic import field_validator
from pydantic_settings import SettingsConfigDict

from sindhu.api.core.logging import InterceptHandler
from sindhu.api.core.settings.base import BaseAppSettings
from sindhu.config.provider_urls import (
    DEFAULT_DWR_CCTV_BASE_URL,
    DEFAULT_HATYAI_CCTV_BASE_URL,
    DEFAULT_RID_CCTV_BASE_URL,
    validate_allowed_api_base_url,
)


def sanitize_mongo_uri(uri: str) -> str:
    if not uri or not ("mongodb://" in uri or "mongodb+srv://" in uri):
        return uri
    scheme_sep = "://"
    scheme, remainder = uri.split(scheme_sep, 1)
    if "@" not in remainder:
        return uri
    host_db_idx = remainder.find("/")
    if host_db_idx == -1:
        host_db_idx = remainder.find("?")
    if host_db_idx != -1:
        user_host_part = remainder[:host_db_idx]
        rest = remainder[host_db_idx:]
    else:
        user_host_part = remainder
        rest = ""

    last_at = user_host_part.rfind("@")
    if last_at == -1:
        return uri

    userinfo = user_host_part[:last_at]
    hostpart = user_host_part[last_at + 1 :]

    if ":" in userinfo:
        user, password = userinfo.split(":", 1)
        quoted_user = urllib.parse.quote_plus(urllib.parse.unquote(user))
        quoted_pass = urllib.parse.quote_plus(urllib.parse.unquote(password))
        return f"{scheme}://{quoted_user}:{quoted_pass}@{hostpart}{rest}"
    return uri


class AppSettings(BaseAppSettings):
    DEBUG: bool = False
    DOCS_URL: str = "/docs"
    OPENAPI_PREFIX: str = ""
    OPENAPI_URL: str = "/openapi.json"
    REDOC_URL: str = "/redoc"
    TITLE: str = os.getenv("APP_TITLE", os.getenv("PROJECT_NAME", "แลน้ำ"))
    VERSION: str = "0.0.2"

    MONGODB_URI: str = "mongodb://localhost/sindhudb"

    @field_validator("MONGODB_URI", mode="before")
    @classmethod
    def validate_mongodb_uri(cls, v: str) -> str:
        return sanitize_mongo_uri(v)

    # MONGODB_DB: str = "sindhudb"
    # MONGODB_HOST: str = "localhost"
    # MONGODB_PORT: int = 27017
    # MONGODB_USERNAME: str = ""
    # MONGODB_PASSWORD: str = ""

    REDIS_URL: str = "redis://localhost:6379"

    SECRET_KEY: str = "secret"

    API_PREFIX: str = ""
    ROOT_PATH: str = ""

    JWT_TOKEN_PREFIX: str = "Token"

    ACCESS_TOKEN_EXPIRE_MINUTES: int = 24 * 60  # 1 day
    REFRESH_TOKEN_EXPIRE_MINUTES: int = 7 * 24 * 60  # 7 days

    ALLOWED_HOSTS: List[str] = ["*"]

    # Keep provider endpoints configurable for proxy, mirror, and test setups.
    HATYAI_CCTV_API_BASE_URL: str = DEFAULT_HATYAI_CCTV_BASE_URL
    DWR_CCTV_API_BASE_URL: str = DEFAULT_DWR_CCTV_BASE_URL
    RID_CCTV_API_BASE_URL: str = DEFAULT_RID_CCTV_BASE_URL

    @field_validator(
        "HATYAI_CCTV_API_BASE_URL",
        "DWR_CCTV_API_BASE_URL",
        "RID_CCTV_API_BASE_URL",
    )
    @classmethod
    def validate_cctv_api_base_url(cls, value: str) -> str:
        return validate_allowed_api_base_url(value, allow_custom_hosts=True)

    LOGGING_LEVEL: int = logging.INFO
    LOGGERS: Tuple[str, str] = ("uvicorn.asgi", "uvicorn.access")

    model_config = SettingsConfigDict(
        env_file=os.getenv("ENV_FILE", ".env"),
        extra="allow",
        validate_assignment=True,
    )

    @property
    def fastapi_kwargs(self) -> Dict[str, Any]:
        return {
            "debug": self.DEBUG,
            "docs_url": self.DOCS_URL,
            "openapi_prefix": self.OPENAPI_PREFIX,
            "openapi_url": self.OPENAPI_URL,
            "redoc_url": self.REDOC_URL,
            "title": self.TITLE,
            "version": self.VERSION,
            "root_path": self.ROOT_PATH,
        }

    def configure_logging(self) -> None:
        logging.getLogger().handlers = [InterceptHandler()]
        for logger_name in self.LOGGERS:
            logging_logger = logging.getLogger(logger_name)
            logging_logger.handlers = [InterceptHandler(level=self.LOGGING_LEVEL)]

        logger.configure(handlers=[{"sink": sys.stderr, "level": self.LOGGING_LEVEL}])
