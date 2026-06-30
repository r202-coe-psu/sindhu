from browser import document, aio, ajax
import javascript as js
import datetime
from urllib.parse import urlencode

from .base import BaseMonitor
import json
from urllib.parse import urlencode


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

    def calculate_risk(self, station):
        metadata = station.get("metadata", {})
        wl_crit = metadata.get("water_level_critical")
        wl_warn = metadata.get("water_level_warning")
        wl_evac = metadata.get("water_level_evacuation")
        if wl_evac is None and wl_crit is not None:
            try:
                wl_evac = float(wl_crit) + 0.5
            except:
                pass

        waterlevel = None
        diff_wl_bank = None
        for m in station.get("metrics", []):
            m_type = m.get("metric_type", "").lower()
            val = m.get("value")
            if val is not None:
                if m_type in ["waterlevel", "waterlevel_msl", "waterlevel_m"]:
                    waterlevel = float(val)
                elif m_type == "diff_wl_bank":
                    diff_wl_bank = float(val)

        risk = -1
        if waterlevel is not None and wl_crit is not None and wl_warn is not None:
            try:
                wl = float(waterlevel)
                crit = float(wl_crit)
                warn = float(wl_warn)
                evac = float(wl_evac) if wl_evac is not None else crit + 0.5
                if wl >= evac:
                    risk = 3
                elif wl >= crit:
                    risk = 2
                elif wl >= warn:
                    risk = 1
                else:
                    risk = 0
            except:
                pass
        elif diff_wl_bank is not None:
            if diff_wl_bank >= 0.5:
                risk = 3
            elif diff_wl_bank >= 0:
                risk = 2
            elif diff_wl_bank >= -0.5:
                risk = 1
            else:
                risk = 0

        return risk, waterlevel, diff_wl_bank

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

        # Bind UI events
        if "marker_style_selector" in document:
            document["marker_style_selector"].bind(
                "change", self.on_marker_style_change
            )

        # Load and render river waterways
        try:
            rivers_response = await aio.get("/static/resources/rivers.geojson")
            rivers_data = json.loads(rivers_response.data)
            self.map.set_rivers_layer(rivers_data)
        except Exception as e:
            print(f"Failed to load rivers: {e}")

        if "source_selector" in document:
            document["source_selector"].bind("change", self.on_source_change)

        if self.running:
            print(f"monitor: wake up {datetime.datetime.now()}")
            print(f"monitor: {self.monitor_name} monitor")
            print(f"monitor: sleep {self.acquisition_interval}s")

            await self.get_stations_metrics()

            # wait for next aquisition
            await aio.sleep(self.acquisition_interval)

    async def get_stations_metrics(self):
        query_data = urlencode({"source": self.source})
        url = f"{self.api_url}/v1/stations/metrics/latest?{query_data}"

        self.set_map_loading(True)
        try:
            response = await aio.get(url, cache=True)
            data = json.loads(response.data)

            for station in data.get("stations", []):
                risk, _, _ = self.calculate_risk(station)

                if risk == 3:
                    station["risk_color"] = "#9333ea"
                    station["risk_percent"] = 100
                elif risk == 2:
                    station["risk_color"] = "#ef4444"
                    station["risk_percent"] = 100
                elif risk == 1:
                    station["risk_color"] = "#f97316"
                    station["risk_percent"] = 100
                elif risk == 0:
                    station["risk_color"] = "#22c55e"
                    station["risk_percent"] = 100
                else:
                    station["risk_color"] = "#9ca3af"
                    station["risk_percent"] = 100

            self.latest_data = data

            if "waterlevel" not in self.map.metric_types:
                self.map.metric_types.append("waterlevel")

            await self.map.update("waterlevel", data)
            self.render_data_list()
        except Exception as e:
            print(f"monitor: error {e}")
        finally:
            self.set_map_loading(False)

    def on_marker_style_change(self, ev):
        if hasattr(self, "map") and hasattr(self, "latest_data"):
            style = ev.target.value
            self.map.marker_style = style
            aio.run(self._update_and_filter())

    async def _update_and_filter(self):
        await self.map.update("waterlevel", self.latest_data)
        if "source_selector" in document:
            selected_source = document["source_selector"].value
            if selected_source != "all":
                filtered_codes = []
                for station in self.latest_data.get("stations", []):
                    if station.get("source") == selected_source:
                        code = station.get("code")
                        if code:
                            filtered_codes.append(code)
                self.map.filter_markers_by_codes(filtered_codes)
            else:
                self.map.show_all_markers()

    def on_source_change(self, ev):
        if hasattr(self, "map") and hasattr(self, "latest_data"):
            selected_source = ev.target.value

            if (
                hasattr(self.map, "_pin_mode_active")
                and self.map._pin_mode_active
                and self.map.user_coord
            ):
                lat, lng = self.map.user_coord
                aio.run(self.on_location_received(lat, lng))
                return

            if selected_source == "all":
                self.map.show_all_markers()
                self.render_data_list()
            else:
                filtered_codes = []
                for station in self.latest_data.get("stations", []):
                    if station.get("source") == selected_source:
                        code = station.get("code")
                        if code:
                            filtered_codes.append(code)
                self.map.filter_markers_by_codes(filtered_codes)
                self.render_data_list()

    def on_zone_stations_found(self, nearby_stations):
        if not hasattr(self, "latest_data"):
            return

        selected_source = "all"
        if "source_selector" in document:
            selected_source = document["source_selector"].value

        zone_codes = []
        for s in nearby_stations:
            code = s.get("code", None)
            if code:
                zone_codes.append(code)

        if selected_source != "all":
            valid_codes = set()
            for station in self.latest_data.get("stations", []):
                if station.get("source") == selected_source:
                    valid_codes.add(station.get("code"))
            zone_codes = [code for code in zone_codes if code in valid_codes]

        self.map.filter_markers_by_codes(zone_codes)
        self.render_data_list(zone_codes)

    def on_zone_stations_cleared(self):
        if hasattr(self, "latest_data"):
            selected_source = "all"
            if "source_selector" in document:
                selected_source = document["source_selector"].value

            if selected_source != "all":
                filtered_codes = []
                for station in self.latest_data.get("stations", []):
                    if station.get("source") == selected_source:
                        code = station.get("code")
                        if code:
                            filtered_codes.append(code)
                self.map.filter_markers_by_codes(filtered_codes)

            self.render_data_list()

    def update_zone_properties(self, zone_geojson, nearby_stations):
        if not hasattr(self, "latest_data") or not nearby_stations:
            return

        selected_source = "all"
        if "source_selector" in document:
            selected_source = document["source_selector"].value

        max_risk = (
            -1
        )  # -1 = Unknown, 0 = Normal, 1 = Warning, 2 = Critical, 3 = Evacuation

        for s in nearby_stations:
            code = s.get("code")
            if not code:
                continue
            for db_station in self.latest_data.get("stations", []):
                if db_station.get("code") == code:
                    if (
                        selected_source != "all"
                        and db_station.get("source") != selected_source
                    ):
                        continue

                    risk, _, _ = self.calculate_risk(db_station)

                    if risk > max_risk:
                        max_risk = risk

        # Map risk to colors
        if max_risk == 3:
            fill_color = "#9333ea"  # Purple (Evacuation)
            fill_opacity = 0.5
            color = "#7e22ce"
        elif max_risk == 2:
            fill_color = "#ef4444"  # Red (Critical)
            fill_opacity = 0.4
            color = "#dc2626"
        elif max_risk == 1:
            fill_color = "#f97316"  # Orange (Warning)
            fill_opacity = 0.3
            color = "#ea580c"
        elif max_risk == 0:
            fill_color = "#22c55e"  # Green (Normal)
            fill_opacity = 0.15
            color = "#16a34a"
        else:
            fill_color = "#9ca3af"  # Gray (Unknown)
            fill_opacity = 0.1
            color = "#6b7280"

        zone_geojson["properties"]["fillColor"] = fill_color
        zone_geojson["properties"]["color"] = color
        zone_geojson["properties"]["fillOpacity"] = fill_opacity

    def render_data_list(self, filter_codes=None):
        if "reservoir_data_list" not in document:
            return

        stations = self.latest_data.get("stations", [])
        if filter_codes is not None:
            stations = [s for s in stations if s.get("code") in filter_codes]

        selected_source = "all"
        if "source_selector" in document:
            selected_source = document["source_selector"].value

        if selected_source != "all":
            stations = [s for s in stations if s.get("source") == selected_source]

        html_content = ""

        for station in stations:
            metrics = station.get("metrics", [])
            if not metrics:
                continue

            risk, waterlevel, diff_wl_bank = self.calculate_risk(station)

            # Only show stations that have valid water level data
            if waterlevel is None and diff_wl_bank is None:
                continue

            if risk == 3:
                hex_color = "#9333ea"
                text_color = "white"
                label = "อพยพ"
            elif risk == 2:
                hex_color = "#ef4444"
                text_color = "white"
                label = "วิกฤต"
            elif risk == 1:
                hex_color = "#f97316"
                text_color = "white"
                label = "เฝ้าระวัง"
            elif risk == 0:
                hex_color = "#22c55e"
                text_color = "white"
                label = "ปกติ"
            else:
                hex_color = "#9ca3af"
                text_color = "white"
                label = "ไม่ทราบสถานะ"

            name = station.get("name_th") or station.get("name")
            prov = station.get("province", "ไม่ระบุจังหวัด")
            location = f"จ.{prov}"

            # format other metrics
            other_html = ""
            for om in metrics:
                m_name = om["metric_type"]
                val = om.get("value")
                if val is None:
                    continue

                if m_name == "waterlevel_msl":
                    display_text = f'ระดับน้ำ: <span class="font-medium text-gray-700">{val} ม.รทก.</span>'
                elif m_name == "diff_wl_bank":
                    try:
                        v = float(val)
                        if v < 0:
                            display_text = f'ระดับน้ำ: <span class="font-medium text-gray-700">ต่ำกว่าตลิ่ง {abs(v):.2f} ม.</span>'
                        elif v > 0:
                            display_text = f'ระดับน้ำ: <span class="font-medium text-red-600">ล้นตลิ่ง {v:.2f} ม.</span>'
                        else:
                            display_text = f'ระดับน้ำ: <span class="font-medium text-yellow-600">เสมอระดับตลิ่งพอดี</span>'
                    except:
                        display_text = f'ระดับน้ำกับตลิ่ง: <span class="font-medium text-gray-700">{val} ม.</span>'
                else:
                    display_text = f'{m_name}: <span class="font-medium text-gray-700">{val}</span>'

                other_html += f'<div class="text-xs text-gray-500 bg-gray-50 px-2 py-1 rounded">{display_text}</div>'

            html_content += f"""
            <div class="bg-white border border-gray-100 p-4 rounded-xl shadow-sm hover:shadow-md transition-all duration-200">
                <div class="flex justify-between items-start mb-2">
                    <div>
                        <h3 class="font-bold text-gray-800 text-base">{name}</h3>
                        <div class="text-xs text-gray-500 mt-0.5">{location}</div>
                    </div>
                    <span class="badge gap-1 px-2 py-3 shadow-sm border border-gray-200" style="background-color: {hex_color}; color: {text_color};">
                        <span class="w-2 h-2 rounded-full border border-gray-300" style="background-color: {'white'};"></span>{label}
                    </span>
                </div>
                <div class="mt-3 flex flex-wrap gap-2">
                    {other_html}
                </div>
            </div>
            """

        if not html_content:
            html_content = '<div class="flex justify-center items-center h-full text-gray-500">ไม่พบข้อมูลสถานีวัดน้ำ</div>'

        document["reservoir_data_list"].html = html_content
