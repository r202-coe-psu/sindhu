from datetime import datetime, timezone, timedelta


from browser import ajax, document, html, window, timer, aio
import javascript as js

from .map import Map

class BaseMap(Map):
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
        self.metrics_markers_layers = {}
        self.metrics_legends = {}
        self.interpolate_layers = {}

    """
    ===========================================================================
    Main functions
    ===========================================================================
    """

    async def update(
        self, document_id, data, is_live_update=True, target_timestamp=None
    ):
        # logic handler
        print("Updating climate marker...")
        print(f"Document ID: {document_id}")
        await self.update_climate_marker(
            document_id, data, target_timestamp=target_timestamp
        )
        await aio.sleep(0.5)

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

    
    """
    ===========================================================================
    Helper functions
    ===========================================================================
    """