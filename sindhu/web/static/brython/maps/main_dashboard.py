from datetime import datetime, timezone, timedelta

from browser import ajax, document, html, window, timer, aio
import javascript as js

from .map import Map

from stations import (
    sensor_colors,
    sensor_infos,
    hotspot_colors,
    hotspot_infos,
    fire_report_infos,
)


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


PM_DISPLAY = {
    "pm_0_1": "PM₀.₁",
    "pm_1": "PM₁",
    "pm_2_5": "PM₂.₅",
    "pm_10": "PM₁₀",
}


class MainDashboardMap(Map):
    def __init__(self, center, zoom, min_zoom, lang_code, api_url):
        super().__init__(center, zoom, min_zoom)

        self.climate_markers_layers = {}
        self.sensor_markers = {}
        self.sensor_markers_layer = {}
        self.station_objects = {}
        self.climate_markers_visible = True
        # self.search_input = None

        self.sensor_types = [
            "PM_0_1",
            "PM_0_1_forecast",
            "PM_1",
            "PM_2_5",
            "PM_2_5_prediction",
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

        self.panel_plus_sensors = [
            "หมู่บ้านอิงกมล",
            "สำนักสงฆ์ย่านยาว",
            "เทศบาลบ้านไร่",
            "ไฮโซคีโมยำ",
            "เทศบาลพะตง",
            "Panel Plus",
        ]

        self.empirical_forecasts = [
            "empirical_PM_0_1_forecast",
            "empirical_PM_0_1",
            "empirical_PM_1",
        ]

        self.predictions = ["PM_2_5_prediction"]

        self.DISPLAY_REGION = {
            "south": "ภาคใต้",
            "all": "ทั้งหมด",
            "bangkok_vicinity": "กรุงเทพฯและปริมณฑล",
            "north": "ภาคเหนือ",
            "northeast": "ภาคตะวันออกเฉียงเหนือ",
            "central_west": "ภาคกลางและตะวันตก",
            "east": "ภาคตะวันออก",
        }
        self.api_url = api_url
        self.get_climate_last_24_hours_url = (
            f"{api_url}/v1/stations/climates/last_24_hours"
        )

        # Callback
        self.on_station_click_callback = None

    def set_on_station_click_listener(self, callback):
        self.on_station_click_callback = callback

    async def on_click_station(self, station_id):
        if self.on_station_click_callback:
            station_data = self.station_objects.get(station_id)
            await self.on_station_click_callback(station_id, station_data)

        # station = self.station_objects.get(station_id)
        # print("Station", station)

        # panel_empty_state = document["panel_empty_state"]
        # panel_empty_state.classList.add("hidden")

        # panel_content_state = document["panel_content_state"]
        # panel_content_state.classList.remove("hidden")

    async def get_sensor_color(self, sensor_type, value):
        return sensor_colors.get_sensor_color(sensor_type, value)

    async def update(
        self, document_id, data, is_live_update=True, target_timestamp=None
    ):
        print("Main Dashboard Update")

        if (
            document_id
            in self.sensor_types
            + self.sources
            + self.empirical_forecasts
            + self.predictions
        ):

            await self.update_climate_marker(
                document_id, data, target_timestamp=target_timestamp
            )
            return
        # document["loading_map"]

    async def update_climate_marker(self, source, stations, target_timestamp=None):
        # print("Update PM2.5 Prediction")
        self.remove_climates_layer(source)
        # source = "PM_2_5_prediction"
        markers = []
        bangkok_timezone = timezone(timedelta(hours=7), name="Asia/Bangkok")

        if source in self.empirical_forecasts:
            source = source.replace("empirical_", "")

        DISPLAY_ORDERS = [
            sensor_type.lower() for sensor_type in sensor_infos.HTML_SENSOR_NAMES.keys()
        ]

        # print("DISPLAY ORDERS", DISPLAY_ORDERS)

        for station in stations["stations"]:
            self.station_objects[station["id"]] = station

            if station["name"] in self.panel_plus_sensors:
                continue

            climates = station.get("climates", [])
            # print("Climates: ", climates)

            # station_sensors = {s["sensor_type"].lower() for s in climates}
            # print("Station Sensor: ", station_sensors)
            # {'pm_2_5_prediction', 'pm_0_1', 'pm_2_5', 'pm_1'}

            climates_dict = {s["sensor_type"].lower(): s for s in climates}
            # print("Climates Dict", climates_dict)
            if not climates:
                animate = False
                sensor_color = "DarkGrey"
                tooltip_detail = f"""
                    <b>{station['name_th']}</b><br>
                    ขาดการเชื่อมต่อ"""

            else:
                # target = "pm_2_5_prediction"
                # target_data = climates_dict.get(target)

                target_prediction_data = None

                if target_timestamp:
                    for c in climates:
                        if c["sensor_type"].lower() == "pm_2_5_prediction":
                            c_time = datetime.fromisoformat(
                                c["timestamp"].replace("Z", "+00:00")
                            )
                            if c_time.date() == target_timestamp.date():
                                target_prediction_data = c
                                break
                # print("Target Prediction Data", target_prediction_data)

                sensor_texts = []

                if target_prediction_data:
                    value = target_prediction_data.get("value")
                    value_str = (
                        f"{value:.2f}" if isinstance(value, float) else str(value)
                    )
                    sensor_color = await self.get_sensor_color("PM_2_5", value)
                    animate = True

                    area_th = get_nested(station, "metadata", "area_th")
                    region_key = get_nested(station, "metadata", "region")
                    region = self.DISPLAY_REGION.get(region_key, "")
                    province = get_nested(station, "metadata", "province")

                    # Tooltip Marker
                    tooltip_detail = f"""
                        <b>{station['name']} ({province})</b><br>
                        <b>{station['name_th']}</b><br>
                        <b>{area_th}</b><br>
                        {f"<b>{region}</b><br>" if region else ""}
                        PM<sub>2.5</sub> (Prediction)" : {value_str} µg/m³
                        """

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
                self.climate_markers_layers[source] = self.leaflet.layerGroup(markers)
                if self.climate_markers_visible:
                    self.climate_markers_layers[source].addTo(self.map)

    def remove_climates_layer(self, source=None):
        for key in list(self.climate_markers_layers.keys()):
            layer = self.climate_markers_layers[key]

            if self.map.hasLayer(layer):
                self.map.removeLayer(layer)

            del self.climate_markers_layers[key]

    def toggle_layers(self, show):
        self.climate_markers_visible = show
        for source, layer in self.climate_markers_layers.items():
            if show:
                # ถ้าให้แสดง และยังไม่มีใน map ให้ add เข้าไป
                if not self.map.hasLayer(layer):
                    layer.addTo(self.map)
            else:
                # ถ้าให้ซ่อน และมีใน map ให้ remove ออก
                if self.map.hasLayer(layer):
                    self.map.removeLayer(layer)
