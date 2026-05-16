import datetime
import typing
from fastapi import APIRouter, Depends, HTTPException, Request, status
from bson.objectid import ObjectId
from sindhu import schemas, models
from sindhu.api.core import deps
from loguru import logger
from beanie.operators import Set


router = APIRouter(prefix="/system_settings", tags=["system_settings"])


@router.get(
    "",
)
async def get() -> schemas.system_settings.SystemSettingResponse:
    db_system_setting = await deps.get_system_setting()
    if not db_system_setting:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Not found system setting",
        )

    return db_system_setting


@router.post(
    "/create",
)
async def create(
    system_setting_form: schemas.system_settings.CreateSystemSetting,
    current_user: models.users.User = Depends(deps.get_current_user),
) -> schemas.system_settings.SystemSettingResponse:
    db_system_setting = await deps.get_system_setting()

    if db_system_setting:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="System setting already exist",
        )

    system_setting = models.system_settings.SystemSetting(
        **system_setting_form.model_dump()
    )

    await system_setting.insert()

    return system_setting


@router.put(
    "/update",
)
async def update(
    system_setting: schemas.system_settings.UpdateSystemSetting,
    current_user: models.users.User = Depends(deps.get_current_user),
) -> schemas.system_settings.SystemSettingResponse:
    db_system_setting = await deps.get_system_setting()
    if not db_system_setting:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Not found system setting",
        )

    data = system_setting.model_dump()
    await db_system_setting.update(Set(data))

    db_system_setting.updated_date = datetime.datetime.now()
    await db_system_setting.save()

    return db_system_setting


@router.get(
    "/api_tokens/get/{api_token_id}",
)
async def get_api_token(
    api_token_id: str,
    current_user: models.users.User = Depends(deps.get_current_user),
) -> schemas.tokens.ApiTokenResponse:
    try:
        db_api_token = await models.ApiToken.find_one(
            {"_id": ObjectId(api_token_id)}, fetch_links=True
        )
    except:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Id is not correct",
        )
    if not db_api_token:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Not found this api token",
        )

    return db_api_token


@router.post(
    "/api_tokens/create",
)
async def create_api_token(
    api_token_form: schemas.tokens.CreateUpdateApiToken,
    current_user: models.users.User = Depends(deps.get_current_user),
) -> schemas.system_settings.SystemSettingResponse:
    db_system_setting = await deps.get_system_setting()

    if not db_system_setting:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Not Found System Setting",
        )

    api_token = models.ApiToken(**api_token_form.model_dump())
    await api_token.insert()

    db_system_setting_data = db_system_setting.model_dump()
    db_system_setting_data["api_tokens"].append(api_token)
    db_system_setting = models.system_settings.SystemSetting.model_validate(
        db_system_setting_data
    )
    await db_system_setting.save()

    return db_system_setting


@router.put("/api_tokens/update/{api_token_id}")
async def update_api_token(
    api_token_id: str,
    api_token: schemas.tokens.CreateUpdateApiToken,
    current_user: typing.Annotated[models.users.User, Depends(deps.get_current_user)],
) -> schemas.tokens.CreateUpdateApiToken:
    try:
        db_api_token = await models.ApiToken.find_one(
            {"_id": ObjectId(api_token_id)}, fetch_links=True
        )
    except:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Id is not correct",
        )

    if not db_api_token:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Not found this api token",
        )

    data = api_token.model_dump()
    await db_api_token.update(Set(data))

    db_api_token.updated_date = datetime.datetime.now()
    await db_api_token.save()

    return db_api_token


@router.delete(
    "/api_tokens/delete/{api_token_id}",
)
async def delete_api_token(
    api_token_id: str,
    current_user: models.users.User = Depends(deps.get_current_user),
) -> schemas.system_settings.SystemSettingResponse:
    db_system_setting = await deps.get_system_setting()
    if not db_system_setting:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Not Found System Setting",
        )

    try:
        db_api_token = await models.ApiToken.find_one({"_id": ObjectId(api_token_id)})
    except:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Id is not correct",
        )

    if not db_api_token:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Not found this api token",
        )

    # Remove from system settings list if present
    if db_system_setting.api_tokens:
        # We search for the token in the list by ID to be safe
        token_to_remove = next(
            (t for t in db_system_setting.api_tokens if str(t.to_ref().id) == api_token_id), None
        )
        if token_to_remove:
            db_system_setting.api_tokens.remove(token_to_remove)
            await db_system_setting.save()

    await db_api_token.delete()
    return db_system_setting
