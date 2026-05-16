from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from typing import Annotated
from jose import jwt, JWTError
from pydantic import ValidationError

from loguru import logger

from ... import models
from ... import schemas
from . import security


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/v1/auth/login")


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
) -> models.users.User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(
            token, security.settings.SECRET_KEY, algorithms=[security.ALGORITHM]
        )
        user_id: str | None = payload.get("sub")
        if user_id is None:
            raise credentials_exception
        token_data = schemas.users.TokenData(user_id=user_id)
    except JWTError:
        raise credentials_exception

    # user = get_user(fake_users_db, username=token_data.username)
    user = await models.users.User.get(token_data.user_id)
    if user is None:
        raise credentials_exception
    return user


async def get_current_active_user(
    current_user: Annotated[models.users.User, Depends(get_current_user)],
    # current_user: models.users.User = Depends(get_current_user),
) -> models.users.User:
    if current_user.status != "active":
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user


async def get_current_active_superuser(
    current_user: models.users.User = Depends(get_current_user),
) -> models.users.User:
    if "admin" not in current_user.roles:
        raise HTTPException(
            status_code=400, detail="The user doesn't have enough privileges"
        )
    return current_user


async def create_logs(action, request, current_user):
    request_log = models.RequestLog(
        user=current_user,
        ip_address=request.client.host,
        action=action,
        user_agent=request.headers.get("user-agent", ""),
    )
    return request_log


async def get_system_setting() -> models.system_settings.SystemSetting:
    db_system_setting = await models.system_settings.SystemSetting.find_one(
        sort=[("_id", -1)], fetch_links=True
    )
    return db_system_setting


class RoleChecker:
    def __init__(self, *allowed_roles: list[str]):
        self.allowed_roles = allowed_roles

    def __call__(self, user: models.users.User = Depends(get_current_active_user)):
        for role in user.roles:
            if role in self.allowed_roles:
                return
        logger.debug(f"User with role {user.roles} not in {self.allowed_roles}")
        raise HTTPException(status_code=403, detail="Role not permitted")


class DivisionChecker:
    def __init__(self, *allowed_divisions: list[str]):
        self.allowed_divisions = allowed_divisions

    def __call__(self, user: models.users.User = Depends(get_current_active_user)):
        if user.division not in self.allowed_divisions:
            logger.debug(
                f"User with division {user.division} not in {self.allowed_divisions}"
            )
            raise HTTPException(status_code=403, detail="Division not permitted")
