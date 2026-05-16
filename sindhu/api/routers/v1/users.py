from fastapi import APIRouter, Depends, HTTPException, Request, status
from sindhu import schemas, models
from sindhu.api.core import deps
from loguru import logger
from beanie.operators import Set
from beanie import PydanticObjectId
import datetime


router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model_by_alias=False, response_model=schemas.users.User)
def get_me(current_user: models.users.User = Depends(deps.get_current_user)):
    return current_user

