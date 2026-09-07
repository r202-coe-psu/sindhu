from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
from fastapi.exceptions import RequestValidationError

from contextlib import asynccontextmanager

from starlette.exceptions import HTTPException
from starlette.middleware.cors import CORSMiddleware

from sindhu.api.routers.errors.http_error import http_error_handler
from sindhu.api.routers.errors.validation_error import http422_error_handler
from sindhu.api.routers import init_router

from sindhu.api.core.config import get_app_settings
from sindhu.api.core.caching import init_redis_cache
from sindhu import models
import httpx
from sindhu.api.core import caching
from sindhu.services import visual_feeds


def create_application() -> FastAPI:
    settings = get_app_settings()
    settings.configure_logging()
    application = FastAPI(lifespan=lifespan, **settings.fastapi_kwargs)

    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_HOSTS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    application.add_exception_handler(HTTPException, http_error_handler)
    application.add_exception_handler(RequestValidationError, http422_error_handler)

    # init_rq(settings)
    return application


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_app_settings()

    init_redis_cache(settings)
    await models.init_beanie(app, settings)
    await init_router(app, settings)
    system_setting = await models.SystemSetting.find_one(sort=[("_id", -1)])
    hatyai_api_base_url = (
        getattr(system_setting, "hatyai_cctv_api_base_url", None)
        or settings.HATYAI_CCTV_API_BASE_URL
    )
    dwr_api_base_url = (
        getattr(system_setting, "dwr_cctv_api_base_url", None)
        or settings.DWR_CCTV_API_BASE_URL
    )
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(5.0, connect=2.0),
        limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
        follow_redirects=False,
    ) as cctv_client:
        visual_feeds.configure_visual_feeds(
            cctv_client,
            caching.redis_client,
            hatyai_api_base_url=hatyai_api_base_url,
            dwr_api_base_url=dwr_api_base_url,
        )
        try:
            yield
        finally:
            visual_feeds.close_visual_feeds()
