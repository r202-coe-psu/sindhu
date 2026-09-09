"""Opt-in read-only provider smoke check; prints sanitized summaries only.

Run: .venv/bin/python -m tests.visual_feeds.live_smoke
Images are checked in memory and never saved; no Mongo/Redis writes.
"""

import asyncio
import datetime as dt
from collections import Counter

import httpx

from sindhu.schemas.visual_feeds import PublicVisualFeed
from sindhu.services.cctv_catalog import DWR_CAMERAS
from sindhu.services.cctv_sources import CctvSources, SourceError, BANGKOK


async def main():
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(5, connect=2), follow_redirects=False
    ) as client:
        sources = CctvSources(client)
        for source in ("hatyai_city_climate", "dwr"):
            try:
                feeds = [
                    PublicVisualFeed.model_validate(f)
                    for f in await sources.latest(source)
                ]
                print(
                    source,
                    "count",
                    len(feeds),
                    "status",
                    dict(Counter(f.availability.value for f in feeds)),
                )
            except SourceError as e:
                print(source, "FAILED", e.code)
        yesterday = dt.datetime.now(BANGKOK).date() - dt.timedelta(days=1)
        for ident in ("9", "56"):
            try:
                result = await sources.history("hatyai_city_climate", ident, yesterday)
                print("history", ident, str(yesterday), "frames", len(result["frames"]))
            except SourceError as e:
                print("history", ident, "FAILED", e.code)
        for camera in DWR_CAMERAS:
            try:
                payload = await sources.snapshot(camera["upstream_id"])
                print("snapshot", camera["code"], "JPEG bytes", len(payload))
            except SourceError as e:
                print("snapshot", camera["code"], "FAILED", e.code)


if __name__ == "__main__":
    asyncio.run(main())
