from browser import aio, document, ajax, window
import javascript as js

import datetime
import json
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
        reference_boundary_url=None,
    ):
        self.lang_code = lang_code
        self.acquisition_interval = 60 * 60

        self.running = False

        self.api_url = api_url
        self.source = source
        self.center = center
        self.zoom = zoom
        self.reference_boundary_url = reference_boundary_url

        self.monitor_name = "base"

        self.params = None
        self.zones = []
        self.apis = {
            "system_settings": f"{self.api_url}/v1/system_settings",
            "locate": f"{self.api_url}/v1/zones/locate",
            "zones": f"{self.api_url}/v1/zones",
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
        """Initialise the map without leaving the page in a permanent loader.

        The API is the authority for map configuration and zones.  If it is
        unavailable we deliberately do not create a map with guessed bounds;
        instead the user gets a clear retry action and the next retry uses the
        API again.
        """
        self.set_map_loading(True)
        try:
            response = await aio.get(self.apis["system_settings"], cache=True)
            if response.status != 200:
                raise RuntimeError(f"system settings returned HTTP {response.status}")

            self.system_setting = json.loads(response.data)
            center = self.system_setting.get("center", {}).get("coordinates")
            zoom = self.system_setting.get("zoom")
            min_zoom = self.system_setting.get("min_zoom")
            if not isinstance(center, list) or len(center) != 2:
                raise ValueError("system settings has no valid map center")
            if zoom is None or min_zoom is None:
                raise ValueError("system settings has no valid zoom configuration")

            if not hasattr(self, "map"):
                self.map = BaseMap(
                    [center[1], center[0]], zoom, min_zoom, self.lang_code
                )
                self.map.enable_pin_mode(self.on_map_pinned, self.on_pin_mode_off)
                self.map.load_river_basins(self.api_url)

            await self.load_zones()

            if "my_locate" in document and not getattr(self, "_locate_bound", False):
                document["my_locate"].bind("click", lambda ev: self.map.fly_to_user())
                self._locate_bound = True
        except Exception as e:
            print(f"monitor setup error: {e}")
            self.set_map_error(
                "เชื่อมต่อข้อมูลแผนที่ไม่ได้ กรุณาตรวจสอบ API แล้วลองใหม่"
            )
            return False

        self.set_map_loading(False)
        return True

    async def load_zones(self):
        """Draw every zone up front so a zone can be picked without pinning."""
        try:
            response = await aio.get(self.apis["zones"], cache=False)
            if response.status != 200:
                raise RuntimeError(f"zones returned HTTP {response.status}")
            data = json.loads(response.data)
            zones = data.get("zones", [])
            if not isinstance(zones, list):
                raise ValueError("zones response is invalid")
        except Exception as e:
            print(f"load_zones error: {e}")
            # Preserve zones already rendered during a transient refresh error.
            if self.zones:
                return False
            raise

        self.zones = zones
        self.map.show_all_zones(self.zones, on_select=self.on_zone_selected)
        if not any(
            zone.get("zone_kind", "flood") == "reference"
            for zone in self.zones
            if isinstance(zone, dict)
        ):
            await self.load_default_reference_boundary()
        return True

    async def load_default_reference_boundary(self):
        """Keep the Hat Yai boundary visible even before the seed is rerun."""
        if not self.reference_boundary_url:
            return

        try:
            response = await aio.get(self.reference_boundary_url, cache=True)
            boundary = json.loads(response.data)
            self.map.show_reference_boundary(boundary, "ขอบเขตหาดใหญ่")
        except Exception as e:
            print(f"reference boundary error: {e}")

    def on_zone_selected(self, zone):
        """Called when a user clicks a zone polygon on the map."""
        aio.run(self.load_zone_stations(zone))

    async def load_zone_stations(self, zone):
        # `Zone.stations` is only filled in when an admin links stations by
        # hand, so fall back to resolving the members geographically.
        stations = zone.get("stations", []) or []
        zone_id = str(zone.get("id", "") or "")

        if not stations and zone_id:
            try:
                response = await aio.get(f"{self.apis['zones']}/{zone_id}/stations")
                stations = json.loads(response.data).get("stations", [])
            except Exception as e:
                print(f"zone stations error: {e}")
                stations = []

        if stations:
            codes = []
            for station in stations:
                code = station.get("code", None)
                if code:
                    codes.append(str(code))
            if codes:
                self.map.filter_markers_by_codes(codes)
            self.on_zone_stations_found(stations)
        else:
            # Say the zone is empty rather than silently falling back to the
            # unfiltered map, which reads as "the click did nothing".
            self.map.filter_markers_by_codes([])
            self.on_zone_stations_empty(zone)

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
                # The zone is already drawn by load_zones, so highlight it
                # instead of stacking a second polygon on top of it.
                zone_id = str(zone.get("id", "") or "")
                if not self.map.select_zone(zone_id, fit_bounds=False):
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
                    mark.setPopupContent(
                        f'<div class="text-sm font-semibold text-blue-700"><i class="ph ph-map-pin"></i> {zone_name}</div>'
                    ).openPopup()

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
                self.map.show_reset_button(False)
                mark = self.map.user_mark
                if mark and not isinstance(mark, list):
                    mark.setPopupContent(
                        '<div class="text-sm text-amber-700 font-semibold"><i class="ph ph-warning"></i> ไม่พบลุ่มน้ำสำหรับตำแหน่งนี้</div>'
                    ).openPopup()
        except Exception as e:
            print(f"locate error: {e}")

        self.set_map_loading(False)

    def on_zone_stations_found(self, nearby_stations):
        pass

    def on_zone_stations_cleared(self):
        pass

    def on_zone_stations_empty(self, zone):
        pass

    def on_filter_clicked(self, ev):
        window.setTimeout(lambda: aio.run(self.on_filter(ev)), 50)

    async def on_filter(self, ev):
        return

    def set_map_loading(self, is_loading: bool):
        if "loading_map" not in document:
            return
        el = document["loading_map"]
        if is_loading:
            if "loading_map_message" in document:
                message = document["loading_map_message"]
                message.text = "กำลังโหลดแผนที่..."
                message.classList.add("animate-pulse")
            if "loading_map_spinner" in document:
                document["loading_map_spinner"].classList.remove("hidden")
            if "retry_map_loading" in document:
                document["retry_map_loading"].classList.add("hidden")
            el.classList.remove("opacity-0", "pointer-events-none")
        else:
            el.classList.add("opacity-0", "pointer-events-none")

    def set_map_error(self, message):
        """Replace the spinner with an actionable failure state."""
        if "loading_map" not in document:
            return
        el = document["loading_map"]
        if "loading_map_message" in document:
            message_el = document["loading_map_message"]
            message_el.text = message
            message_el.classList.remove("animate-pulse")
        if "loading_map_spinner" in document:
            document["loading_map_spinner"].classList.add("hidden")
        if "retry_map_loading" in document:
            retry = document["retry_map_loading"]
            retry.classList.remove("hidden")
            retry.unbind("click")
            retry.bind("click", lambda ev: aio.run(self.retry_setup()))
        el.classList.remove("opacity-0", "pointer-events-none")

    async def retry_setup(self):
        if await self.setup() and hasattr(self, "get_stations_metrics"):
            await self.get_stations_metrics()
