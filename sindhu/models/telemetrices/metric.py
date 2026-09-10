from beanie import Document, TimeSeriesConfig, PydanticObjectId, Link
from datetime import datetime
from pydantic import Field

from sindhu.schemas.metrics import Metric as MetricSchema


class Metric(MetricSchema, Document):
    id: PydanticObjectId = Field(
        default_factory=PydanticObjectId,
        alias="_id",
    )

    class Settings:
        name = "metrics"
        timeseries = TimeSeriesConfig(
            time_field="timestamp",
            meta_field="metadata",
        )
