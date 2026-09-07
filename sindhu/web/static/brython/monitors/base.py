from browser import aio, timer, document, ajax, window
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
        fallback_zone_urls=None,
        reference_boundary_url=None,
    ):
        self.lang_code = lang_code
        self.acquisition_interval = 60 * 60

        self.running = False

        self.api_url = api_url
        self.source = source
        self.center = center
        self.zoom = zoom
        self.fallback_zone_urls = fallback_zone_urls or []
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
        """Prepare the map even when system settings are not initialized yet.

        A fresh development database does not contain a ``system_settings``
        document until an administrator saves the settings form.  The API
        correctly responds with 404 in that state; the monitor should keep the
        page usable instead of indexing a missing ``center`` key and stopping
        Brython entirely.
        """
        self.system_setting = {}
        try:
            response = await aio.get(self.apis["system_settings"], cache=True)
            if getattr(response, "status", 200) != 200:
                raise RuntimeError(
                    f"system settings returned HTTP {response.status}"
                )
            parsed = json.loads(response.data)
            if isinstance(parsed, dict):
                self.system_setting = parsed
        except Exception as exc:
            print(f"monitor setup: using default map settings ({exc})")

        center_object = self.system_setting.get("center") or {}
        center = center_object.get("coordinates") or self.center or [100.5, 7.0]
        if not isinstance(center, (list, tuple)) or len(center) < 2:
            center = [100.5, 7.0]
        zoom = self.system_setting.get("zoom") or self.zoom or 12
        min_zoom = self.system_setting.get("min_zoom")
        if min_zoom is None:
            min_zoom = 8

        self.map = BaseMap([center[1], center[0]], zoom, min_zoom, self.lang_code)
        self.map.load_river_basins(self.api_url)
        self.set_map_loading(False)

        self.map.enable_pin_mode(self.on_map_pinned, self.on_pin_mode_off)

        await self.load_zones()

        if "my_locate" in document:
            document["my_locate"].bind("click", lambda ev: self.map.fly_to_user())

        if hasattr(self, "visual_feed_monitor") and self.visual_feed_monitor:
            try:
                self.visual_feed_monitor.update_map_markers()
            except Exception as e:
                print(f"update_map_markers error: {e}")

        return True

    async def load_zones(self):
        """Draw API zones, or bundled prototype GeoJSON zones 1-4."""
        db_zones = []
        try:
            response = await aio.get(self.apis["zones"], cache=False)
            data = json.loads(response.data)
            db_zones = data.get("zones", [])
        except Exception as e:
            print(f"load_zones error: {e}")

        if db_zones:
            for z in db_zones:
                if not z.get("style"):
                    z["style"] = z.get("metadata") or {}
            self.zones = [z for z in db_zones if z.get("status") != "inactive"]
        elif self.fallback_zone_urls:
            region_th_map = {
                "south": "ทิศใต้",
                "west": "ทิศตะวันตก",
                "central_east": "ตอนกลาง-ทิศตะวันออก",
                "north": "ทิศเหนือ",
            }
            fallback_zones = []
            for index, url in enumerate(self.fallback_zone_urls):
                try:
                    response = await aio.get(url, cache=True)
                    collection = json.loads(response.data)
                    for feature in collection.get("features", []):
                        props = feature.get("properties") or {}
                        reg = props.get("region", "")
                        reg_label = region_th_map.get(reg, reg)
                        base_name_th = props.get("name_th", f"โซน {index + 1}")
                        display_name_th = (
                            f"{base_name_th} ({reg_label})" if reg_label else base_name_th
                        )
                        fallback_zones.append({
                            "id": f"prototype-zone-{index + 1}",
                            "name": props.get("name", f"Zone {index + 1}"),
                            "name_th": display_name_th,
                            "boundary": feature.get("geometry"),
                            "style": props,
                            "prototype": True,
                        })
                except Exception as e:
                    print(f"load fallback zone error: {e}")
            self.zones = fallback_zones

        self.map.show_all_zones(self.zones, on_select=self.on_zone_selected)
        has_db_boundary = any(
            (z.get("metadata") or {}).get("role") == "reference_boundary"
            or z.get("code") == "hatyai-boundary"
            for z in db_zones
        )
        if not has_db_boundary:
            await self.load_reference_boundary()
        if hasattr(self.map, "fit_to_hatyai_bounds"):
            self.map.fit_to_hatyai_bounds()

    async def load_reference_boundary(self):
        if not self.reference_boundary_url:
            return
        try:
            response = await aio.get(self.reference_boundary_url, cache=True)
            geometry = json.loads(response.data)
            if geometry.get("type") == "Feature":
                geometry = geometry.get("geometry")
            elif geometry.get("type") == "FeatureCollection":
                features = geometry.get("features", [])
                geometry = features[0].get("geometry") if features else None
            self.map.show_reference_boundary(geometry)
        except Exception as e:
            print(f"load Hat Yai boundary error: {e}")

    def on_zone_selected(self, zone):
        """Called when a user clicks a zone polygon on the map."""
        aio.run(self.load_zone_stations(zone))

    async def load_zone_stations(self, zone):
        if zone.get("prototype"):
            self.on_zone_stations_empty(zone)
            return
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
        timer.set_timeout(lambda: aio.run(self.on_filter(ev)), 50)

    async def on_filter(self, ev):
        return

    def set_map_loading(self, is_loading: bool):
        el = document["loading_map"]
        if is_loading:
            el.classList.remove("opacity-0", "pointer-events-none")
        else:
            el.classList.add("opacity-0", "pointer-events-none")
