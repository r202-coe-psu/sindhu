from browser import aio, timer, document, ajax
import javascript as js

import datetime
from urllib.parse import urlencode

from sindhu.web.static.brython.maps.base import BaseMap


class BaseMonitor:
    def __init__(
        self,
        lang_code,
        api_url,
        source,
        center=None,
        zoom=None,
    ):
        self.lang_code = lang_code
        self.acquisition_interval = 60 * 60

        self.running = False

        self.api_url = api_url
        self.source = source
        self.center = center
        self.zoom = zoom

        self.monitor_name = "base"

        # hardcoded URL
        self.params = None
        self.apis = {
        }

    """
    ===========================================================================
    Main functions
    ===========================================================================
    """

    def start(self):
        """Start function defined in child class"""
        pass

    async def monitor(self):
        await self.setup()

        while self.running:
            print(f"monitor: wake up {datetime.datetime.now()}")
            print(f"monitor: {self.monitor_name} monitor")
            print(f"monitor: sleep {self.acquisition_interval}s")

            # params = dict(source=self.source)
            # stations = await self.fetch_stations(
            #     self.apis["stations"]["climates"]["latest"], params
            # )
            stations = {}
            await self.map.update(self.source, stations)

            # wait for next aquisition
            await aio.sleep(self.acquisition_interval)

    async def setup(self):
        response = await aio.get(self.apis["system_settings"], cache=True)
        self.system_setting = js.JSON.parse(response.data)

        center = self.system_setting["center"]["coordinates"]
        zoom = self.system_setting["zoom"]
        min_zoom = self.system_setting["min_zoom"]

        self.map = BaseMap([center[1], center[0]], zoom, min_zoom, self.lang_code)

    def on_filter_clicked(self, ev):
        timer.set_timeout(lambda: aio.run(self.on_filter(ev)), 50)

    async def on_filter(self, ev):
        """Filter function defined in child class"""
        return

    """
    ===========================================================================
    Helper functions
    ===========================================================================
    """
