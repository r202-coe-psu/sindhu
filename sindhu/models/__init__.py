# import motor.motor_asyncio
import sys
from typing import Sequence, Type, TypeVar
from inspect import getmembers, isclass
import beanie
import pymongo
from pydantic_settings import BaseSettings

from sindhu.models.users import User
from sindhu.models.stations import Station
from sindhu.models.zones import Zone
from sindhu.models.system_settings import SystemSetting
from sindhu.models.tokens import ApiToken
from sindhu.models.logs import RequestLog

from sindhu.models.telemetrices.metric import Metric

DocumentType = TypeVar("DocumentType", bound=beanie.Document)


class AppSettings(BaseSettings):
    MONGODB_URI: str = "mongodb://host.docker.internal:27017/sindhudb"

    class Config:
        env_file = ".env"
        extra = "allow"


async def gather_documents() -> Sequence[Type[beanie.Document]]:
    """Returns a list of all MongoDB document models defined in `models` module."""

    class_models = getmembers(sys.modules[__name__], isclass)

    for key in [k for k in sys.modules if __name__ in k]:
        class_models.extend(getmembers(sys.modules[key], isclass))

    class_models = list(set(class_models))

    return [
        doc
        for _, doc in class_models
        if issubclass(doc, beanie.Document) and doc.__name__ != "Document"
    ]


import urllib.parse


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


class BeanieClient:
    async def init_beanie(self, settings):
        self.settings = settings
        uri = sanitize_mongo_uri(getattr(settings, "MONGODB_URI", ""))
        self.client = pymongo.AsyncMongoClient(uri)
        self.db = self.client.get_default_database()

        documents = await gather_documents()

        print("Documents >>>")
        for document in documents:
            print(document)

        await beanie.init_beanie(
            database=self.db,
            document_models=documents,
            # recreate_views=True,
        )


async def init_beanie(app, settings):
    await beanie_client.init_beanie(settings)


async def init_default_beanie_client():
    """
    Initializes the Beanie client with default settings.
    For MageAI integration
    """
    settings = AppSettings()
    print("setings>>>", settings)
    await beanie_client.init_beanie(settings)


beanie_client = BeanieClient()
