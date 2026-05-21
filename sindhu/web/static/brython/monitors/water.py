from browser import document, aio, ajax
import javascript as js
import datetime
from urllib.parse import urlencode

from monitors.base import BaseMonitor

class WaterMonitor(BaseMonitor):
    def __init__(
        self,
        lang_code,
        api_url,
        source,
        center=None,
        zoom=None,
    ):
        super().__init__(
            lang_code=lang_code,
            api_url=api_url,
            source=source,
            center=center,
            zoom=zoom,
        )
        self.monitor_name = "water"

        self.params = dict()
   

    """
    ===========================================================================
    Main functions
    ===========================================================================
    """

    def start(self):
        self.running = True
        aio.run(self.monitor())

    async def monitor(self):
        await self.setup()

        while self.running:
            print(f"monitor: wake up {datetime.datetime.now()}")
            print(f"monitor: {self.monitor_name} monitor")
            print(f"monitor: sleep {self.acquisition_interval}s")

            await self.get_stations_metrics()

            # wait for next aquisition
            await aio.sleep(self.acquisition_interval)

    async def get_stations_metrics(self):
        url = f"{self.api_url}/v1/stations/metrics/latest"
        params = dict(source=self.source)
        
        self.set_map_loading(True)
        try:
            response = await aio.get(url, params=params)
            data = js.JSON.parse(response.data)
            await self.map.update("latest", data)
        except Exception as e:
            print(f"monitor: error {e}")
        finally:
            self.set_map_loading(False)