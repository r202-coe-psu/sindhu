from __future__ import annotations

import datetime
import hashlib

from fastapi import APIRouter, Query, Request, Response
from starlette import status
from starlette.exceptions import HTTPException

from sindhu import schemas, services

router = APIRouter(prefix="/visual-feeds", tags=["visual-feeds"])


def _http_error(error: services.visual_feeds.ViewerError) -> HTTPException:
    return HTTPException(status_code=error.status_code, detail=error.code)


@router.get("", response_model=schemas.visual_feeds.PublicVisualFeedList)
async def list_visual_feeds(
    response: Response,
    media_type: schemas.visual_feeds.MediaType | None = Query(default=None),
    coverage_group: str | None = Query(default=None, min_length=1, max_length=200),
    availability: schemas.visual_feeds.Availability | None = Query(default=None),
    has_coordinates: bool | None = Query(default=None),
) -> schemas.visual_feeds.PublicVisualFeedList:
    response.headers["Cache-Control"] = "no-store"
    try:
        feeds, source_health = await services.visual_feeds.list_visual_feeds(
            media_type=media_type,
            coverage_group=coverage_group,
            availability=availability,
            has_coordinates=has_coordinates,
        )
    except services.visual_feeds.ViewerError as error:
        raise _http_error(error) from None
    return schemas.visual_feeds.PublicVisualFeedList(
        visual_feeds=feeds,
        count=len(feeds),
        generated_at=datetime.datetime.now(datetime.timezone.utc),
        source_health=source_health,
    )


@router.get(
    "/{source}/{upstream_id}",
    response_model=schemas.visual_feeds.PublicVisualFeed,
)
async def get_visual_feed(
    source: str,
    upstream_id: str,
    response: Response,
) -> schemas.visual_feeds.PublicVisualFeed:
    response.headers["Cache-Control"] = "no-store"
    try:
        feed = await services.visual_feeds.get_visual_feed(source, upstream_id)
    except services.visual_feeds.ViewerError as error:
        raise _http_error(error) from None
    if feed is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Visual feed not found",
        )
    return feed


@router.get(
    "/{source}/{upstream_id}/history",
    response_model=schemas.visual_feeds.VisualFeedHistory,
)
async def get_visual_feed_history(
    source: str,
    upstream_id: str,
    response: Response,
    date: datetime.date | None = Query(None),
):
    response.headers["Cache-Control"] = "no-store"
    try:
        return await services.visual_feeds.get_history(source, upstream_id, date)
    except services.visual_feeds.ViewerError as error:
        raise _http_error(error) from None


def _etag(value: bytes | str) -> str:
    data = value.encode() if isinstance(value, str) else value
    return '"' + hashlib.sha256(data).hexdigest() + '"'


def _image_headers(etag: str) -> dict[str, str]:
    return {
        "Cache-Control": "private, max-age=120",
        "ETag": etag,
        "X-Content-Type-Options": "nosniff",
    }


def _not_modified(request: Request, etag: str) -> Response | None:
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=_image_headers(etag))
    return None


def _image_response(
    payload: bytes, media_type: str, request: Request, etag: str | None = None
) -> Response:
    etag = etag or _etag(payload)
    return _not_modified(request, etag) or Response(
        payload, media_type=media_type, headers=_image_headers(etag)
    )


@router.get("/dwr/{upstream_id}/snapshot")
async def get_visual_feed_snapshot(upstream_id: str, request: Request):
    try:
        # The dated image path changes exactly when the image does, so it is the
        # ETag: a repeat request costs one small upstream call, not the JPEG.
        token = await services.visual_feeds.get_snapshot_token(upstream_id)
        etag = _etag(token) if token else None
        if etag and (unchanged := _not_modified(request, etag)):
            return unchanged
        payload = await services.visual_feeds.get_snapshot(upstream_id, token)
    except services.visual_feeds.ViewerError as error:
        raise _http_error(error) from None
    return _image_response(payload, "image/jpeg", request, etag)


@router.get("/rid/{upstream_id}/snapshot")
async def get_rid_visual_feed_snapshot(upstream_id: str, request: Request):
    try:
        payload, media_type = await services.visual_feeds.get_rid_snapshot(upstream_id)
    except services.visual_feeds.ViewerError as error:
        raise _http_error(error) from None
    return _image_response(payload, media_type, request)
