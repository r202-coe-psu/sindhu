import datetime

from typing import Dict
from pydantic import BaseModel, EmailStr, Field, ConfigDict
from beanie import PydanticObjectId, Link

from . import bases

"""Abstract base class for all metric documents."""


class BaseMetric(BaseModel):
    timestamp: datetime.datetime
    metadata: dict
    value: float


"""MongoDB document model for a metric."""


class Metric(bases.BaseSchema, BaseMetric):
    pass
