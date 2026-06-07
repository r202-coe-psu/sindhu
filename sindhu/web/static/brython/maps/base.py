from datetime import datetime, timezone, timedelta


from browser import ajax, document, html, window, timer, aio
import javascript as js

from .map import Map
from stations import metric_infos
from stations.metric_colors import get_metric_color as _get_metric_color

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
        self.metric_markers_layers = {}
        self.metric_legends = {}
        self.interpolate_layers = {}
        
        self.metric_markers = {}
        self.metric_markers_by_code = {}
        self.metric_markers_layer = {}
        self.metric_types = []
        self.panel_plus_sensors = []
        self.marker_style = "donut"

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
        await self.update_metric_marker(
            document_id, data, target_timestamp=target_timestamp
        )
        await aio.sleep(0.5)

    async def update_metric_marker(self, document_id, data, target_timestamp=None):
        print(
            f"update_metric_marker: {document_id}, target_timestamp: {target_timestamp}"
        )
        markers = []
        bangkok_timezone = timezone(timedelta(hours=7), name="Asia/Bangkok")

        # if source in self.empirical_forecasts:
        # source = source.replace("empirical_", "")

        if document_id not in self.metric_legends:
            await self.update_metric_legend(document_id)

        metric_type_mapped_key = document_id.replace("empirical_", "")

        DISPLAY_ORDERS = [
            metric_type.lower() for metric_type in metric_infos.HTML_METRIC_NAMES.keys()
        ]

        for station in data["stations"]:
            animate = False
            metric_color = "DeepSkyBlue"
            tooltip_detail = ""
            has_wind = False
            rotate_direction = 0

            if station["name"] in self.panel_plus_sensors:
                continue

            # Determine badge color based on source
            source_name = station.get("source", "")
            source_lower = source_name.lower()
            badge_color_map = {
                "thaiwater": "badge-info text-info-content",
                "rid": "badge-error text-error-content",
                "dwr": "badge-success text-success-content"
            }
            badge_color = badge_color_map.get(source_lower, "badge-neutral")

            metrics = station.get("metrics", [])
            if not metrics:
                animate = False
                metric_color = "DarkGrey"
                disactive_txt = {"th": "ขาดการเชื่อมต่อ", "en": "lost connection"}
                tooltip_detail = f"""
                <div class="card card-compact w-64 bg-base-100 shadow-xl border border-base-content/10 text-base-content overflow-hidden">
                    <div class="card-body p-3 gap-1.5">
                        <div class="flex justify-between items-center border-b border-base-content/10 pb-1 mb-1">
                            <span class="badge {badge_color} badge-xs font-semibold px-2 py-1.5">{source_name.upper()}</span>
                            <span class="text-[10px] font-mono opacity-60">#{station["code"]}</span>
                        </div>
                        <div>
                            <h3 class="font-bold text-sm text-base-content leading-snug">{station.get("name_th", "")}</h3>
                            <p class="text-[11px] text-base-content/60 font-mono mt-0.5">{station["name"]}</p>
                        </div>
                        <div class="text-xs font-semibold text-error mt-1.5 flex items-center gap-1">
                            <span class="relative flex h-2 w-2">
                                <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-error opacity-75"></span>
                                <span class="relative inline-flex rounded-full h-2 w-2 bg-error"></span>
                            </span>
                            {disactive_txt[self.lang_code]}
                        </div>
                    </div>
                </div>
                """
            else:
                metrics_dict = {}
                for sensor in metrics:
                    if sensor["metric_type"].lower() == "pm_2_5_prediction" and (
                        datetime.fromisoformat(sensor["timestamp"]) != target_timestamp
                    ):
                        continue

                    metrics_dict[sensor["metric_type"].lower()] = sensor

                wind_sensor = metrics_dict.get("wind_direction")
                if wind_sensor and station.get("source") != "air4thai":
                    has_wind = True
                    rotate_direction = wind_sensor["value"]

                # Build sensor display order
                display_order = DISPLAY_ORDERS.copy()
                if (
                    metric_type_mapped_key.lower() in display_order
                    and metric_type_mapped_key in self.metric_types
                ):
                    display_order.remove(metric_type_mapped_key.lower())
                    display_order.insert(0, metric_type_mapped_key.lower())

                # Add any new sensor types not in display list
                for s_type in metrics_dict.keys():
                    if s_type not in display_order:
                        display_order.append(s_type)

                # Build sensor display text
                metric_texts = []
                timestamp = target_timestamp if target_timestamp else None
                for metric_type in display_order:
                    sensor = metrics_dict.get(metric_type)
                    if not sensor:
                        continue

                    value = sensor.get("value")
                    value_str = (
                        f"{value:.2f}" if isinstance(value, float) else str(value)
                    )
                    if sensor["value"] is None or (
                        sensor["value"] < 0 and metric_type not in ["diff_wl_bank", "waterlevel_msl"]
                    ):
                        animate = False

                        if metric_type == "PM_0_1_forecast".lower():
                            msg = "ไม่พบข้อมูลการพยากรณ์"
                        else:
                            msg = "ไม่พบข้อมูล"
                        metric_texts.append(
                            f"""
                            <div class="flex justify-between items-center text-xs py-0.5 border-b border-base-content/5 last:border-0">
                                <span class="opacity-70">{metric_infos.HTML_METRIC_NAMES.get(metric_type, metric_type)}</span>
                                <span class="text-base-content/40 italic text-[11px]">{msg}</span>
                            </div>
                            """
                        )
                    else:
                        unit = metric_infos.HTML_METRIC_UNITS.get(metric_type, "")
                        metric_texts.append(
                            f"""
                            <div class="flex justify-between items-center text-xs py-0.5 border-b border-base-content/5 last:border-0">
                                <span class="opacity-70">{metric_infos.HTML_METRIC_NAMES.get(metric_type, metric_type)}</span>
                                <span class="font-semibold text-base-content">{value_str} <span class="text-[10px] opacity-60 font-normal">{unit}</span></span>
                            </div>
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
                    <div class="card card-compact w-64 bg-base-100 shadow-xl border border-base-content/10 text-base-content overflow-hidden">
                        <div class="card-body p-3 gap-1.5">
                            <div class="flex justify-between items-center border-b border-base-content/10 pb-1 mb-1">
                                <span class="badge {badge_color} badge-xs font-semibold px-2 py-1.5">{source_name.upper()}</span>
                                <span class="text-[10px] font-mono opacity-60">#{station["code"]}</span>
                            </div>
                            <div>
                                <h3 class="font-bold text-sm text-base-content leading-snug">{station["name_th"]}</h3>
                                <p class="text-[11px] text-base-content/60 font-mono mt-0.5">{station["name"]}</p>
                            </div>
                            <div class="flex flex-col gap-0.5 mt-1">
                                {"".join(metric_texts)}
                            </div>
                            <div class="border-t border-base-content/10 pt-1 mt-1 text-[9px] text-base-content/40 flex flex-col gap-0.5 font-mono">
                                <div>UTC: {utc_ts.strftime("%d/%m/%Y %H:%M:%S")}</div>
                                <div>ICT: {ict_ts.strftime("%d/%m/%Y %H:%M:%S")}</div>
                            </div>
                        </div>
                    </div>
                    """


            # Sensor color
            # metrics = {k: v["value"] for k, v in metrics_dict.items()}
            metrics = {
                sensor["metric_type"].lower(): sensor["value"]
                for sensor in metrics
                if not (
                    sensor["metric_type"].lower() == "pm_2_5_prediction"
                    and target_timestamp
                    and datetime.fromisoformat(sensor["timestamp"]) != target_timestamp
                )
            }

            metric_types = self.metric_types.copy()
            if document_id == "wind_direction":
                metric_types.remove(document_id)

            if (
                metric_type_mapped_key in metric_types
                and metric_type_mapped_key.lower() in metrics
            ):
                metric_color = await self.get_metric_color(
                    metric_type_mapped_key, metrics[metric_type_mapped_key.lower()]
                )
            else:
                for s_type in metric_infos.HTML_METRIC_NAMES:
                    if s_type in metrics:
                        metric_color = await self.get_metric_color(
                            s_type, metrics[s_type]
                        )
                        break

            marker_option = {}

            if has_wind:
                wind_speed_val = metrics.get("wind_speed", 0)
                metric_color = await self.get_metric_color(
                    "wind_speed", wind_speed_val
                )
                metric_marker = self.leaflet.icon(
                    {
                        "iconUrl": f"/static/resources/marks/up_arrow_{metric_color}.svg",
                        "iconSize": [15, 15],
                        "color": metric_color,
                        "fillColor": metric_color,
                    }
                )
                marker_option["rotationAngle"] = rotate_direction
            else:
                style = getattr(self, "marker_style", "donut")
                percent = metrics.get("storage_percent", 0)
                if percent is None: percent = 0
                percent = min(max(percent, 0), 100)
                
                if style == "donut":
                    html_content = f'<div style="width: 24px; height: 24px; border-radius: 50%; background: conic-gradient({metric_color} {percent}%, #e5e7eb 0); border: 2px solid white; box-shadow: 0 0 4px rgba(0,0,0,0.3);"></div>'
                    metric_marker = self.leaflet.divIcon({
                        "className": "custom-div-icon",
                        "html": html_content,
                        "iconSize": [24, 24],
                        "iconAnchor": [12, 12]
                    })
                elif style == "drop":
                    html_content = f'<div style="width: 24px; height: 24px; display: flex; align-items: center; justify-content: center; filter: drop-shadow(0 2px 2px rgba(0,0,0,0.3));"><svg viewBox="0 0 24 24" fill="{metric_color}" width="24" height="24"><path d="M12 21.5c-3.3 0-6-2.7-6-6 0-3.1 3.5-8.5 5.5-11.3.3-.4.8-.4 1 0 2 2.8 5.5 8.2 5.5 11.3 0 3.3-2.7 6-6 6z"/></svg></div>'
                    metric_marker = self.leaflet.divIcon({
                        "className": "custom-div-icon",
                        "html": html_content,
                        "iconSize": [24, 24],
                        "iconAnchor": [12, 12]
                    })
                elif style == "tank":
                    html_content = f'<div style="width: 14px; height: 28px; border-radius: 6px; border: 2px solid #cbd5e1; background: white; position: relative; overflow: hidden; box-shadow: 0 2px 4px rgba(0,0,0,0.3);"><div style="position: absolute; bottom: 0; left: 0; width: 100%; height: {percent}%; background-color: {metric_color}; transition: height 0.3s ease;"></div></div>'
                    metric_marker = self.leaflet.divIcon({
                        "className": "custom-div-icon",
                        "html": html_content,
                        "iconSize": [14, 28],
                        "iconAnchor": [7, 14]
                    })
                elif style == "bubble":
                    size = max(12, min(percent / 2.5, 40))
                    html_content = f'<div style="width: {size}px; height: {size}px; border-radius: 50%; background-color: {metric_color}; border: 2px solid white; opacity: 0.85; box-shadow: 0 2px 4px rgba(0,0,0,0.3);"></div>'
                    metric_marker = self.leaflet.divIcon({
                        "className": "custom-div-icon",
                        "html": html_content,
                        "iconSize": [size, size],
                        "iconAnchor": [size/2, size/2]
                    })
                else:
                    metric_marker = self.leaflet.icon.pulse(
                        {
                            "iconSize": [15, 15],
                            "color": metric_color,
                            "fillColor": metric_color,
                            "animate": False,
                        }
                    )

            marker_option["customId"] = station["id"]
            marker_option["icon"] = metric_marker

            # ดึง marker เก่าจาก cache ถ้าไม่มี default
            marker = self.metric_markers.get(station["id"], None)
            # ใช้สำหรับเช็ค marker สำหรับสร้าง Marker

            # create new marker
            if marker is None:
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
                self.metric_markers[station["id"]] = marker
                if station.get("code"):
                    self.metric_markers_by_code[station["code"]] = marker
            # Update marker
            else:
                marker.setIcon(metric_marker)
                marker.setTooltipContent(tooltip_detail)

            if marker not in markers:
                markers.append(marker)

        # Create layer group for sensors and add to map
        self.metric_markers_layer[document_id] = markers

        # Pack markers into layer group for better performance when adding/removing from map
        self.metric_markers_layers[document_id] = self.leaflet.layerGroup(
            self.metric_markers_layer[document_id]
        ).addTo(self.map)

    
    """
    ===========================================================================
    Helper functions
    ===========================================================================
    """

    async def get_metric_color(self, type_, value):
        return _get_metric_color(type_, value)

    async def update_metric_legend(self, document_id):
        self.metric_legends[document_id] = True

    def filter_markers_by_codes(self, station_codes):
        code_set = set(station_codes)
        visible = set()
        for code in code_set:
            m = self.metric_markers_by_code.get(code)
            if m:
                visible.add(code)
                if not self.map.hasLayer(m):
                    m.addTo(self.map)
        for code, marker in self.metric_markers_by_code.items():
            if code not in visible:
                if self.map.hasLayer(marker):
                    self.map.removeLayer(marker)

    def show_all_markers(self):
        for station_id, marker in self.metric_markers.items():
            if not self.map.hasLayer(marker):
                marker.addTo(self.map)

    def on_click_station(self, station_id):
        print(f"Station clicked: {station_id}")