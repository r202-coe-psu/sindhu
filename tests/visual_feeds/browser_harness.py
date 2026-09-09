"""Local CCTV component harness: real template/controller/API; mock upstream only.

Run: .venv/bin/python -m uvicorn tests.visual_feeds.browser_harness:app --port 18081
No Mongo or live provider required. Not a production entry point.
"""

import asyncio
import os
import re
from contextlib import asynccontextmanager
from pathlib import Path

import brython
import httpx
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment

from sindhu.api.routers.v1.visual_feeds import router
from sindhu.services import visual_feeds
from tests.visual_feeds.test_api_integration import upstream_handler

REPO = Path(__file__).resolve().parents[2]
STATE = {"failure": None, "calls": [], "slow_date": None}


async def upstream(request):
    STATE["calls"].append(request.url.path + "?" + request.url.query.decode())
    if (
        request.url.path == "/api/flood/cam"
        and request.url.params.get("date") == STATE["slow_date"]
    ):
        await asyncio.sleep(0.5)  # Deliberately slow external provider, race fixture.
    return upstream_handler(request, source_failure=STATE["failure"])


@asynccontextmanager
async def lifespan(app):
    transport = (
        None
        if os.environ.get("CCTV_DEMO_LIVE") == "1"
        else httpx.MockTransport(upstream)
    )
    async with httpx.AsyncClient(
        transport=transport,
        timeout=httpx.Timeout(8, connect=3),
        follow_redirects=False,
    ) as client:
        visual_feeds.configure_visual_feeds(client, None)
        yield
        visual_feeds.close_visual_feeds()


app = FastAPI(lifespan=lifespan)
app.include_router(router, prefix="/v1")
app.mount("/runtime", StaticFiles(directory=Path(brython.__file__).parent / "data"))
app.mount("/static/brython", StaticFiles(directory=REPO / "sindhu/web/static/brython"))


@app.get("/_test/state")
def state():
    return STATE


@app.post("/_test/state")
def set_state(values: dict):
    STATE.update({k: v for k, v in values.items() if k in STATE})
    return STATE


@app.get("/", response_class=HTMLResponse)
def page():
    source = (REPO / "sindhu/web/templates/sites/monitor.html").read_text()
    content = re.search(
        r"{% block content %}(.*?){% endblock content %}", source, re.S
    )[1]
    # Exclude unrelated WaterMonitor bootstrap, keep actual template CCTV DOM.
    content = re.sub(r"<script\b.*?</script>", "", content, flags=re.S)
    rendered = Environment().from_string(content).render()
    return (
        """<!doctype html><html><head><meta charset="utf-8">
    <style>.hidden{display:none!important} img{max-width:320px}dialog{max-width:800px}
    #loading_map{display:none} .visual-feed-card{border:1px solid #ddd;margin:8px}</style>
    <script src="/runtime/brython.js"></script>
    <script src="/runtime/brython_stdlib.js"></script>
    <script src="/static/brython/visual_feeds.brython.js"></script>
    </head><body onload="brython({debug:1,pythonpath:['/static/brython']})">"""
        + rendered
        + """
    <script type="text/python">
from browser import window
from visual_feeds import VisualFeedMonitor
viewer = VisualFeedMonitor(window.location.origin)
viewer.start()
window.cctv_test_ready = True
    </script></body></html>"""
    )
