import datetime
from typing import Dict, List, Optional
from pydantic import BaseModel, Field, ConfigDict, field_validator
from beanie import PydanticObjectId

from sindhu.schemas import bases

"""Abstract base class for all station documents."""


class BaseStation(BaseModel):
    name: str
    name_th: str | None

    code: str
    source: str
    url: str

    metadata: dict | None = None
    coordinates: bases.GeoObject
    # coordinates: Point
    status: str = Field("active")


class CreateUpdateStation(BaseStation):
    create_update_metadata: dict | None = Field(None, alias="metadata")


class StationMetaData(BaseModel):
    pass


"""MongoDB document model for a station."""


class Station(bases.BaseSchema, BaseStation):
    station_metadata: dict | None = Field(None, alias="metadata")
    created_date: datetime.datetime
    updated_date: datetime.datetime
    status: str
    # Admin switch for the public map. Kept apart from `status`, which the ETL
    # pipelines use to find stations, so hiding a station never stops ingest.
    # Kept off CreateUpdateStation so a generic update cannot reset it.
    is_visible: bool = True
    # Bank height in metres above MSL, entered by an admin. Lives outside
    # `metadata` because the ETL rewrites that on every run, and off
    # CreateUpdateStation for the same reason as `is_visible`.
    bank_level: Optional[float] = None


class StationList(BaseModel):
    stations: List[Station]


class StationWithMetrics(Station):
    metrics: list


class StationWithMetricsList(BaseModel):
    stations: List[StationWithMetrics]


class UpdateStationVisibility(BaseModel):
    station_ids: List[PydanticObjectId] = Field(min_length=1)
    is_visible: bool


BANK_LEVEL_MIN_M = -20.0
BANK_LEVEL_MAX_M = 3000.0

SENSOR_NO_DATA_VALUES = (-9.99, -999.0)


class UpdateStationBankLevel(BaseModel):
    # Required, so clearing the value has to be an explicit null
    bank_level: Optional[float] = Field(
        ...,
        allow_inf_nan=False,
        ge=BANK_LEVEL_MIN_M,
        le=BANK_LEVEL_MAX_M,
        strict=True,
    )

    @field_validator("bank_level")
    @classmethod
    def not_a_no_data_code(cls, value: Optional[float]) -> Optional[float]:
        if value is not None and any(
            abs(value - code) < 0.001 for code in SENSOR_NO_DATA_VALUES
        ):
            raise ValueError(
                f"{value} คือรหัส 'ไม่มีข้อมูล' ของเซนเซอร์ ไม่ใช่ระดับตลิ่ง"
            )
        if value == 0:
            raise ValueError(
                "ระดับตลิ่ง 0 ม. ระบบถือว่าไม่มีค่า ถ้าต้องการล้างค่าให้เว้นว่าง"
            )
        return value
