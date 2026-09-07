from __future__ import annotations

from beanie import Document, PydanticObjectId
from pydantic import Field
import pymongo

from sindhu import schemas


class VisualFeed(schemas.visual_feeds.VisualFeed, Document):
    id: PydanticObjectId = Field(
        default_factory=PydanticObjectId,
        alias="_id",
    )

    class Settings:
        name = "visual_feeds"
        indexes = [
            pymongo.IndexModel(
                [("source", pymongo.ASCENDING), ("upstream_id", pymongo.ASCENDING)],
                unique=True,
                name="uq_visual_feeds_source_upstream_id",
            ),
            pymongo.IndexModel(
                [
                    ("media_type", pymongo.ASCENDING),
                    ("coverage_group", pymongo.ASCENDING),
                    ("availability", pymongo.ASCENDING),
                ],
                name="ix_visual_feeds_filters",
            ),
            pymongo.IndexModel(
                [("coordinates", pymongo.GEOSPHERE)],
                sparse=True,
                name="ix_visual_feeds_coordinates",
            ),
        ]


__all__ = ["VisualFeed"]
