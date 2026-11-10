from browser import aio, timer, document, ajax, window, html
import javascript as js

import datetime
import json
from urllib.parse import urlencode

from maps.base import BaseMap
from monitors.area import (
    ALL_AREAS,
    MSG_DENIED,
    MSG_ERROR,
    MSG_IN_ZONE,
    MSG_OUTSIDE,
    SOURCE_LIST,
    SOURCE_LOCATION,
    SOURCE_MAP,
    build_area_options,
    location_message,
    merge_station_codes,
    zone_ids_for_value,
)


class BaseMonitor:
    def __init__(
        self,
        lang_code,
        api_url,
        source=None,
        center=None,
        zoom=None,
        reference_boundary_url=None,
        rivers_url=None,
    ):
        self.lang_code = lang_code
        self.acquisition_interval = 60 * 60

        self.running = False

        self.api_url = api_url
        self.source = source
        self.center = center
        self.zoom = zoom
        self.reference_boundary_url = reference_boundary_url
        self.rivers_url = rivers_url or "/static/resources/songkhla_basins.geojson"

        self.monitor_name = "base"

        self.params = None
        self.zones = []
        # Area filter: None codes means "all areas" (no filtering).
        self.selected_zone_ids = []
        self.selected_zone_codes = None
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
            print(
                f"[Monitor:{self.monitor_name}] Cycle running (interval: {self.acquisition_interval}s)"
            )

            stations = {}
            await self.map.update(self.source, stations)
            self.set_map_loading(False)

            await aio.sleep(self.acquisition_interval)

    async def setup(self):
        """Initialise the map without leaving the page in a permanent loader."""
        self.set_map_loading(True)
        self.system_setting = {}
        try:
            try:
                response = await aio.get(self.apis["system_settings"], cache=True)
                if getattr(response, "status", 200) == 200:
                    parsed = json.loads(response.data)
                    if isinstance(parsed, dict):
                        self.system_setting = parsed
            except Exception as exc:
                print(f"[Monitor] System settings fetch error: {exc}")

            center_object = self.system_setting.get("center") or {}
            center = center_object.get("coordinates") or self.center or [100.5, 7.0]
            if not isinstance(center, (list, tuple)) or len(center) < 2:
                center = [100.5, 7.0]
            zoom = self.system_setting.get("zoom") or self.zoom or 12
            min_zoom = self.system_setting.get("min_zoom")
            if min_zoom is None:
                min_zoom = 8

            if not hasattr(self, "map"):
                self.map = BaseMap(
                    [center[1], center[0]], zoom, min_zoom, self.lang_code
                )
                self.map.enable_pin_mode(self.on_map_pinned, self.on_pin_mode_off)
                self.map.add_focus_control()
                # Rivers come from songkhla_basins.geojson (load_rivers below);
                # /v1/basins holds the same 807 lines, so it is not drawn twice.

            await self.load_zones()
            await self.load_rivers()

            if "my_locate" in document and not getattr(self, "_locate_bound", False):
                document["my_locate"].bind("click", self.on_my_locate_click)
                self._locate_bound = True

            if hasattr(self, "visual_feed_monitor") and self.visual_feed_monitor:
                try:
                    self.visual_feed_monitor.update_map_markers()
                except Exception as e:
                    print(f"update_map_markers error: {e}")
        except Exception as e:
            print(f"[Monitor] Setup error: {e}")
            self.set_map_error(
                "เชื่อมต่อข้อมูลแผนที่ไม่ได้ กรุณาตรวจสอบ API แล้วลองใหม่"
            )
            return False

        self.set_map_loading(False)
        return True

    async def load_rivers(self):
        """Load and render river waterways with flow animation."""
        if not self.rivers_url:
            return

        loaded = False
        try:
            response = await aio.get(self.rivers_url, cache=True)
            if response.status == 200 or response.status == 0:
                rivers_data = json.loads(response.data)
                self.map.set_rivers_layer(rivers_data)
                loaded = True
            else:
                print(f"[Monitor] Rivers returned HTTP {response.status}")
        except Exception as e:
            print(f"[Monitor] Failed to load rivers: {e}")
        self.map.rivers_unavailable = not loaded
        self.map.refresh_legend()

    async def load_zones(self):
        """Draw active API flood zones from database."""
        db_zones = []
        try:
            response = await aio.get(self.apis["zones"], cache=False)
            data = json.loads(response.data)
            db_zones = data.get("zones", [])
        except Exception as e:
            print(f"[Monitor] Failed to load zones: {e}")
            if self.zones:
                return False
            db_zones = []

        flood_zones = []
        for z in db_zones:
            if z.get("status") == "inactive":
                continue
            meta = z.get("metadata") or z.get("style") or {}
            is_ref = (
                z.get("zone_kind") == "reference"
                or meta.get("role") == "reference_boundary"
                or z.get("code") in ("hatyai-boundary", "hatyai")
                or (
                    z.get("code")
                    and "hatyai" in str(z.get("code")).lower()
                    and "zone" not in str(z.get("code")).lower()
                )
                or z.get("name")
                in ("Hat Yai", "Hat Yai Boundary", "กรอบพื้นที่หาดใหญ่")
                or z.get("name_th") in ("หาดใหญ่", "กรอบพื้นที่หาดใหญ่")
            )
            if is_ref:
                continue
            if not z.get("style"):
                z["style"] = meta
            flood_zones.append(z)

        self.zones = flood_zones
        self.map.show_all_zones(self.zones, on_select=self.on_zone_selected)
        self.populate_area_selector()
        await self.load_reference_boundary()
        if hasattr(self.map, "fit_to_hatyai_bounds"):
            self.map.fit_to_hatyai_bounds()
            window.setTimeout(self.map.fit_to_hatyai_bounds, 100)

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
            print(f"[Monitor] Reference boundary error: {e}")

    load_default_reference_boundary = load_reference_boundary

    """
    ===========================================================================
    Area selection (map click, dropdown, my location)
    ===========================================================================
    """

    def populate_area_selector(self):
        if "area_selector" not in document:
            return
        select = document["area_selector"]
        current = select.value
        select.clear()
        groups = {}
        for opt in build_area_options(self.zones):
            node = html.OPTION(opt["label"], value=opt["value"])
            if opt["group"] is None:
                select <= node
                continue
            if opt["group"] not in groups:
                groups[opt["group"]] = html.OPTGROUP(label=opt["group"])
                select <= groups[opt["group"]]
            groups[opt["group"]] <= node
        select.value = current
        if not getattr(self, "_area_bound", False):
            select.bind("change", self.on_area_change)
            self._area_bound = True

    def on_area_change(self, ev):
        value = ev.target.value
        if value == ALL_AREAS:
            self.reset_area()
            return
        zone_ids = zone_ids_for_value(self.zones, value)
        if zone_ids:
            self.select_area(zone_ids, SOURCE_LIST)

    def reset_area(self):
        self.map.reset_all()
        self.on_pin_mode_off()

    def set_area_message(self, text=None):
        if "area_message" not in document:
            return
        box = document["area_message"]
        if text:
            box.text = text
            box.classList.remove("hidden")
        else:
            box.text = ""
            box.classList.add("hidden")

    def _sync_area_selector(self, zone_ids):
        if "area_selector" not in document:
            return
        select = document["area_selector"]
        wanted = f"zone:{zone_ids[0]}" if len(zone_ids) == 1 else ALL_AREAS
        if select.value != wanted:
            select.value = wanted

    def select_area(self, zone_ids, source, message=None):
        """Single entry point: source is SOURCE_MAP, SOURCE_LIST or SOURCE_LOCATION."""
        aio.run(self._select_area(zone_ids, source, message))

    async def _select_area(self, zone_ids, source, message=None, fallback_zone=None):
        """Select zones by id. `fallback_zone` (a /locate zone dict) is used
        when the id is not one of the drawn zones, so state stays consistent."""
        ids = [str(z) for z in zone_ids or []]
        zones = [z for z in self.zones if str(z.get("id", "") or "") in ids]
        if not zones and fallback_zone:
            zones = [fallback_zone]
        if not zones:
            return False

        # `Zone.stations` is only filled in when an admin links stations by
        # hand, so fall back to resolving the members geographically.
        for zone in zones:
            if zone.get("stations"):
                continue
            zone_id = str(zone.get("id", "") or "")
            if not zone_id:
                zone["stations"] = []
                continue
            try:
                response = await aio.get(f"{self.apis['zones']}/{zone_id}/stations")
                zone["stations"] = json.loads(response.data).get("stations", [])
            except Exception as e:
                print(f"[Monitor] Zone stations error: {e}")
                zone["stations"] = []

        codes = merge_station_codes(zones)
        stations = [s for z in zones for s in (z.get("stations") or [])]

        self.selected_zone_ids = [str(z.get("id")) for z in zones]
        self.selected_zone_codes = codes
        # A location pick keeps the flyTo(user, 16) view, so only highlight.
        highlighted = self.map.select_zones(
            self.selected_zone_ids, fit_bounds=source == SOURCE_LIST
        )
        if not highlighted and fallback_zone and fallback_zone.get("boundary"):
            zone_geojson = {
                "type": "Feature",
                "properties": {
                    "name": fallback_zone.get("name_th") or fallback_zone.get("name", "")
                },
                "geometry": fallback_zone["boundary"],
            }
            if hasattr(self, "update_zone_properties"):
                self.update_zone_properties(zone_geojson, stations)
            self.map.show_zone(zone_geojson)
        if source != SOURCE_LIST:
            self._sync_area_selector(self.selected_zone_ids)
        self.set_area_message(message)

        self.map.filter_markers_by_codes(codes)
        if codes:
            self.on_zone_stations_found(stations)
        else:
            # Say the area is empty rather than silently falling back to the
            # unfiltered map, which reads as "the click did nothing".
            names = ", ".join(z.get("name_th") or z.get("name") or "" for z in zones)
            self.on_zone_stations_empty({"name_th": names})
        return True

    def on_zone_selected(self, zone):
        """Called when a user clicks a zone polygon on the map."""
        self.select_area([zone.get("id")], SOURCE_MAP)

    def on_pin_mode_off(self):
        self.selected_zone_ids = []
        self.selected_zone_codes = None
        if "area_selector" in document:
            document["area_selector"].value = ALL_AREAS
        self.set_area_message(None)
        self.map.show_all_markers()
        self.on_zone_stations_cleared()

    def on_map_pinned(self, lat, lng):
        aio.run(self.on_location_received(lat, lng))

    def on_my_locate_click(self, ev):
        self.set_area_message(None)
        self.map.fly_to_user(
            on_found=self.on_my_location_found, on_error=self.on_my_location_error
        )

    def on_my_location_found(self, lat, lng):
        aio.run(self.on_location_received(lat, lng))

    def on_my_location_error(self, e):
        # GeolocationPositionError.PERMISSION_DENIED == 1
        kind = MSG_DENIED if getattr(e, "code", None) == 1 else MSG_ERROR
        self.set_area_message(location_message(kind, error=e))

    async def on_location_received(self, lat, lng):
        try:
            body = js.JSON.stringify({"latitude": lat, "longitude": lng})
            response = await aio.post(
                self.apis["locate"],
                data=body,
                headers={"Content-Type": "application/json"},
            )
            if response.status != 0 and not 200 <= response.status < 300:
                raise RuntimeError(f"locate returned HTTP {response.status}")
            data = json.loads(response.data)

            zone = data.get("zone", None)
            nearby_stations = data.get("nearby_stations", [])

            self.map.clear_zone_display()

            if zone:
                zone_name = zone.get("name_th") or zone.get("name", "")
                zone_id = str(zone.get("id", "") or "")
                message = location_message(MSG_IN_ZONE, zone=zone)
                # Same path for drawn and undrawn zones; an undrawn one falls
                # back to the response's own stations (or nearby codes).
                fallback = dict(zone)
                if not fallback.get("stations"):
                    fallback["stations"] = [
                        s for s in nearby_stations or [] if s and s.get("code")
                    ]
                await self._select_area(
                    [zone_id], SOURCE_LOCATION, message, fallback_zone=fallback
                )

                mark = self.map.user_mark
                if mark and not isinstance(mark, list):
                    mark.setPopupContent(
                        f'<div class="text-sm font-semibold text-brand-700"><i class="ph ph-map-pin"></i> {zone_name}</div>'
                    ).openPopup()

                if nearby_stations and len(nearby_stations) > 0:
                    self.map.show_station_paths((lat, lng), nearby_stations)
            else:
                self.on_pin_mode_off()
                self.map.show_reset_button(False)
                self.set_area_message(location_message(MSG_OUTSIDE))
                mark = self.map.user_mark
                if mark and not isinstance(mark, list):
                    mark.setPopupContent(
                        '<div class="text-sm text-warning font-semibold"><i class="ph ph-warning"></i> นอกพื้นที่ Zone</div>'
                    ).openPopup()
        except Exception as e:
            print(f"[Monitor] Locate error: {e}")
            self.set_area_message(location_message(MSG_ERROR, error=e))

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
