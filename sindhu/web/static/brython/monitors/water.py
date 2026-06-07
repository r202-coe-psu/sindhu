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
            document["marker_style_selector"].bind("change", self.on_marker_style_change)

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
            self.latest_data = data
            
            if "storage_percent" not in self.map.metric_types:
                self.map.metric_types.append("storage_percent")
                
            await self.map.update("storage_percent", data)
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
        await self.map.update("storage_percent", self.latest_data)
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
            
            if hasattr(self.map, "_pin_mode_active") and self.map._pin_mode_active and self.map.user_coord:
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
                
            storage_percent = None
            other_metrics = []
            
            for m in metrics:
                if m["metric_type"].lower() == "storage_percent":
                    storage_percent = m.get("value")
                else:
                    other_metrics.append(m)
            
            if storage_percent is None:
                continue
                
            percent_val = float(storage_percent)
            
            if percent_val < 30:
                hex_color = "#FFFFFF"
                text_color = "#374151" # gray-700
                label = "น้ำน้อย"
            elif percent_val < 50:
                hex_color = "#B3E5FC"
                text_color = "#0369a1" # light blue on white bg -> use darker text
                label = "น้ำน้อย"
            elif percent_val < 80:
                hex_color = "#4FC3F7"
                text_color = "#0c4a6e"
                label = "น้ำปกติ"
            elif percent_val <= 100:
                hex_color = "#0288D1"
                text_color = "#FFFFFF"
                label = "น้ำมาก"
            else:
                hex_color = "#01579B"
                text_color = "#FFFFFF"
                label = "เฝ้าระวัง"
                
            name = station.get("name_th") or station.get("name")
            prov = station.get("province", "ไม่ระบุจังหวัด")
            location = f"จ.{prov}"
            
            # format other metrics
            other_html = ""
            for om in other_metrics:
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
                        <span class="w-2 h-2 rounded-full border border-gray-300" style="background-color: {'#e5e7eb' if percent_val < 30 else 'white'};"></span>{label}
                    </span>
                </div>
                <div class="flex justify-between text-sm mb-1.5 mt-3">
                    <span class="text-gray-500">ปริมาณน้ำ</span>
                    <span class="font-semibold text-gray-800">
                        <span class="ml-1" style="color: {hex_color if percent_val >= 80 else text_color}">{percent_val:.1f}%</span>
                    </span>
                </div>
                <div class="w-full bg-gray-100 rounded-full h-2 overflow-hidden border border-gray-200">
                    <div class="h-full rounded-full transition-all duration-300" style="width: {min(100, percent_val)}%; background-color: {hex_color};"></div>
                </div>
                <div class="mt-3 flex flex-wrap gap-2">
                    {other_html}
                </div>
            </div>
            """
            
        if not html_content:
            html_content = '<div class="flex justify-center items-center h-full text-gray-500">ไม่พบข้อมูลอ่างเก็บน้ำ</div>'
            
        document["reservoir_data_list"].html = html_content