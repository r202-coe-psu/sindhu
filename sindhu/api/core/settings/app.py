import logging
import sys
from typing import Any, Dict, List, Tuple
import urllib.parse

from loguru import logger
from pydantic import field_validator

from sindhu.api.core.logging import InterceptHandler
from sindhu.api.core.settings.base import BaseAppSettings


ALLOWED_PUBLIC_API_HOSTS = frozenset(
    {
        "hatyaicityclimate.org",
        "www.hatyaicityclimate.org",
        "photo.hatyaicityclimate.org",
        "telemetry.dwr.go.th",
    }
)
ALLOWED_LOCAL_API_HOSTS = frozenset(
    {"localhost", "127.0.0.1", "host.docker.internal"}
)


def validate_allowed_api_base_url(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("API base URL must be a string")
    raw = value.strip()
    if not raw or len(raw) > 2048:
        raise ValueError("API base URL must be a non-empty URL")
    try:
        parsed = urllib.parse.urlsplit(raw)
        hostname = parsed.hostname
        parsed.port
    except ValueError as error:
        raise ValueError("API base URL is malformed") from error
    if (
        parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or any(ord(char) < 33 for char in raw)
        or "\\" in raw
    ):
        raise ValueError(
            "API base URL cannot contain credentials, query, fragment, or backslash"
        )
    if not hostname:
        raise ValueError("API base URL must include a hostname")
    hostname = hostname.lower()
    if hostname in ALLOWED_LOCAL_API_HOSTS:
        if parsed.scheme.lower() != "http":
            raise ValueError("Local API base URLs must use http")
    elif hostname in ALLOWED_PUBLIC_API_HOSTS:
        if parsed.scheme.lower() != "https":
            raise ValueError("Public API base URLs must use https")
    else:
        raise ValueError("API base URL host is not allowed")
    return urllib.parse.urlunsplit(
        (parsed.scheme.lower(), parsed.netloc.lower(), parsed.path.rstrip("/"), "", "")
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
    TITLE: str = "sindhu"
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

    # Provider origins are configurable so deployments can use a proxy or a
    # mirror without changing request-time adapter code.  The defaults retain
    # the public endpoints used by the checked-in CCTV catalog.
    HATYAI_CCTV_API_BASE_URL: str = "https://hatyaicityclimate.org"
    DWR_CCTV_API_BASE_URL: str = "https://telemetry.dwr.go.th/api"

    @field_validator("HATYAI_CCTV_API_BASE_URL", "DWR_CCTV_API_BASE_URL")
    @classmethod
    def validate_cctv_api_base_url(cls, value: str) -> str:
        return validate_allowed_api_base_url(value)

    LOGGING_LEVEL: int = logging.INFO
    LOGGERS: Tuple[str, str] = ("uvicorn.asgi", "uvicorn.access")

    class Config:
        validate_assignment = True

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
