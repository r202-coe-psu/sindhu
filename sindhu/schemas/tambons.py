from typing import Dict, List, Optional, Union

from pydantic import BaseModel, Field, field_validator


class TambonRef(BaseModel):
    code: str
    name_th: str
    amphoe_th: Optional[str] = None

    @field_validator("code", mode="before")
    @classmethod
    def _code_to_str(cls, v):
        return str(v) if v is not None else v


def coerce_tambon_ref(value) -> dict:
    """Normalize a tambon reference to {code, name_th, amphoe_th}.

    The single place that handles legacy data: a plain str (an old tambon
    name) becomes {code: str, name_th: str}. Models and dicts with extra keys
    are reduced to the three ref fields.
    """
    if isinstance(value, str):
        return {"code": value, "name_th": value, "amphoe_th": None}
    if hasattr(value, "model_dump"):
        value = value.model_dump()
    return {
        "code": str(value.get("code")),
        "name_th": value.get("name_th"),
        "amphoe_th": value.get("amphoe_th"),
    }


class TambonSummary(BaseModel):
    code: str
    name_th: str
    amphoe_th: Optional[str] = None
    zone_ids: List[str] = Field(default_factory=list)


class TambonSummaryWithGeometry(TambonSummary):
    boundary: Optional[Dict] = None


class TambonList(BaseModel):
    tambons: List[Union[TambonSummaryWithGeometry, TambonSummary]]


class ImportTambonRequest(BaseModel):
    feature_collection: Dict
    code_property: str
    name_property: str
    amphoe_property: Optional[str] = None
    dry_run: bool = True


class ImportTambonResponse(BaseModel):
    dry_run: bool
    imported: int
    skipped: int
    clipped_out: int = 0
    warnings: List[str] = Field(default_factory=list)
    zones: Dict[str, List[TambonRef]] = Field(default_factory=dict)
    changes: Dict[str, Dict] = Field(default_factory=dict)
