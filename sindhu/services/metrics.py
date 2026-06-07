import datetime

from beanie import PydanticObjectId
from loguru import logger

from sindhu import models


async def get_metrics(source, metric_type, started_datetime, ended_datetime):
    match_metric = {
        "timestamp": {
            "$gte": started_datetime,
            "$lt": ended_datetime,
        },
    }
    if metric_type:
        match_metric["metadata.parameter"] = metric_type

    aggregation_pipeline = [
        {"$match": {"source": source, "status": "active"}},
        {
            "$lookup": {
                "from": "metrics",
                "localField": "_id",
                "foreignField": "metadata.station.$id",
                "as": "metrics",
                "pipeline": [
                    {"$match": match_metric},
                    {"$sort": {"timestamp": 1}},
                    {
                        "$group": {
                            "_id": "$metadata.parameter",
                            "metric_type": {"$last": "$metadata.parameter"},
                            "value": {"$last": "$value"},
                            "timestamp": {"$last": "$timestamp"},
                            "std_value": {"$stdDevSamp": "$value"},
                        }
                    },
                    {
                        "$project": {
                            "_id": 0,
                            "metric_type": 1,
                            "value": 1,
                            "timestamp": 1,
                            "std_value": 1,
                        }
                    },
                ],
            }
        },
        {"$addFields": {"id": "$_id"}},
        {"$project": {"_id": 0}},
    ]

    try:
        responses = await models.Station.aggregate(aggregation_pipeline).to_list()
    except Exception as e:
        logger.exception(e)
        raise e

    return responses


async def get_latest_metrics(source=None, timestamp=None):
    if not timestamp:
        timestamp = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(
            hours=24
        )

    match_query = {"status": "active"}
    if source:
        match_query["source"] = source

    aggregation_pipeline = [
        {"$match": match_query},
        {
            "$lookup": {
                "from": "metrics",
                "localField": "_id",
                "foreignField": "metadata.station.$id",
                "as": "metrics",
                "pipeline": [
                    {"$match": {"timestamp": {"$gte": timestamp}}},
                    {"$sort": {"timestamp": 1}},
                    {
                        "$group": {
                            "_id": "$metadata.parameter",
                            "metric_type": {"$last": "$metadata.parameter"},
                            "value": {"$last": "$value"},
                            "timestamp": {"$last": "$timestamp"},
                        }
                    },
                    {"$project": {"_id": 0}},
                ],
            }
        },
        {"$addFields": {"id": "$_id"}},
        {"$project": {"_id": 0}},
    ]

    try:
        station_with_metrics = await models.Station.aggregate(
            aggregation_pipeline
        ).to_list()
    except Exception as e:
        logger.exception(e)
        raise e

    return station_with_metrics


async def get_latest_metrics_by_metric_type(
    metric_type, station_codes=None, source=None
):
    timestamp = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(
        hours=24
    )
    match_query = {
        "metadata.parameter": metric_type,
        "timestamp": {"$gte": timestamp},
    }
    if source:
        match_query["metadata.source"] = source

    aggregation_pipeline = [
        {"$match": match_query},
        {
            "$group": {
                "_id": {"station": "$metadata.station"},
                "station": {"$first": "$metadata.station"},
            }
        },
    ]

    station_refs = await models.Metric.aggregate(aggregation_pipeline).to_list()
    object_ids = [ref["_id"]["station"].id for ref in station_refs]

    match_query = {"_id": {"$in": object_ids}, "status": "active"}
    if source:
        match_query["source"] = source
    if station_codes:
        match_query["code"] = {"$in": station_codes}

    aggregation_pipeline = [
        {"$match": match_query},
        {
            "$lookup": {
                "from": "metrics",
                "localField": "_id",
                "foreignField": "metadata.station.$id",
                "as": "metrics",
                "pipeline": [
                    {
                        "$match": {
                            "timestamp": {"$gte": timestamp},
                            "metadata.parameter": metric_type,
                        }
                    },
                    {
                        "$group": {
                            "_id": "$metadata.parameter",
                            "metric_type": {"$last": "$metadata.parameter"},
                            "value": {"$last": "$value"},
                            "timestamp": {"$last": "$timestamp"},
                        }
                    },
                    {"$project": {"_id": 0}},
                ],
            }
        },
        {"$addFields": {"id": "$_id"}},
        {"$project": {"_id": 0}},
    ]

    station_with_metrics = await models.Station.aggregate(
        aggregation_pipeline
    ).to_list()

    return station_with_metrics


async def get_metrics_by_station(
    station_id: PydanticObjectId, started_datetime, ended_datetime, every="1h"
) -> list[dict]:
    year = "$year"
    month = None
    day = None
    hour = None
    minute = None

    if every == "1m":
        month = "$month"
        day = "$day"
        hour = "$hour"
        minute = "$minute"
    elif every == "1h":
        month = "$month"
        day = "$day"
        hour = "$hour"
    elif every == "1d":
        month = "$month"
        day = "$day"
    elif every == "1mo":
        month = "$month"

    pipeline = [
        {
            "$match": {
                "metadata.station.$id": station_id,
                "timestamp": {
                    "$gte": started_datetime,
                    "$lte": ended_datetime,
                },
            }
        },
        {
            "$addFields": {
                "year": {
                    "$dateToString": {
                        "date": {"$toDate": "$timestamp"},
                        "format": "%Y",
                    }
                },
                "month": {
                    "$dateToString": {
                        "date": {"$toDate": "$timestamp"},
                        "format": "%m",
                    }
                },
                "day": {
                    "$dateToString": {
                        "date": {"$toDate": "$timestamp"},
                        "format": "%d",
                    }
                },
                "hour": {
                    "$dateToString": {
                        "date": {"$toDate": "$timestamp"},
                        "format": "%H",
                    }
                },
                "minute": {
                    "$dateToString": {
                        "date": {"$toDate": "$timestamp"},
                        "format": "%M",
                    }
                },
            }
        },
        {
            "$group": {
                "_id": {
                    "metric_type": "$metadata.parameter",
                    "year": year,
                    "month": month,
                    "day": day,
                    "hour": hour,
                    "minute": minute,
                },
                "value": {"$avg": "$value"},
                "timestamp": {"$first": "$timestamp"},
            }
        },
        {
            "$group": {
                "_id": "$timestamp",
                "metrics": {
                    "$mergeObjects": {
                        "$arrayToObject": [
                            [{"k": "$_id.metric_type", "v": "$value"}]
                        ]
                    }
                },
            }
        },
        {
            "$project": {
                "_id": 0,
                "timestamp": "$_id",
                "metrics": 1,
            }
        },
    ]

    responses = await models.Metric.aggregate(pipeline).to_list()
    return responses
