from sindhu.api.core.settings.app import AppSettings


class ProdAppSettings(AppSettings):
    MONGODB_HOST: str = "sindhu-mongodb"
    ROOT_PATH: str = "/api"

    class Config(AppSettings.Config):
        env_file = "prod.env"
