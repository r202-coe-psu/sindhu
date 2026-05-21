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

        # bind self.interpolates from base
        bindings = self.forecasts + self.interpolates

        for name in bindings:
            if name in document:
                document[name].bind("click", self.on_filter_clicked)

        aio.run(self.monitor())


    async def get_stations_metrics(self):
        url = f"{self.api_url}/v1/stations/metrics"
        params = dict(source=self.source)
        def _on_response(req):
            response = js.JSON.parse(req.text)
            aio.run(
                self.map.update(
                    "latest",
                    response,
                )
            )
            return True

        self.set_map_loading(True)
        try:
            ajax.get(url, params=urlencode(params), oncomplete=_on_response)
        except Exception as e:
            print(f"monitor: error {e}")
        finally:
            self.set_map_loading(False)