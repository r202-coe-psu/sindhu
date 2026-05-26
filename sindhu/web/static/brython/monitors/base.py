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
        self.set_map_loading(False)

        self.map.enable_pin_mode(self.on_map_pinned)

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
                zone_geojson = {
                    "type": "Feature",
                    "properties": {"name": zone.get("name_th") or zone.get("name", "")},
                    "geometry": zone["boundary"],
                }
                self.map.show_zone(zone_geojson)

                if nearby_stations and len(nearby_stations) > 0:
                    codes = []
                    for s in nearby_stations:
                        code = s.get("code", None)
                        if code:
                            codes.append(str(code))
                    if codes:
                        self.map.filter_markers_by_codes(codes)

                self.update_locate_panel("success", zone=zone, stations=nearby_stations)
                self.on_zone_stations_found(nearby_stations)
            else:
                mark = self.map.user_mark
                if mark and not isinstance(mark, list):
                    mark.setPopupContent('<div class="text-sm text-amber-700 font-semibold"><i class="ph ph-warning"></i> ไม่พบลุ่มน้ำสำหรับตำแหน่งนี้</div>').openPopup()
        except Exception as e:
            print(f"locate error: {e}")
            self.update_locate_panel("error", error_msg=str(e))

        self.set_map_loading(False)

    def update_locate_panel(self, state, zone=None, stations=None, error_msg=None):
        panel = document.getElementById("locate_result_panel")
        if not panel:
            return

        if state == "loading":
            panel.innerHTML = """
                <div class="flex items-center gap-2 text-gray-500 p-4">
                    <div class="w-5 h-5 border-2 border-blue-500 border-t-transparent rounded-full animate-spin"></div>
                    <span class="text-sm">กำลังค้นหาตำแหน่ง...</span>
                </div>
            """
        elif state == "error":
            panel.innerHTML = f"""
                <div class="p-4 text-sm text-red-600 bg-red-50 rounded-xl">
                    <i class="ph ph-warning-circle"></i> ไม่สามารถระบุตำแหน่งได้: {error_msg or 'Unknown error'}
                </div>
            """
        elif state == "success":
            panel.innerHTML = """
            <button id="btn_show_all_stations" class="btn btn-sm btn-ghost text-blue-600 hover:bg-blue-50 w-full mb-2">
                <i class="ph ph-arrow-counter-clockwise"></i> แสดงสถานีทั้งหมด
            </button>
            """
            btn = document.getElementById("btn_show_all_stations")
            if btn:
                btn.bind("click", self.on_show_all_stations)

    def on_zone_stations_found(self, nearby_stations):
        pass

    def on_show_all_stations(self, ev):
        self.map.show_all_markers()
        self.map.clear_zone_display()
        if hasattr(self, "user_mark") and self.map.user_mark and not isinstance(self.map.user_mark, list):
            self.map.map.removeLayer(self.map.user_mark)
            self.map.user_mark = []
        panel = document.getElementById("locate_result_panel")
        if panel:
            panel.innerHTML = ""
        self.on_zone_stations_cleared()

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
