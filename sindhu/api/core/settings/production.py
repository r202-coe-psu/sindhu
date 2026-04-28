from sindhu.api.core.settings.app import AppSettings


class ProdAppSettings(AppSettings):
    MONGODB_HOST: str = "sindhu-mongodb"

    class Config(AppSettings.Config):
        env_file = "prod.env"
