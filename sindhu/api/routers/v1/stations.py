import math
from typing import Annotated
import datetime
from enum import Enum
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
from fastapi.responses import JSONResponse
from fastapi_cache.decorator import cache
from flask import json

from beanie import PydanticObjectId
from beanie.operators import Set, In
import bson
from loguru import logger


from sindhu.api.core import deps, caching
from sindhu import schemas, models, services

router = APIRouter(prefix="/stations", tags=["stations"])

SOURCES = ["thaiwater", "rid", "dwr"]

@router.get("")
#@cache(expire=300)
async def all(
    status: str = "active",
    source: Annotated[list[str], Query()] | None = None,
    station_code: Annotated[list[str], Query()] | None = None,
    name: str | None = None,
    name_th: str | None = None,
    # current_user: models.users.User = Depends(deps.get_current_user),
) ->schemas.stations.StationList:
    try:
        logger.debug(source)
        if source == [""]:
            source = SOURCES
        logger.debug(source)

        stations = models.Station.find({"status": status}, fetch_links=True)
        if source:
            stations = stations.find({"source": {"$in": source}}, fetch_links=True)

        if station_code:
            stations = stations.find({"code": {"$in": station_code}}, fetch_links=True)
        if name:
            stations = stations.find({"name": {"$regex": name}}, fetch_links=True)
        if name_th:
            stations = stations.find({"name_th": {"$regex": name_th}}, fetch_links=True)

        stations = await stations.to_list()
    except Exception as e:
        print(e)
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="Not found any stations",
        )
    response = schemas.stations.StationList(stations=stations)
    # logger.debug(response)
    return response


@router.get("/{station_id}")
# @cache(expire=300)
async def get(
    station_id: PydanticObjectId,
    # current_user: models.users.User = Depends(deps.get_current_user),
) -> schemas.stations.Station:
    try:
        station = await models.Station.find_one(
            models.Station.id == station_id,
            fetch_links=True,
        )
    except Exception as e:
        logger.exception(e)
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="Not found station",
        )

    if not station:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="Not found station",
        )

    return station


@router.post(
    "/create",
)
async def create(
    station_form: schemas.stations.CreateUpdateStation,
    current_user: models.User = Depends(deps.get_current_user),
) -> schemas.stations.Station:
    try:
        db_station = await models.Station.find_one(
            models.Station.code == station_form.code,
            fetch_links=True,
        )
    except Exception as e:
        logger.exception(e)
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="Not found station",
        )

    if db_station:
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail="This station already exist",
        )

    station = models.Station(**station_form.model_dump())

    await station.insert()

    return station


@router.put(
    "/update/{station_id}",
)
async def update(
    station_id: PydanticObjectId,
    station: schemas.stations.CreateUpdateStation,
    current_user: models.User = Depends(deps.get_current_user),
) -> schemas.stations.Station:
    try:
        db_station = await models.Station.find_one(
            models.Station.id == station_id,
            fetch_links=True,
        )
        if not db_station:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail="Not found station",
            )
    except Exception as e:
        logger.exception(e)
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="Not found station",
        )

    data = station.model_dump()
    await db_station.update(Set(data))

    db_station.updated_date = datetime.datetime.now()
    await db_station.save()

    return db_station


@router.delete(
    "/delete/{station_id}",
)
async def delete(
    station_id: PydanticObjectId,
    current_user: models.User = Depends(deps.get_current_user),
) -> schemas.stations.Station:
    try:
        db_station = await models.Station.find_one(
            models.Station.id == station_id,
            fetch_links=True,
        )
        if not db_station:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail="Not found station",
            )
    except Exception as e:
        logger.exception(e)
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="Not found station",
        )

    db_station.status = "delete"
    db_station.updated_date = datetime.datetime.now()
    await db_station.save()

    return db_station


# api ที่ใช้สำหรับการดึงค่า ของ metric type ออกมาเพื่อนำข้อมูลไปแสดงเป็น marker
@router.get("/metrics/{metric_type}/latest")
async def get_latest_metrics_by_metric_type(
    metric_type: str,
    source: str | None = None,
) -> schemas.stations.StationWithMetricsList:
    station_with_metrics = await services.metrics.get_latest_metrics_by_metric_type(
        metric_type, source=source
    )
    return schemas.stations.StationWithMetricsList(stations=station_with_metrics)


@router.get("/metrics/latest")
@cache(expire=300)
async def get_latest_metrics(
    source: str,
) -> schemas.stations.StationWithMetricsList:
    try:
        result = await services.metrics.get_latest_metrics(source)
    except Exception as e:
        logger.exception(e)
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="Not found any stations",
        )

    return schemas.stations.StationWithMetricsList(stations=result)


@router.get(
    "/metrics",
)
async def get_metrics(
    source: str,
    started_datetime: datetime.datetime,
    ended_datetime: datetime.datetime,
    metric_type: str | None= None,
) -> schemas.stations.StationWithMetricsList:
    try:
        result = await services.metrics.get_metrics(
            source, metric_type, started_datetime, ended_datetime
        )
    except Exception as e:
        logger.exception(e)
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="Not found any stations",
        )

    return schemas.stations.StationWithMetricsList(stations=result)


@router.get("/{station_id}/metrics")
async def get_metrics_by_station(
    station_id: PydanticObjectId,
    started_datetime: datetime.datetime,
    ended_datetime: datetime.datetime,
) -> list[dict]:
    response = await services.metrics.get_metrics_by_station(
        station_id, started_datetime, ended_datetime
    )
    return response
