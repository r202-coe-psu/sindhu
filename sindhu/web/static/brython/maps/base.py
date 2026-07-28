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
        self.metric_markers_by_key = {}
        self.metric_markers_layer = {}
        self.metric_types = []
        self.panel_plus_sensors = []
        self.marker_style = "donut"
        self._metric_legend_container = None

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
                "dwr": "badge-success text-success-content",
                "dwr_telemetry": "badge-success text-success-content",
            }
            badge_color = badge_color_map.get(source_lower, "badge-neutral")

            # Credit the agency that publishes this station's data
            source_credit = metric_infos.get_source_credit(source_lower)
            credit_html = ""
            credit_footer_html = ""
            if source_credit:
                credit_html = f"""
                <div class="flex items-start gap-1 text-[9px] text-base-content/50 leading-tight">
                    <i class="ph ph-database mt-px"></i>
                    <span>ที่มาข้อมูล: {source_credit["name"]}</span>
                </div>
                """
                credit_footer_html = f"""
                <div class="border-t border-base-content/10 pt-1 mt-1">
                    {credit_html}
                </div>
                """

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
                        {credit_footer_html}
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
                        sensor["value"] < 0
                        and metric_type
                        not in ["diff_wl_bank", "waterlevel", "waterlevel_msl"]
                    ):
                        animate = False

                        if metric_type == "PM_0_1_forecast".lower():
                            msg = "ไม่พบข้อมูลการพยากรณ์"
                        else:
                            msg = "ไม่พบข้อมูล"
                        metric_texts.append(f"""
                            <div class="flex justify-between items-center text-xs py-0.5 border-b border-base-content/5 last:border-0">
                                <span class="opacity-70">{metric_infos.HTML_METRIC_NAMES.get(metric_type, metric_type)}</span>
                                <span class="text-base-content/40 italic text-[11px]">{msg}</span>
                            </div>
                            """)
                    else:
                        unit = metric_infos.HTML_METRIC_UNITS.get(metric_type, "")
                        metric_texts.append(f"""
                            <div class="flex justify-between items-center text-xs py-0.5 border-b border-base-content/5 last:border-0">
                                <span class="opacity-70">{metric_infos.HTML_METRIC_NAMES.get(metric_type, metric_type)}</span>
                                <span class="font-semibold text-base-content">{value_str} <span class="text-[10px] opacity-60 font-normal">{unit}</span></span>
                            </div>
                            """)

                    # Capture one timestamp for display
                    if not timestamp and sensor.get("timestamp"):
                        timestamp = datetime.fromisoformat(sensor["timestamp"])

                # Format timestamps
                timestamp_html = ""
                footer_html = ""
                if timestamp:
                    utc_ts = timestamp.replace(tzinfo=timezone.utc)
                    ict_ts = utc_ts.astimezone(bangkok_timezone)
                    timestamp_html = f"""
                    <div class="text-[9px] text-base-content/40 flex flex-col gap-0.5 font-mono">
                        <div>UTC: {utc_ts.strftime("%d/%m/%Y %H:%M:%S")}</div>
                        <div>ICT: {ict_ts.strftime("%d/%m/%Y %H:%M:%S")}</div>
                    </div>
                    """

                if credit_html or timestamp_html:
                    footer_html = f"""
                    <div class="border-t border-base-content/10 pt-1 mt-1 flex flex-col gap-0.5">
                        {credit_html}
                        {timestamp_html}
                    </div>
                    """

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
                        {footer_html}
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

            # Which metric decides this marker's colour and fill level
            primary_type = None
            primary_value = None
            if (
                metric_type_mapped_key in metric_types
                and metric_type_mapped_key.lower() in metrics
            ):
                primary_type = metric_type_mapped_key.lower()
                primary_value = metrics[primary_type]
            else:
                primary_type, primary_value = metric_infos.pick_primary_metric(metrics)

            if primary_type is None:
                for s_type in metric_infos.HTML_METRIC_NAMES:
                    if s_type in metrics:
                        primary_type = s_type
                        primary_value = metrics[s_type]
                        break

            if primary_type is not None:
                metric_color = await self.get_metric_color(primary_type, primary_value)

            marker_option = {}

            if has_wind:
                wind_speed_val = metrics.get("wind_speed", 0)
                metric_color = await self.get_metric_color("wind_speed", wind_speed_val)
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

                if "risk_percent" in station:
                    percent = station["risk_percent"]
                else:
                    # storage_percent is no longer emitted, so fall back to
                    # how far up its own scale the station's metric sits
                    percent = metric_infos.get_metric_fill_percent(
                        primary_type, primary_value
                    )
                if percent is None:
                    percent = 0
                percent = min(max(percent, 0), 100)

                if "risk_color" in station:
                    metric_color = station["risk_color"]

                if style == "donut":
                    html_content = f'<div style="width: 24px; height: 24px; border-radius: 50%; background: conic-gradient({metric_color} {percent}%, #e5e7eb 0); border: 2px solid white; box-shadow: 0 0 4px rgba(0,0,0,0.3);"></div>'
                    metric_marker = self.leaflet.divIcon(
                        {
                            "className": "custom-div-icon",
                            "html": html_content,
                            "iconSize": [24, 24],
                            "iconAnchor": [12, 12],
                        }
                    )
                elif style == "drop":
                    html_content = f'<div style="width: 24px; height: 24px; display: flex; align-items: center; justify-content: center; filter: drop-shadow(0 2px 2px rgba(0,0,0,0.3));"><svg viewBox="0 0 24 24" fill="{metric_color}" width="24" height="24"><path d="M12 21.5c-3.3 0-6-2.7-6-6 0-3.1 3.5-8.5 5.5-11.3.3-.4.8-.4 1 0 2 2.8 5.5 8.2 5.5 11.3 0 3.3-2.7 6-6 6z"/></svg></div>'
                    metric_marker = self.leaflet.divIcon(
                        {
                            "className": "custom-div-icon",
                            "html": html_content,
                            "iconSize": [24, 24],
                            "iconAnchor": [12, 12],
                        }
                    )
                elif style == "tank":
                    html_content = f'<div style="width: 14px; height: 28px; border-radius: 6px; border: 2px solid #cbd5e1; background: white; position: relative; overflow: hidden; box-shadow: 0 2px 4px rgba(0,0,0,0.3);"><div style="position: absolute; bottom: 0; left: 0; width: 100%; height: {percent}%; background-color: {metric_color}; transition: height 0.3s ease;"></div></div>'
                    metric_marker = self.leaflet.divIcon(
                        {
                            "className": "custom-div-icon",
                            "html": html_content,
                            "iconSize": [14, 28],
                            "iconAnchor": [7, 14],
                        }
                    )
                elif style == "bubble":
                    size = max(12, min(percent / 2.5, 40))
                    html_content = f'<div style="width: {size}px; height: {size}px; border-radius: 50%; background-color: {metric_color}; border: 2px solid white; opacity: 0.85; box-shadow: 0 2px 4px rgba(0,0,0,0.3);"></div>'
                    metric_marker = self.leaflet.divIcon(
                        {
                            "className": "custom-div-icon",
                            "html": html_content,
                            "iconSize": [size, size],
                            "iconAnchor": [size / 2, size / 2],
                        }
                    )
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
            # L.Marker defaults to bubblingMouseEvents: false, which stops the
            # click before the map ever sees it — with a station under the
            # cursor, pin mode would silently do nothing.
            marker_option["bubblingMouseEvents"] = True

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
                code = station.get("code")
                if code:
                    # rid and dwr_telemetry publish the same station codes, so
                    # a code maps to a list and (source, code) is the exact key
                    self.metric_markers_by_code.setdefault(code, []).append(marker)
                    self.metric_markers_by_key[
                        self.marker_key(source_lower, code)
                    ] = marker
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
        """Draw the colour scale of the active metric on top of the map.

        The bands come from `metric_infos.get_metric_levels`, which reads the
        same `metric_colors` ranks the markers use, so the legend can never
        describe colours the map does not actually draw.
        """
        from browser import document as doc

        metric_type = document_id.replace("empirical_", "").lower()
        levels = metric_infos.get_metric_levels(metric_type)
        if not levels:
            self.metric_legends[document_id] = True
            return

        rows = ""
        for level in levels:
            rows += f"""
            <div class="flex items-center gap-2">
                <span class="inline-block w-4 h-3 rounded-sm shrink-0 border border-gray-300" style="background-color: {level["color"]};"></span>
                <span class="text-[11px] text-gray-700 leading-tight">{level["label"]}</span>
                <span class="text-[10px] text-gray-400 leading-tight ml-auto pl-2 whitespace-nowrap">{level["range"]}</span>
            </div>
            """

        container = self._metric_legend_container
        if container is None:
            container = doc.createElement("div")
            container.style.cssText = (
                "position:absolute;bottom:12px;left:12px;z-index:1000;max-width:220px;"
            )
            self.map.getContainer() <= container
            self._metric_legend_container = container
            # Keep clicks and wheel events on the legend out of the map
            self.leaflet.DomEvent.disableClickPropagation(container)
            self.leaflet.DomEvent.disableScrollPropagation(container)

        title = metric_infos.get_metric_level_title(metric_type)
        container.html = f"""
        <div class="bg-white/95 backdrop-blur-sm border border-gray-200 rounded-xl shadow-md px-3 py-2">
            <div class="flex items-center gap-1.5 pb-1 mb-1.5 border-b border-gray-100">
                <i class="ph ph-palette text-blue-600 text-sm"></i>
                <div class="leading-tight">
                    <div class="text-[11px] font-semibold text-gray-700">{title}</div>
                    <div class="text-[9px] text-gray-400">ระดับความปลอดภัย</div>
                </div>
            </div>
            <div class="flex flex-col gap-1">
                {rows}
            </div>
        </div>
        """

        self.metric_legends[document_id] = True

    def marker_key(self, source, code):
        return f"{str(source).lower()}:{code}"

    def filter_markers_by_codes(self, station_codes):
        """Keep only the markers for these codes, whatever source they came from.

        Use this when the caller genuinely means "these stations" — zone
        membership, for example. When a source filter is in play use
        `filter_markers_by_keys` instead, because one code can carry two
        markers.
        """
        code_set = set(str(code) for code in station_codes)
        for code, markers in self.metric_markers_by_code.items():
            wanted = code in code_set
            for marker in markers:
                on_map = self.map.hasLayer(marker)
                if wanted and not on_map:
                    marker.addTo(self.map)
                elif not wanted and on_map:
                    self.map.removeLayer(marker)

    def filter_markers_by_keys(self, station_keys):
        """Keep only the markers for these `marker_key(source, code)` keys.

        rid and dwr_telemetry publish the same gauge codes, so filtering by
        code alone leaves the other source's marker on the map while the
        station panel drops it. Keying on the source as well is what keeps
        the two views describing the same set of stations.
        """
        key_set = set(station_keys)
        for key, marker in self.metric_markers_by_key.items():
            wanted = key in key_set
            on_map = self.map.hasLayer(marker)
            if wanted and not on_map:
                marker.addTo(self.map)
            elif not wanted and on_map:
                self.map.removeLayer(marker)

    def show_all_markers(self):
        for station_id, marker in self.metric_markers.items():
            if not self.map.hasLayer(marker):
                marker.addTo(self.map)

    def close_all_tooltips(self):
        """Tooltips opened by a click stay open, so clear them before the next."""
        for marker in self.metric_markers.values():
            marker.closeTooltip()

    def reset_all(self):
        self.close_all_tooltips()
        super().reset_all()

    def fly_to_station(self, station_code, source=None, zoom=13):
        """Centre the map on a station marker and reveal its tooltip."""
        marker = None
        if source:
            marker = self.metric_markers_by_key.get(
                self.marker_key(source, station_code)
            )
        if not marker:
            markers = self.metric_markers_by_code.get(station_code) or []
            marker = markers[0] if markers else None
        if not marker:
            print(f"fly_to_station: no marker for code {station_code}")
            return False

        if not self.map.hasLayer(marker):
            marker.addTo(self.map)

        target_zoom = max(self.map.getZoom(), zoom)
        self.map.flyTo(marker.getLatLng(), target_zoom)

        # Only the station picked from the panel should be labelled
        self.close_all_tooltips()
        marker.openTooltip()

        # Zooming to one station is also a state the user needs a way out of
        self.show_reset_button()
        return True

    def on_click_station(self, station_id):
        print(f"Station clicked: {station_id}")
