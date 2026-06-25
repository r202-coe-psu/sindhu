from browser import aio, timer, document, ajax, window
import javascript as js

import datetime
from urllib.parse import urlencode

from maps.base import BaseMap


class BaseMonitor:
    def __init__(
        self,
        lang_code,
        api_url,
        source=None,
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

        self.params = None
        self.apis = {
            "system_settings": f"{self.api_url}/v1/system_settings",
            "locate": f"{self.api_url}/v1/zones/locate",
        }

    def start(self):
        self.running = True
        aio.run(self.monitor())

    async def monitor(self):
        await self.setup()

        while self.running:
            self.set_map_loading(True)
            print(f"monitor: wake up {datetime.datetime.now()}")
            print(f"monitor: {self.monitor_name} monitor")
            print(f"monitor: sleep {self.acquisition_interval}s")

            stations = {}
            await self.map.update(self.source, stations)
            self.set_map_loading(False)

            await aio.sleep(self.acquisition_interval)

    async def setup(self):
        response = await aio.get(self.apis["system_settings"], cache=True)
        self.system_setting = js.JSON.parse(response.data)

        center = self.system_setting["center"]["coordinates"]
        zoom = self.system_setting["zoom"]
        min_zoom = self.system_setting["min_zoom"]

        self.map = BaseMap([center[1], center[0]], zoom, min_zoom, self.lang_code)
        self.map.load_river_basins(self.api_url)
        self.set_map_loading(False)

        self.map.enable_pin_mode(self.on_map_pinned, self.on_pin_mode_off)

        if "my_locate" in document:
            document["my_locate"].bind("click", lambda ev: self.map.fly_to_user())

    def on_pin_mode_off(self):
        self.map.show_all_markers()
        self.on_zone_stations_cleared()

    def on_map_pinned(self, lat, lng):
        aio.run(self.on_location_received(lat, lng))

    async def on_location_received(self, lat, lng):
        try:
            body = js.JSON.stringify({"latitude": lat, "longitude": lng})
            response = await aio.post(
                self.apis["locate"],
                data=body,
                headers={"Content-Type": "application/json"},
            )
            data = js.JSON.parse(response.data)

            zone = data.get("zone", None)
            nearby_stations = data.get("nearby_stations", [])

            self.map.clear_zone_display()

            if zone:
                zone_name = zone.get("name_th") or zone.get("name", "")
                zone_geojson = {
                    "type": "Feature",
                    "properties": {"name": zone_name},
                    "geometry": zone["boundary"],
                }
                if hasattr(self, "update_zone_properties"):
                    self.update_zone_properties(zone_geojson, nearby_stations)
                self.map.show_zone(zone_geojson)

                mark = self.map.user_mark
                if mark and not isinstance(mark, list):
                    mark.setPopupContent(f'<div class="text-sm font-semibold text-blue-700"><i class="ph ph-map-pin"></i> {zone_name}</div>').openPopup()

                if nearby_stations and len(nearby_stations) > 0:
                    self.map.show_station_paths((lat, lng), nearby_stations)
                    codes = []
                    for s in nearby_stations:
                        code = s.get("code", None)
                        if code:
                            codes.append(str(code))
                    if codes:
                        self.map.filter_markers_by_codes(codes)

                self.on_zone_stations_found(nearby_stations)
            else:
                self.map.show_all_markers()
                self.on_zone_stations_cleared()
                if self.map._reset_btn_container:
                    self.map._reset_btn_container.style.display = "none"
                mark = self.map.user_mark
                if mark and not isinstance(mark, list):
                    mark.setPopupContent('<div class="text-sm text-amber-700 font-semibold"><i class="ph ph-warning"></i> ไม่พบลุ่มน้ำสำหรับตำแหน่งนี้</div>').openPopup()
        except Exception as e:
            print(f"locate error: {e}")

        self.set_map_loading(False)

    def on_zone_stations_found(self, nearby_stations):
        pass

    def on_zone_stations_cleared(self):
        pass

    def on_filter_clicked(self, ev):
        timer.set_timeout(lambda: aio.run(self.on_filter(ev)), 50)

    async def on_filter(self, ev):
        return

    def set_map_loading(self, is_loading: bool):
        el = document["loading_map"]
        if is_loading:
            el.classList.remove("opacity-0", "pointer-events-none")
        else:
            el.classList.add("opacity-0", "pointer-events-none")
