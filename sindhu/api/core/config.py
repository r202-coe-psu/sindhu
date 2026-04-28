from functools import lru_cache
from typing import Dict, Type

from sindhu.api.core.settings.app import AppSettings
from sindhu.api.core.settings.base import AppEnvTypes, BaseAppSettings
from sindhu.api.core.settings.development import DevAppSettings
from sindhu.api.core.settings.production import ProdAppSettings
from sindhu.api.core.settings.test import TestAppSettings

environments: Dict[AppEnvTypes, Type[AppSettings]] = {
    AppEnvTypes.dev: DevAppSettings,
    AppEnvTypes.prod: ProdAppSettings,
    AppEnvTypes.test: TestAppSettings,
}


@lru_cache
def get_app_settings() -> AppSettings:
    app_env = BaseAppSettings().APP_ENV
    config = environments[app_env]
    return config()


settings = get_app_settings()
