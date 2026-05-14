from datetime import datetime, timezone, timedelta


from browser import ajax, document, html, window, timer, aio
import javascript as js

from .map import Map

class BaseMap(Map):
    def __init__(
        self,
        center,
        zoom,
        min_zoom,
        lang_code,
        # project_id,
    ):
        super().__init__(center, zoom, min_zoom)

        self.lang_code = lang_code
        # self.project_id = project_id
        self.metrics_markers_layers = {}
        self.metrics_legends = {}
        self.interpolate_layers = {}

       

    async def update(
        self, document_id, data, is_live_update=True, target_timestamp=None
    ):
        document["loading_map"].className = "ui inactive inverted dimmer"

        # logic handler

