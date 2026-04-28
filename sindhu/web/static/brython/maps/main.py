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


class MainMap(Map):
    def __init__(
        self,
        center,
        zoom,
        min_zoom,
        lang_code,
        # project_id,
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

        # ทำการกำหนด sensor types เพื่อเช็คค่า
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

    # async def render(self):
    #     self.map.on(
    #         "click", lambda ev: print(f"location: {ev.latlng.lat}, {ev.latlng.lng}")
    #     )  # map clicked will print mouse location

    async def update(
        self, document_id, data, is_live_update=True, target_timestamp=None
    ):
        document["loading_map"].className = "ui inactive inverted dimmer"

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
            print("Updating climate marker...")
            print(f"Document ID: {document_id}")
            await self.update_climate_marker(
                document_id, data, target_timestamp=target_timestamp
            )
            return

    def set_all_sensor_marker(self, marker_id):
        if marker_id in self.climate_markers_layers.keys():
            self.climate_markers_layers[marker_id] = self.leaflet.layerGroup(
                self.sensor_markers_layer[marker_id]
            ).addTo(self.map)

    ### Remove
    # Climates
    def remove_climates_layer(self, source):
        if source in self.climate_markers_layers.keys():
            self.map.removeLayer(self.climate_markers_layers.get(source))

    def remove_all_climate_legends(self):
        for key in self.climate_legends:
            self.remove_climate_legend(key)

    def remove_climate_legend(self, source):
        for key, value in self.climate_legends.items():
            if key == source and value:
                self.map.removeControl(value)

                self.climate_legends[source] = []

    ### Climates
    async def update_climate_legend(self, document_id):
        legend = self.leaflet.control({"position": "bottomleft"})
        container = document.createElement("div")
        container.setAttribute(
            "style",
            "background:white; padding:10px; border-radius:5px; box-shadow:0 0 10px rgba(0,0,0,0.2); font-size:14px;",
        )
        sensor_type_mapped_key = document_id.replace("empirical_", "").replace(
            "_prediction", ""
        )
        default_title = sensor_infos.HTML_CLIMATE_LEGEND_TITLES.get(
            sensor_type_mapped_key, ""
        )
        container.innerHTML = f"<strong>{default_title}</strong><br>"

        climate_legend_dict = {}

        climate_legend = sensor_infos.HTML_CLIMATE_LEGENDS.get(
            sensor_type_mapped_key, None
        )
        if climate_legend:
            for feature in climate_legend:
                fill_color = feature.get("fill", "Unknown")
                description = feature.get("DES", "Unknown")

                if description not in climate_legend:
                    climate_legend_dict[description] = fill_color

            for label in climate_legend_dict:
                container.innerHTML += (
                    f'<span style="display:inline-block;width:15px;height:15px;background:{climate_legend_dict[label]};'
                    'margin-right:5px;border:1px solid #000;"></span>'
                    f"{label}<br>"
                )

            container.innerHTML += "<br>*ข้อจำกัดการใช้ข้อมูล: เป็นข้อมูลจากงานวิจัยและผ่านการทดสอบ(Validation Test) เฉพาะในภาคใต้"
            legend.onAdd = lambda _: container
            legend.addTo(self.map)
            self.climate_legends[document_id] = legend

    def on_click_station(self, station_id):
        url = f"{self.station_view_url}{station_id}"

        window.open(url)

    async def get_sensor_color(self, sensor_type, value):
        return sensor_colors.get_sensor_color(sensor_type, value)

    async def update_climate_marker(self, document_id, data, target_timestamp=None):
        print(
            f"update_climate_marker: {document_id}, target_timestamp: {target_timestamp}"
        )
        markers = []
        bangkok_timezone = timezone(timedelta(hours=7), name="Asia/Bangkok")

        # if source in self.empirical_forecasts:
        # source = source.replace("empirical_", "")

        if document_id not in self.climate_legends:
            await self.update_climate_legend(document_id)

        sensor_type_mapped_key = document_id.replace("empirical_", "")

        DISPLAY_ORDERS = [
            sensor_type.lower() for sensor_type in sensor_infos.HTML_SENSOR_NAMES.keys()
        ]

        for station in data["stations"]:
            animate = True
            sensor_color = "DeepSkyBlue"
            tooltip_detail = ""
            has_wind = False
            rotate_direction = 0

            if station["name"] in self.panel_plus_sensors:
                continue

            climates = station.get("climates", [])
            if not climates:
                animate = False
                sensor_color = "DarkGrey"
                disactive_txt = {"th": "ขาดการเชื่อมต่อ", "en": "lost connection"}
                tooltip_detail = f"""
                <div align="left" style="font-size: 15px;">
                    <b>{station["name"]}</b><br/>
                    {disactive_txt[self.lang_code]}
                </div>
                """
            else:
                climates_dict = {}
                for sensor in climates:
                    if sensor["sensor_type"].lower() == "pm_2_5_prediction" and (
                        datetime.fromisoformat(sensor["timestamp"]) != target_timestamp
                    ):
                        continue

                    climates_dict[sensor["sensor_type"].lower()] = sensor

                wind_sensor = climates_dict.get("wind_direction")
                if wind_sensor and station.get("source") != "air4thai":
                    has_wind = True
                    rotate_direction = wind_sensor["value"]

                # Build sensor display order
                display_order = DISPLAY_ORDERS.copy()
                if (
                    sensor_type_mapped_key.lower() in display_order
                    and sensor_type_mapped_key in self.sensor_types
                ):
                    display_order.remove(sensor_type_mapped_key.lower())
                    display_order.insert(0, sensor_type_mapped_key.lower())

                # Add any new sensor types not in display list
                for s_type in climates_dict.keys():
                    if s_type not in display_order:
                        display_order.append(s_type)

                # Build sensor display text
                sensor_texts = []
                timestamp = target_timestamp if target_timestamp else None
                for sensor_type in display_order:
                    sensor = climates_dict.get(sensor_type)
                    if not sensor:
                        continue

                    value = sensor.get("value")
                    value_str = (
                        f"{value:.2f}" if isinstance(value, float) else str(value)
                    )
                    if sensor["value"] is None or sensor["value"] < 0:
                        animate = False

                        if sensor_type == "PM_0_1_forecast".lower():
                            msg = "<b>ไม่พบข้อมูลการพยากรณ์ </b><br/><em><b>หมายเหตุ:</b> สถานีนี้อาจจะมีข้อมูลไม่เพียงพอสำหรับการพยากรณ์<br/><br/>"
                        else:
                            msg = "<b>ไม่พบข้อมูล</b><br/>"
                        sensor_texts.append(
                            f"""
                            {sensor_infos.HTML_SENSOR_NAMES.get(sensor_type, sensor_type)}:
                            {msg}
                            """
                        )
                    else:
                        sensor_texts.append(
                            f"""
                            {sensor_infos.HTML_SENSOR_NAMES.get(sensor_type, sensor_type)}:
                            <b>{value_str}</b> {sensor_infos.HTML_SENSOR_UNITS.get(sensor_type, "")}<br/>
                            """
                        )

                    # Capture one timestamp for display
                    if not timestamp and sensor.get("timestamp"):
                        timestamp = datetime.fromisoformat(sensor["timestamp"])

                # Format timestamps
                if timestamp:
                    utc_ts = timestamp.replace(tzinfo=timezone.utc)
                    ict_ts = utc_ts.astimezone(bangkok_timezone)

                    tooltip_detail = f"""
                    <div align="left" style="font-size: 15px;">
                        <b>{station["name"]}</b><br/>
                        <b>{station["name_th"]}</b><br/>
                        <b>หมายเหตุ</b> ค่าที่แสดงเป็นข้อมูลรายชั่วโมง แต่การใช้สีอ้างอิงจากค่าเฉลี่ย 24 ชั่วโมง<br/>
                        อ้างอิงข้อมูลสีตาม AQI จากกรมควบคุมมลพิษ<br/>
                        {"".join(sensor_texts)}
                        {utc_ts.strftime("%d/%m/%Y %H:%M:%S %Z")}<br/>
                        {ict_ts.strftime("%d/%m/%Y %H:%M:%S %Z")}<br/>
                    </div>
                    """

            # Sensor color
            # sensors = {k: v["value"] for k, v in climates_dict.items()}
            sensors = {
                sensor["sensor_type"].lower(): sensor["value"]
                for sensor in climates
                if not (
                    sensor["sensor_type"].lower() == "pm_2_5_prediction"
                    and target_timestamp
                    and datetime.fromisoformat(sensor["timestamp"]) != target_timestamp
                )
            }

            sensor_types = self.sensor_types.copy()
            if document_id == "wind_direction":
                sensor_types.remove(document_id)

            if (
                sensor_type_mapped_key in sensor_types
                and sensor_type_mapped_key.lower() in sensors
            ):
                sensor_color = await self.get_sensor_color(
                    sensor_type_mapped_key, sensors[sensor_type_mapped_key.lower()]
                )
            else:
                for s_type in sensor_infos.HTML_SENSOR_NAMES:
                    if s_type in sensors:
                        sensor_color = await self.get_sensor_color(
                            s_type, sensors[s_type]
                        )
                        break

            marker_option = {}

            if has_wind:
                sensor_color = await self.get_sensor_color(
                    "wind_speed", sensors[sensor_type]
                )
                sensor_marker = self.leaflet.icon(
                    {
                        "iconUrl": f"/static/resources/marks/up_arrow_{sensor_color}.svg",
                        "iconSize": [15, 15],
                        "color": sensor_color,
                        "fillColor": sensor_color,
                    }
                )
                marker_option["rotationAngle"] = rotate_direction
            else:
                sensor_marker = self.leaflet.icon.pulse(
                    {
                        "iconSize": [15, 15],
                        "color": sensor_color,
                        "fillColor": sensor_color,
                        "animate": animate,
                    }
                )

            marker_option["customId"] = station["id"]
            marker_option["icon"] = sensor_marker

            # ดึง marker เก่าจาก cache ถ้าไม่มี default
            marker = self.sensor_markers.get(station["id"], None)
            # ใช้สำหรับเช็ค marker สำหรับสร้าง Marker

            # create new marker
            if document_id not in self.sensor_markers_layer:
                coordinates = station["coordinates"]["coordinates"]
                marker = (
                    self.leaflet.marker(
                        [coordinates[1], coordinates[0]],
                        marker_option,
                    ).bindTooltip(
                        tooltip_detail,
                        {"offset": (0, 30), "className": "tooltip-marker"},
                    )
                    # add to map
                    .addTo(self.map)
                    # add event
                    .on(
                        "click",
                        lambda e: self.on_click_station(
                            e.sourceTarget.options.customId
                        ),
                        """
                        e.sourceTarget = marker ที่ถูกคลิก

                        options.customId = id ของ station (คุณคงใส่ไว้ตอนสร้าง marker_option)

                        เรียกฟังก์ชัน self.on_click_station(id) → เพื่อให้โหลดข้อมูลสถานีเวลาคลิก
                    """,
                    )
                )

                markers.append(marker)
                self.sensor_markers[station["id"]] = marker
            # Update marker
            else:
                marker.setIcon(sensor_marker)
                marker.setTooltipContent(tooltip_detail)

            if marker not in markers:
                markers.append(marker)

        # Create layer group for sensors and add to map
        self.sensor_markers_layer[document_id] = markers

        # Pack markers into layer group for better performance when adding/removing from map
        self.climate_markers_layers[document_id] = self.leaflet.layerGroup(
            self.sensor_markers_layer[document_id]
        ).addTo(self.map)

    ### Hotspots
    def set_all_hotspots_marker(self, satellite):
        if satellite in self.hotspot_markers_layers.keys():
            self.hotspot_markers_layers[satellite] = self.leaflet.layerGroup(
                self.sensor_markers_layer[satellite]
            ).addTo(self.map)

    def remove_all_hotspot_legends(self):
        for key in self.hotspot_legends:
            self.remove_hotspot_legend(key)

    def remove_hotspot_legend(self, source):
        for key, value in self.hotspot_legends.items():
            if key == source and value:
                self.map.removeControl(value)

                self.hotspot_legends[source] = []

    def remove_all_hotspots_layer(self):
        for key in self.hotspot_markers_layers.keys():
            if key in self.hotspots:
                self.remove_hotspots_layer(key)

    def remove_hotspots_layer(self, satellite):
        # self.hotspot_markers_layers[satellite].clearLayers()
        for key, value in self.sensor_markers_layer.items():
            if key == satellite:
                for v in value:
                    self.map.removeLayer(v)

    async def get_hotspot_color(self, satellite, value):
        return hotspot_colors.get_hotspot_color(satellite, value)

    def generate_hotspot_tooltip(self, hotspot, bangkok_timezone):

        hotspot_texts = []
        for sensor_type in hotspot_infos.HTML_HOTSPOT_SENSOR_NAMES:
            hotspot_texts.append(
                f"""{sensor_type}: <b>{hotspot["metadata"][sensor_type]}</b><br/>"""
            )

        timestamp = datetime.fromisoformat(hotspot["timestamp"])
        utc_time = timestamp.replace(tzinfo=timezone.utc)
        ict_time = utc_time.astimezone(bangkok_timezone)

        return f"""
            <div align="left" style="font-size: 15px;">
                <b>{hotspot["station_code"]}</b><br/>
                {"".join(hotspot_texts)}
                {utc_time.strftime("%d/%m/%Y %H:%M:%S %Z")}<br/>
                {ict_time.strftime("%d/%m/%Y %H:%M:%S %Z")}<br/>
            </div>
        """

    async def update_hotspot_legend(self, source):
        legend = self.leaflet.control({"position": "bottomleft"})
        container = document.createElement("div")
        container.setAttribute(
            "style",
            "background:white; padding:10px; border-radius:5px; box-shadow:0 0 10px rgba(0,0,0,0.2); font-size:14px;",
        )
        default_title = hotspot_infos.HTML_HOTSPOT_LEGEND_TITLES.get(source.lower(), "")
        container.innerHTML = f"<strong>{default_title}</strong><br>"

        hotspot_legend_dict = {}

        hotspot_legend = hotspot_infos.HTML_HOTSPOT_LEGENDS.get(source.lower(), None)
        if hotspot_legend:
            for feature in hotspot_legend:
                fill_color = feature.get("fill", "Unknown")
                description = feature.get("DES", "Unknown")

                if description not in hotspot_legend:
                    hotspot_legend_dict[description] = fill_color

        for label in hotspot_legend_dict:
            container.innerHTML += (
                f'<span style="display:inline-block;width:15px;height:15px;background:{hotspot_legend_dict[label]};'
                'margin-right:5px;border:1px solid #000;"></span>'
                f"{label}<br>"
            )

        legend.onAdd = lambda _: container
        legend.addTo(self.map)
        self.hotspot_legends[source] = legend

    async def update_hotspot_marker(self, satellite, hotspots, is_live_update=True):
        bangkok_timezone = timezone(timedelta(hours=7), name="Asia/Bangkok")
        batch_size = 300

        if satellite not in self.hotspot_markers_layers:
            self.hotspot_markers_layers[satellite] = self.leaflet.layerGroup().addTo(
                self.map
            )

        if satellite not in self.sensor_markers_layer:
            self.sensor_markers_layer[satellite] = []

        for i, hotspot in enumerate(hotspots["hotspots"]):
            marker = self.sensor_markers.get(hotspot["id"])
            if marker is None:
                # tooltip_detail = self.generate_hotspot_tooltip(
                #     hotspot, bangkok_timezone
                # )

                coordinates = hotspot["metadata"]["coordinates"]["coordinates"]
                satellite_name = hotspot["station_code"]
                hotspot_color = await self.get_hotspot_color(
                    satellite_name, hotspot["metadata"]["confidence"]
                )

                marker = self.leaflet.circle(
                    [coordinates[1], coordinates[0]],
                    {
                        "color": hotspot_color,
                        "fillColor": hotspot_color,
                        "fillOpacity": 0.5,
                        "radius": 1000,
                    },
                )
                # .bindTooltip(
                #     tooltip_detail,
                #     {"offset": (0, 30), "className": "tooltip-marker"},
                # )

                self.sensor_markers[hotspot["id"]] = marker

            self.sensor_markers_layer[satellite].append(marker)
            self.hotspot_markers_layers[satellite].addLayer(marker)

            if is_live_update and i % batch_size == 0:
                await aio.sleep(0)

    ### Fire Report
    def remove_all_fire_report_layers(self):
        for key in self.fire_reports:
            self.remove_fire_report_layer(key)

    def remove_fire_report_layer(self, report_name):
        if report_name in self.fire_report_layers.keys():
            self.map.removeLayer(self.fire_report_layers.get(report_name))

    def remove_all_fire_report_legends(self):
        for key in self.fire_report_legends:
            self.remove_fire_report_legend(key)

    def remove_fire_report_legend(self, report_name):
        for key, value in self.fire_report_legends.items():
            if key == report_name and value:
                self.map.removeControl(value)

                self.fire_report_legends[report_name] = []

    async def update_fire_report_legend(self, report_name, fire_port_legend):
        legend = self.leaflet.control({"position": "bottomleft"})
        container = document.createElement("div")
        container.setAttribute(
            "style",
            "background:white; padding:10px; border-radius:5px; box-shadow:0 0 10px rgba(0,0,0,0.2); font-size:14px;",
        )
        default_title = fire_report_infos.HTML_FIRE_REPORT_LEGEND_TITLES.get(
            report_name.lower(), ""
        )

        event_title = fire_port_legend.get("event", "").strip()

        container.innerHTML = f"<strong>{default_title}</strong><br>"
        if report_name == "MLBA" and event_title:
            container.innerHTML += f"<strong>{event_title} Event</strong><br>"

        for label, color in fire_port_legend.items():
            if label != "event":
                container.innerHTML += (
                    f'<span style="display:inline-block;width:15px;height:15px;background:{color};'
                    'margin-right:5px;border:1px solid #000;"></span>'
                    f"{label}<br>"
                )

        legend.onAdd = lambda _: container
        legend.addTo(self.map)
        self.fire_report_legends[report_name] = legend

    async def update_fire_report(self, report_name, fire_report):
        layers = []
        fire_report_legend = {}

        get_fire_report_legend = fire_report_infos.HTML_FIRE_REPORT_LEGENDS.get(
            report_name.lower(), None
        )
        if get_fire_report_legend:
            for feature in get_fire_report_legend:
                fill_color = feature.get("fill", "Unknown")
                description = feature.get("DES", "Unknown")

                if report_name == "MLBA":
                    for feature in fire_report["features"]:
                        mlba_event = feature["properties"]["Event"]

                        if mlba_event:
                            fire_report_legend["event"] = mlba_event

                            break

                if description not in fire_report_legend:
                    fire_report_legend[description] = fill_color

        await self.update_fire_report_legend(report_name, fire_report_legend)

        geojson = self.leaflet.geoJson(
            fire_report,
            {
                "style": lambda feature: {
                    **fire_report_infos.get_fire_report_style(report_name=report_name),
                    "fillColor": feature["properties"]["fill"],
                },
                "onEachFeature": lambda feature, layer: layer.bindPopup(
                    feature["properties"][
                        fire_report_infos.get_fire_report_popup(report_name=report_name)
                    ]
                ),
            },
        ).addTo(self.map)

        layers.append(geojson)
        self.fire_report_layers[report_name] = self.leaflet.layerGroup(layers).addTo(
            self.map
        )
