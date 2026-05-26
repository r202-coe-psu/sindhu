import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
from beanie import PydanticObjectId
from beanie.operators import Set
from loguru import logger

from sindhu.api.core import deps
from sindhu import schemas, models, services

router = APIRouter(prefix="/zones", tags=["zones"])


@router.get("")
async def get_all(
    status: str = "active",
) -> schemas.zones.ZoneList:
    zones = await models.Zone.find({"status": status}).to_list()
    return schemas.zones.ZoneList(zones=zones)


@router.get("/{zone_id}")
async def get(zone_id: PydanticObjectId) -> schemas.zones.Zone:
    zone = await models.Zone.find_one(models.Zone.id == zone_id)
    if not zone:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="Not found zone",
        )
    return zone


@router.post("/locate")
async def locate(
    body: schemas.zones.LocateRequest,
) -> schemas.zones.LocateResponse:
    zone = await services.zones.find_zone_by_location(body.longitude, body.latitude)
    zone_stations = await services.zones.find_stations_by_zone(zone, body.longitude, body.latitude)
    return schemas.zones.LocateResponse(
        zone=zone,
        nearby_stations=zone_stations,
        user_location=[body.longitude, body.latitude],
    )


@router.post("/create")
async def create(
    zone_form: schemas.zones.CreateUpdateZone,
    current_user: models.User = Depends(deps.get_current_user),
) -> schemas.zones.Zone:
    db_zone = await models.Zone.find_one(models.Zone.code == zone_form.code)
    if db_zone:
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail="This zone already exists",
        )
    zone = models.Zone(**zone_form.model_dump())
    await zone.insert()
    return zone


@router.put("/update/{zone_id}")
async def update(
    zone_id: PydanticObjectId,
    zone_form: schemas.zones.CreateUpdateZone,
    current_user: models.User = Depends(deps.get_current_user),
) -> schemas.zones.Zone:
    db_zone = await models.Zone.find_one(models.Zone.id == zone_id)
    if not db_zone:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="Not found zone",
        )
    data = zone_form.model_dump()
    await db_zone.update(Set(data))
    db_zone.updated_date = datetime.datetime.now()
    await db_zone.save()
    return db_zone


@router.delete("/delete/{zone_id}")
async def delete(
    zone_id: PydanticObjectId,
    current_user: models.User = Depends(deps.get_current_user),
) -> schemas.zones.Zone:
    db_zone = await models.Zone.find_one(models.Zone.id == zone_id)
    if not db_zone:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="Not found zone",
        )
    db_zone.status = "delete"
    db_zone.updated_date = datetime.datetime.now()
    await db_zone.save()
    return db_zone
