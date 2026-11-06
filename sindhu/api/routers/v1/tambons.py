import json

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import ValidationError

from sindhu.api.core import deps
from sindhu import schemas, models, services

router = APIRouter(prefix="/tambons", tags=["tambons"])

MAX_IMPORT_BYTES = 20 * 1024 * 1024
MAX_IMPORT_FEATURES = 5000


def _too_large():
    return HTTPException(
        status_code=413,
        detail="ไฟล์ใหญ่เกินไป (สูงสุด 20 MB)",
    )


async def _read_limited_body(request: Request) -> bytes:
    """Read the body, aborting as soon as it exceeds MAX_IMPORT_BYTES.

    Counting streamed bytes also covers chunked uploads with no
    Content-Length header.
    """
    length = request.headers.get("content-length")
    if length and length.isdigit() and int(length) > MAX_IMPORT_BYTES:
        raise _too_large()
    chunks, total = [], 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > MAX_IMPORT_BYTES:
            raise _too_large()
        chunks.append(chunk)
    return b"".join(chunks)


@router.get("")
async def get_all(include_geometry: bool = False) -> schemas.tambons.TambonList:
    schema = (
        schemas.tambons.TambonSummaryWithGeometry
        if include_geometry
        else schemas.tambons.TambonSummary
    )
    tambons = await services.tambons.list_latest_tambons()
    return schemas.tambons.TambonList(
        tambons=[
            schema(**services.tambons.tambon_summary(t, include_geometry))
            for t in tambons
        ]
    )


@router.post("/import")
async def import_(
    request: Request,
    current_user: models.User = Depends(deps.get_current_user),
) -> schemas.tambons.ImportTambonResponse:
    raw = await _read_limited_body(request)
    try:
        payload = json.loads(raw)
        body = schemas.tambons.ImportTambonRequest.model_validate(payload)
    except (ValueError, ValidationError) as exc:
        detail = (
            json.loads(exc.json(include_input=False, include_url=False))
            if isinstance(exc, ValidationError)
            else "JSON ไม่ถูกต้อง"
        )
        raise HTTPException(
            status_code=422, detail=detail
        )

    # Checked before any geometry is parsed.
    features = body.feature_collection.get("features")
    if isinstance(features, list) and len(features) > MAX_IMPORT_FEATURES:
        raise HTTPException(
            status_code=422,
            detail=f"จำนวนฟีเจอร์เกิน {MAX_IMPORT_FEATURES}",
        )
    result = await services.tambons.import_tambons(body, body.dry_run)
    return schemas.tambons.ImportTambonResponse(**result)
