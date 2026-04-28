from datetime import datetime, timezone, timedelta

import json
import javascript as js
from browser import ajax, document, html, window, timer, aio, console
from .map import Map

# /home/suthinan/suthinxn/work/sindhu/sindhu/models
from stations import (
    sensor_colors,
    sensor_infos,
    hotspot_colors,
    hotspot_infos,
    fire_report_infos,
)

PM_DISPLAY = {
    "pm_0_1_forecast": "PM₀.₁",
    "pm_0_1": "PM₀.₁",
    "pm_1": "PM₁",
    "pm_2_5": "PM₂.₅",
    "pm_10": "PM₁₀",
}


# Helper
def get_nested(data, *keys, default="-"):
    """
    ฟังก์ชันช่วยดึงข้อมูลแบบปลอดภัย
    วิธีใช้: get_nested(item, "pm_2_5", "latest", "value")
    """
    for key in keys:
        if isinstance(data, dict):
            data = data.get(key)
        else:
            return default
    return data if data is not None else default


def format_timestamp(timestamp):
    bangkok_timezone = timezone(timedelta(hours=7), name="Asia/Bangkok")
    if timestamp in (None, "-"):
        return "-"

    if timestamp:
        try:
            if isinstance(timestamp, str):
                dt_obj = datetime.fromisoformat(timestamp)
            else:
                dt_obj = timestamp
            if dt_obj.tzinfo is None:
                dt_obj = dt_obj.replace(tzinfo=timezone.utc)

            ict_ts = dt_obj.astimezone(bangkok_timezone)
            return ict_ts.strftime("%d/%m/%Y %H:%M:%S (UTC+7)")

        except ValueError as e:
            print(f"Time Parse Error (ValueError): {e}")
            return str(timestamp)
        except TypeError as e:
            print(f"Time Parse Error (TypeError): {e}")
            return str(timestamp)


class LnMainMap(Map):
    def __init__(
        self,
        center,
        zoom,
        min_zoom,
        lang_code,
        # project_id,
        api_url,
        selected_sensor_type,
    ):
        super().__init__(center, zoom, min_zoom)

        self.lang_code = lang_code
        # self.project_id = project_id

        self.climate_markers_layers = {}
        self.hotspot_markers_layers = {}
        self.sensor_markers = {}
        self.sensor_markers_layer = {}
        self.hotspot_informations_layer = {}
        self.fire_report_layers = {}
        self.fire_report_legends = {}
        self.fire_report_aod_marker_layers = {}
        self.fire_report_aod_markers = {}
        self.climate_legends = {}
        self.hotspot_legends = {}
        self.station_objects = {}
        self.api_url = api_url
        self.get_climate_last_24_hours_url = (
            f"{api_url}/v1/stations/climates/last_24_hours"
        )

        self.selected_sensor_type = selected_sensor_type
        self.current_source = None
        self.current_data = None

        self.search_input = None

        # Get ID Current station Marker
        self.selected_station_id = None

        self.sensor_types = [
            "PM_0_1",
            "PM_0_1_forecast",
            "PM_1",
            "PM_2_5",
            "PM_10",
            "rain",
            "pressure",
            "temperature",
            "wind_direction",
            "humidity",
            "CO",
            "O3",
            "SO2",
            "NO2",
        ]
        self.sources = [
            "air4thai",
            "meteorological",
            "airport",
            "santhings",
        ]
        self.hotspots = [
            "viir_hotspots",
            "modis_hotspots",
            # "noaa-20",
            # "noaa-20_hotspots",
            # "noaa-21_hotspots",
            # "suomi_hotspots",
        ]

        self.hotspot_stations_code = [
            "modis",
            "noaa-20",
            "noaa-21",
            "suomi",
        ]
        self.modis_station_code = [
            "modis",
        ]
        self.viir_station_code = [
            "noaa-20",
            "noaa-21",
            "suomi",
        ]
        self.panel_plus_sensors = [
            "หมู่บ้านอิงกมล",
            "สำนักสงฆ์ย่านยาว",
            "เทศบาลบ้านไร่",
            "ไฮโซคีโมยำ",
            "เทศบาลพะตง",
            "Panel Plus",
        ]

        self.fire_reports = ["FAHP", "dNBR", "aod", "MLBA", "Emissions"]
        self.fire_report_aod = ["aod"]
        self.empirical_forecasts = [
            "empirical_PM_0_1_forecast",
            "empirical_PM_0_1",
            "empirical_PM_1",
        ]

        self.predictions = ["PM_2_5_prediction"]

        self.station_view_url = f"/{self.lang_code}/stations/"

        self.DISPLAY_REGION = {
            "south": "ภาคใต้",
            "all": "ทั้งหมด",
            "bangkok_vicinity": "กรุงเทพฯและปริมณฑล",
            "north": "ภาคเหนือ",
            "northeast": "ภาคตะวันออกเฉียงเหนือ",
            "central_west": "ภาคกลางและตะวันตก",
            "east": "ภาคตะวันออก",
        }

    def get_sensor_status(
        self,
        pm_value,
        sensor_type,
    ):
        thresholds = {
            "pm_0_1": [2.25, 3.75, 5.63, 11.25],
            "pm_1": [12, 20, 30, 60],
            "pm_2_5": [15, 25, 37.5, 75],
            "pm_10": [54, 154, 254, 354],
        }

        limits = thresholds.get(sensor_type.lower(), thresholds["pm_2_5"])
        pm_value = float(pm_value)

        # img_el.attrs["src"] = img_path

        if pm_value is None:
            return {
                "label": "ไม่มีข้อมูล",
                "color": "text-slate-600 bg-slate-100",
                "gradient": "bg-[radial-gradient(circle,rgba(150,150,150,0.8)_0%,rgba(150,150,150,0.25)_45%,rgba(255,255,255,0)_100%)]",
            }

        if pm_value <= limits[0]:
            return {
                "label": "คุณภาพอากาศดีมาก",
                "color": "text-blue-600 bg-blue-100",
                "img_path": "/static/images/pm25_level/air_quality_excellent.png",
                "gradient": "bg-[radial-gradient(circle,rgba(59,130,246,0.85)_0%,rgba(59,130,246,0.35)_45%,rgba(255,255,255,0)_75%)]",
            }

        if pm_value <= limits[1]:
            return {
                "label": "คุณภาพอากาศดี",
                "color": "text-green-600 bg-green-100",
                "img_path": "/static/images/pm25_level/air_quality_moderate.png",
                "gradient": "bg-[radial-gradient(circle,rgba(34,197,94,0.85)_0%,rgba(34,197,94,0.35)_45%,rgba(255,255,255,0)_75%)]",
            }

        if pm_value <= limits[2]:
            return {
                "label": "คุณภาพอากาศปานกลาง",
                "color": "text-yellow-700 bg-yellow-100",
                "img_path": "/static/images/pm25_level/air_quality_unhealthy_sensitive.png",
                "gradient": "bg-[radial-gradient(circle,rgba(234,179,8,0.85)_0%,rgba(234,179,8,0.35)_45%,rgba(255,255,255,0)_75%)]",
            }

        if pm_value <= limits[3]:
            return {
                "label": "มีผลกระทบต่อสุขภาพ",
                "color": "text-orange-600 bg-orange-100",
                "img_path": "/static/images/pm25_level/air_quality_unhealthy.png",
                "gradient": "bg-[radial-gradient(circle,rgba(249,115,22,0.85)_0%,rgba(249,115,22,0.35)_45%,rgba(255,255,255,0)_75%)]",
            }

        return {
            "label": "มีผลกระทบต่อสุขภาพมาก",
            "color": "text-red-600 bg-red-100",
            "img_path": "/static/images/pm25_level/air_quality_very_unhealthy.png",
            "gradient": "bg-[radial-gradient(circle,rgba(239,68,68,0.9)_0%,rgba(239,68,68,0.4)_45%,rgba(255,255,255,0)_75%)]",
        }

    async def render(self):
        self.map.on(
            "click", lambda ev: print(f"location: {ev.latlng.lat}, {ev.latlng.lng}")
        )

    async def update(
        self,
        document_id,
        data,
        is_live_update=True,
        target_timestamp=None,
    ):
        print("LmMainMap is running")
        # print("Document_id", document_id)
        # print("Data", data)

        # document["loading_map"].classList.remove("hidden")

        pm01_legend = document["pm01_legend_description"]
        pm1_legend = document["pm1_legend_description"]
        pm25_legend = document["pm25_legend_description"]
        pm10_legend = document["pm10_legend_description"]

        all_legends = [pm01_legend, pm1_legend, pm25_legend, pm10_legend]
        for legend in all_legends:
            legend.classList.add("hidden")

        legend_map = {
            "pm_0_1": pm01_legend,
            "pm_1": pm1_legend,
            "pm_2_5": pm25_legend,
            "pm_10": pm10_legend,
        }

        target_legend = legend_map.get(self.selected_sensor_type)

        if target_legend:
            target_legend.classList.remove("hidden")

        # pm01_label = document["pm01_label"]
        # pm1_label = document["pm1_label"]
        # pm25_label = document["pm25_label"]
        # pm10_label = document["pm10_label"]

        all_label_ids = ["pm01_label", "pm1_label", "pm25_label", "pm10_label"]

        for label_id in all_label_ids:
            document[label_id].classList.add("hidden")

        label_map = {
            "pm_0_1": "pm01_label",
            "pm_1": "pm1_label",
            "pm_2_5": "pm25_label",
            "pm_10": "pm10_label",
        }
        # print("Debug", self.selected_sensor_type)
        if self.selected_sensor_type in label_map:
            target_id = label_map[self.selected_sensor_type]
            document[target_id].classList.remove("hidden")

        # document["loading_map"].className = "loading loading-spinner loading-sm"
        # document["loading_map"].className = "hidden"
        # Get current data
        self.current_source = document_id
        self.current_data = data

        if document_id in self.hotspots:
            await self.update_hotspot_marker(document_id, data, is_live_update)
            return

        if document_id in self.fire_reports:
            await self.update_fire_report(document_id, data)
            return

        if (
            document_id
            in self.sensor_types
            + self.sources
            + self.empirical_forecasts
            + self.predictions
        ):
            # print("Data", data)
            await self.update_climate_marker(
                document_id, data, target_timestamp=target_timestamp
            )
            # document["loading_map"].classList.add("hidden")
            return

    def set_all_sensor_marker(self, marker_id):
        if marker_id in self.climate_markers_layers.keys():
            self.climate_markers_layers[marker_id] = self.leaflet.layerGroup(
                self.sensor_markers_layer[marker_id]
            ).addTo(self.map)

    ### Remove
    # Climates
    # def remove_climates_layer(self, source):
    #     if source in self.climate_markers_layers.keys():
    #         self.map.removeLayer(self.climate_markers_layers.get(source))

    def remove_climates_layer(self, source=None):
        for key in list(self.climate_markers_layers.keys()):
            layer = self.climate_markers_layers[key]

            if self.map.hasLayer(layer):
                self.map.removeLayer(layer)

            del self.climate_markers_layers[key]

    def remove_all_climate_legends(self):
        for key in self.climate_legends:
            self.remove_climate_legend(key)

    def remove_climate_legend(self, source):
        for key, value in self.climate_legends.items():
            if key == source and value:
                self.map.removeControl(value)

                self.climate_legends[source] = []

    ### Climates
    async def update_climate_legend(self, source):
        pass

    async def update_chart(self, station_id):
        # self.selected_sensor_type
        self.show_chart_loading()

        if self.selected_sensor_type == "pm_0_1":
            sensor_type = "PM_0_1_forecast"
        else:
            sensor_type = self.selected_sensor_type.upper()
        # if self.selected_sensor_type == "pm_0_1":
        # sensor_type = "PM_0_1_forecast"

        try:
            response = await aio.get(
                url=self.get_climate_last_24_hours_url,
                data={
                    "station": station_id,
                    "sensor_type": sensor_type,
                },
                cache=False,
            )

            res_json = js.JSON.parse(response.data)
            self.pm_last_24_hours = res_json.get("history", [])
            # self.render_pm25_chart(self.pm25_last_24_hours)
            self.update_pm_section(station_id, self.pm_last_24_hours)

        except Exception as e:
            print(f"An error occurred in update_chart: {e}")

    def update_pm_section(self, station_id, data):
        section = document["pm-section"]

        station = self.station_objects.get(station_id)
        station_name_th = station.get("name_th", "")

        if hasattr(self, "pm_chart"):
            self.pm_chart.destroy()
            del self.pm_chart

        section.innerHTML = f"""
            <div class="bg-white rounded-2xl shadow-lg border border-gray-100 p-6 mt-6">
                
                <div class="flex items-center gap-4 bg-white p-4 rounded-xl max-w-md">
                <div class="flex items-center justify-center w-12 h-12 rounded-xl bg-gradient-to-br from-blue-400 to-cyan-500">
                    <i class="ph ph-clock text-white text-xl"></i>
                </div>

                <div class="flex flex-col">
                    <span class="text-xl font-semibold text-gray-700">
                    คุณภาพอากาศย้อนหลัง 24 ชั่วโมง {PM_DISPLAY.get(self.selected_sensor_type, "N/A")}
                    </span>
                    <span class="text-sm text-gray-500">
                    { station_name_th }
                    </span>
                </div>
                </div>


                <div id="pm25-chart"></div>

                <div class="flex items-center justify-center gap-6 pt-4 border-t border-gray-100">
                    <div class="flex items-center gap-2>
                    <span class="text-xs text-gray-600">กราฟขวาสุดเป็นข้อมูลล่าสุด ณ เวลาปัจจุบัน</span>
                    </div>
                </div>
            
            </div>

        """

        section.classList.remove("hidden")

        self.init_pm25_chart()
        self.render_pm25_chart(data)

    def render_pm25_chart(self, data):
        series_data = self.prepare_chart_data(data)

        labels = [item["x"] for item in series_data]

        self.pm_chart.updateSeries(
            [
                {
                    "name": f"{PM_DISPLAY.get(self.selected_sensor_type, 'N/A')} (µg/m³)",
                    "data": series_data,
                }
            ],
            True,
        )

        self.pm_chart.updateOptions({"xaxis": {"categories": labels}})

    def init_pm25_chart(self):
        options = {
            "chart": {
                "type": "bar",
                "height": 300,
                "toolbar": {"show": False},
                "animations": {
                    "enabled": True,
                    "easing": "easeinout",
                    "speed": 500,
                },
            },
            "dataLabels": {"enabled": False},
            "series": [{"name": "PM2.5", "data": []}],
            "xaxis": {"categories": []},
            "yaxis": {
                "title": {
                    "text": f"{PM_DISPLAY.get(self.selected_sensor_type, 'N/A')} (µg/m³)"
                }
            },
            "plotOptions": {"bar": {"borderRadius": 4}},
            "tooltip": {"enabled": True},
        }

        # js_options = window.JSON.parse(json.dumps(options))
        self.pm_chart = window.ApexCharts.new(
            window.document.querySelector("#pm25-chart"),
            window.JSON.parse(window.JSON.stringify(options)),
        )
        self.pm_chart.render()

    def prepare_chart_data(self, data):
        bangkok_timezone = timezone(timedelta(hours=7), name="Asia/Bangkok")
        series_data = []
        data_map = {}

        for item in data:
            dt = datetime.fromisoformat(item["timestamp"])

            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)

            dt = dt.astimezone(bangkok_timezone)

            key = dt.strftime("%Y-%m-%d %H")
            data_map[key] = item["value"]

        now = datetime.now(bangkok_timezone)

        for i in range(23, -1, -1):
            hour_dt = now - timedelta(hours=i)

            key = hour_dt.strftime("%Y-%m-%d %H")
            label = hour_dt.strftime("%H:00")

            value = data_map.get(key, 0)

            series_data.append(
                {
                    "x": label,
                    "y": value,
                    "fillColor": (
                        sensor_colors.get_sensor_color(self.selected_sensor_type, value)
                        if value > 0
                        else "#E5E7EB"
                    ),
                }
            )

        return series_data

    # when click marker
    async def on_click_station(self, station_id):
        self.set_panel_loading()
        station = self.station_objects.get(station_id)

        if not station:
            return

        self.selected_station_id = station_id
        self.update_station_panel(station)
        await self.update_chart(station_id)

    def update_station_panel(self, station):
        empty_view = document["panel_empty_state"]
        content_view = document["panel_content_state"]
        error_view = document["panel_error_state"]

        # Get data
        name_th = get_nested(station, "name_th")
        province = get_nested(station, "metadata", "province")

        coords = get_nested(station, "coordinates", "coordinates")
        climates = get_nested(station, "climates")
        climate_dict = {c["sensor_type"].lower(): c for c in climates}
        # print("Climate Dict: ", climate_dict)

        # Get Climates
        # pm_2_5 = get_nested(climate_dict, "pm_2_5", "value")
        # pm_10 = get_nested(climate_dict, "pm_10", "value")
        current_sensor_type = self.selected_sensor_type
        if current_sensor_type == "pm_0_1":
            current_sensor_type = "pm_0_1_forecast"
        time = get_nested(climate_dict, current_sensor_type, "timestamp")
        time_display = format_timestamp(time)
        pm_value = get_nested(climate_dict, current_sensor_type, "value")
        temperature = get_nested(climate_dict, "temperature", "value")
        humidity = get_nested(climate_dict, "humidity", "value")
        wind_speed = get_nested(climate_dict, "wind_speed", "value")

        if "panel_loading_state" in document:
            document["panel_loading_state"].classList.add("hidden")

        if pm_value:
            status = self.get_sensor_status(pm_value, current_sensor_type)
            label = status["label"]
            color = status["color"]
            image_path = status["img_path"]
            gradient = status["gradient"]

            document["panel_name_th"].text = f"{name_th} ({province})"
            document["panel_time"].text = f"ข้อมูลล่าสุด: {time_display}"
            document["panel_coords"].text = f"( {coords[1]}, {coords[0]} )"
            document["panel_label"].text = label
            base_label_classes = (
                "inline-flex px-4 py-1.5 text-sm font-medium rounded-full"
            )
            document["panel_label"].class_name = f"{base_label_classes} {color}"
            document["panel_pm_value"].text = pm_value
            # document["panel_gradient"].classList.add(gradient)
            document["panel_gradient"].class_name = (
                f"absolute inset-0 rounded-full blur-md {gradient}"
            )
            document["panel_image"].attrs["src"] = image_path
            document["panel_temperature"].text = f"{temperature} °C"
            document["panel_humidity"].text = f"{humidity} %"
            document["panel_wind_speed"].text = f"{wind_speed} กม./ชม."

            empty_view.classList.add("hidden")
            content_view.classList.remove("hidden")
            error_view.classList.add("hidden")

        else:
            empty_view.classList.add("hidden")
            content_view.classList.add("hidden")
            error_view.classList.remove("hidden")

    def set_panel_loading(self):
        """แสดงหน้า Loading และซ่อนหน้าอื่นๆ"""
        # ซ่อนหน้าอื่นๆ
        document["panel_empty_state"].classList.add("hidden")
        document["panel_content_state"].classList.add("hidden")
        document["panel_error_state"].classList.add("hidden")

        # แสดงหน้า Loading
        if "panel_loading_state" in document:
            document["panel_loading_state"].classList.remove("hidden")

    def show_chart_loading(self):
        section = document["pm-section"]

        if hasattr(self, "pm_chart"):
            try:
                self.pm_chart.destroy()
                del self.pm_chart
            except Exception:
                pass

        section.innerHTML = f"""
            <div class="bg-white rounded-2xl shadow-lg border border-gray-100 p-6 mt-6">
                
                <div class="flex items-center gap-4 bg-white p-4 rounded-xl max-w-md">
                    <div class="w-12 h-12 rounded-xl bg-gray-200"></div> 
                    <div class="flex flex-col gap-2 w-full">
                        <div class="h-6 bg-gray-200 rounded w-3/4"></div> 
                        <div class="h-4 bg-gray-100 rounded w-1/2"></div> 
                    </div>
                </div>

                <div class="relative h-[300px] mt-4 bg-gray-50 rounded-xl border border-gray-100 flex items-center justify-center">
                    
                    <div class="relative flex items-center justify-center">
                        <div class="w-12 h-12 border-4 border-gray-200 rounded-full"></div>
                        <div class="absolute w-12 h-12 border-4 border-blue-500 border-t-transparent rounded-full animate-spin"></div>
                    </div>

                </div>

                <div class="flex items-center justify-center gap-6 pt-4 mt-4 border-t border-gray-100">
                     <div class="h-4 bg-gray-100 rounded w-64"></div>
                </div>
            
            </div>
        """

        section.classList.remove("hidden")

    def reset_panel_to_empty(self):
        document["panel_empty_state"].classList.remove("hidden")
        document["panel_content_state"].classList.add("hidden")
        document["panel_error_state"].classList.add("hidden")
        document["pm-section"].classList.add("hidden")

        # Reset
        self.selected_station_id = None

    async def refresh_active_station_panel(self):
        self.reset_panel_to_empty()

    async def get_sensor_color(self, sensor_type, value):
        return sensor_colors.get_sensor_color(sensor_type, value)

    async def update_climate_marker(self, source, stations, target_timestamp=None):
        print("Update Climate: PM Only ")
        self.remove_climates_layer(source)

        # print("Stations: ", stations)
        markers = []
        bangkok_timezone = timezone(timedelta(hours=7), name="Asia/Bangkok")

        if source in self.empirical_forecasts:
            source = source.replace("empirical_", "")

        selected_pm = self.selected_sensor_type

        TARGET_PM_SENSORS = ["pm_0_1", "pm_1", "pm_2_5", "pm_10", "PM_0_1_forecast"]

        DISPLAY_ORDERS = [
            sensor_type.lower() for sensor_type in sensor_infos.HTML_SENSOR_NAMES.keys()
        ]
        # print("Display Orders: ", DISPLAY_ORDERS)

        # Main Loop for Create Markers
        for station in stations["stations"]:
            # Get id for Information panel(show image)
            self.station_objects[station["id"]] = station

            if station["name"] in self.panel_plus_sensors:
                continue

            # Search Field
            if self.search_input:
                if (
                    self.search_input not in station["name"]
                    and self.search_input not in station["name_th"]
                    and self.search_input not in station["metadata"]["area_th"]
                    and self.search_input not in station["metadata"]["province"]
                ):
                    continue

            # Get climates
            climates = station.get("climates", [])
            # print("Climates: ", climates)

            # Set Comprehension
            station_sensors = {s["sensor_type"].lower() for s in climates}
            # print("station_sensor", station_sensors)
            # {'pm_2_5_prediction', 'temperature', 'pressure', 'pm_2_5', 'humidity'}

            if selected_pm in TARGET_PM_SENSORS:
                if selected_pm not in station_sensors:
                    continue

            climates_dict = {s["sensor_type"].lower(): s for s in climates}
            # print("Climates Dict: ", climates_dict)

            if not climates:
                continue
                # animate = False
                # sensor_color = "DarkGrey"
                # tooltip_detail = f"""
                #     <b>{station['name_th']}</b><br>
                #     ขาดการเชื่อมต่อ"""
            else:
                if selected_pm == "pm_0_1":
                    selected_pm = "pm_0_1_forecast"
                target_data = climates_dict.get(selected_pm)
                # print("target_data", target_data)
                if target_data is None:
                    continue

                # target_data = climates_dict.get("PM_0_1_forecast")
                # print("Target Date", target_data)

                value = target_data.get("value") if target_data else None

                if selected_pm == "pm_2_5":
                    value_str = (
                        f"{value:.1f}" if isinstance(value, float) else str(value)
                    )
                else:
                    value_str = (
                        f"{value:.2f}" if isinstance(value, float) else str(value)
                    )
                if selected_pm == "pm_0_1_forecast":
                    selected_pm = "pm_0_1"
                sensor_color = await self.get_sensor_color(selected_pm, value)
                animate = True

                # print("Station", station)

                coords = get_nested(station, "coordinates", "coordinates")
                area_th = get_nested(station, "metadata", "area_th")
                region_key = get_nested(station, "metadata", "region")
                region = self.DISPLAY_REGION.get(region_key, "")
                province = get_nested(station, "metadata", "province")
                station_code = get_nested(station, "code")

                time = target_data.get("timestamp")
                time_display = format_timestamp(time)

                # Tooltip Marker
                # <b>{station['name_th']}</b><br>
                tooltip_detail = f"""
                    <b>{station_code} {station['name_th']}, {province}</b><br>
                    <b>สถานีกรมควบคุมมลพิษ (PCD)</b><br>
                    <b>{area_th}</b><br>
                    {f"<b>{region}</b><br>" if region else ""}
                    {PM_DISPLAY.get(selected_pm, "N/A")} : {value_str} µg/m³<br>
                    <b>{time_display}</b><br/>
                    """
            # Create Marker
            sensor_marker = self.leaflet.icon.pulse(
                {
                    "iconSize": [15, 15],
                    "color": sensor_color,
                    "fillColor": sensor_color,
                    "animate": animate,
                }
            )

            coordinates = station["coordinates"]["coordinates"]
            marker = (
                self.leaflet.marker(
                    [coordinates[1], coordinates[0]],
                    {"icon": sensor_marker, "customId": station["id"]},
                )
                .bindTooltip(tooltip_detail)
                .on(
                    "click",
                    lambda e: aio.run(
                        self.on_click_station(e.sourceTarget.options.customId)
                    ),
                )
            )

            markers.append(marker)

        # Set All markers in map
        if markers:
            self.sensor_markers_layer[source] = markers
            self.climate_markers_layers[source] = self.leaflet.layerGroup(
                markers
            ).addTo(self.map)

        await self.refresh_active_station_panel()

        # document["loading_map"].classList.add("hidden")
