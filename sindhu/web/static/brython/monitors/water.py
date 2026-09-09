from browser import document, aio, window
import javascript as js
import datetime
from urllib.parse import urlencode

from .base import BaseMonitor
from stations import metric_infos
from maps.map import _haversine_distance
import json


class WaterMonitor(BaseMonitor):
    def __init__(
        self,
        lang_code,
        api_url,
        source,
        center=None,
        zoom=None,
        fallback_zone_urls=None,
        reference_boundary_url=None,
        rivers_url=None,
    ):
        super().__init__(
            lang_code=lang_code,
            api_url=api_url,
            source=source,
            center=center,
            zoom=zoom,
            fallback_zone_urls=fallback_zone_urls,
            reference_boundary_url=reference_boundary_url,
            rivers_url=rivers_url,
        )
        self.monitor_name = "water"

        self.params = dict()
        self.latest_data = None
        self.visual_feed_monitor = None

    def calculate_risk(self, station):
        if not station or not isinstance(station, dict):
            return -1, None, None

        metadata = station.get("metadata") or {}
        if not isinstance(metadata, dict):
            metadata = {}

        wl_crit = metadata.get("water_level_critical")
        wl_warn = metadata.get("water_level_warning")

        waterlevel = None
        diff_wl_bank = None
        for m in station.get("metrics") or []:
            if not m or not isinstance(m, dict):
                continue
            m_type = (m.get("metric_type") or "").lower()
            val = m.get("value")
            if val is not None:
                try:
                    if m_type in ["waterlevel", "waterlevel_msl", "waterlevel_m"]:
                        waterlevel = float(val)
                    elif m_type == "diff_wl_bank":
                        diff_wl_bank = float(val)
                except (ValueError, TypeError):
                    pass

        risk = -1
        if waterlevel is not None and wl_crit is not None and wl_warn is not None:
            try:
                wl = float(waterlevel)
                crit = float(wl_crit)
                warn = float(wl_warn)
                if wl >= crit:
                    risk = 2
                elif wl >= warn:
                    risk = 1
                else:
                    risk = 0
            except:
                pass
        elif diff_wl_bank is not None:
            if diff_wl_bank >= 0:
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

    def find_matching_cctv(self, station):
        """Find the nearest co-located CCTV camera for a given water station."""
        if (
            hasattr(self, "map")
            and self.map
            and hasattr(self.map, "find_matching_cctv")
        ):
            return self.map.find_matching_cctv(station)
        feeds = []
        if hasattr(self, "visual_feed_monitor") and self.visual_feed_monitor:
            feeds = getattr(self.visual_feed_monitor, "latest_feeds", [])
        if not feeds:
            return None
        st_code = str(station.get("code") or "").strip().lower()
        scoord_obj = station.get("coordinates")
        s_coords = (
            scoord_obj.get("coordinates") if isinstance(scoord_obj, dict) else None
        )
        best = None
        min_dist = float("inf")
        for feed in feeds:
            c_code = str(feed.get("code") or "").strip().lower()
            if st_code and c_code and st_code == c_code:
                return feed
            ccoord_obj = feed.get("coordinates")
            c_coords = (
                ccoord_obj.get("coordinates") if isinstance(ccoord_obj, dict) else None
            )
            if s_coords and c_coords and len(s_coords) >= 2 and len(c_coords) >= 2:
                dist = _haversine_distance(s_coords, c_coords)
                if dist <= 300 and dist < min_dist:
                    min_dist = dist
                    best = feed
        return best

    def focus_station(self, code, source=None):
        """Switch to water panel, scroll to the station card, and fly to marker."""
        water_tab = document.getElementById("water_panel_tab")
        if water_tab:
            water_tab.click()

        target_card = None
        if "reservoir_data_list" in document:
            for card in document["reservoir_data_list"].select("[data-station-code]"):
                c_code = card.getAttribute("data-station-code")
                c_source = card.getAttribute("data-station-source")
                if c_code == code and (not source or c_source == source):
                    target_card = card
                    break

        if target_card:
            self.highlight_station_card(target_card)
            try:
                target_card.scrollIntoView({"behavior": "smooth", "block": "center"})
            except Exception:
                pass

        if hasattr(self, "map") and self.map:
            self.map.fly_to_station(code, source=source, zoom=16)
            markers = self.map.metric_markers_by_code.get(code) or []
            if markers:
                markers[0].openPopup()

    def start(self):
        self.running = True
        try:
            window.focus_water_station = lambda code, source=None: self.focus_station(
                code, source
            )
        except Exception:
            pass
        aio.run(self.monitor())

    async def monitor(self):
        if not await self.setup():
            return

        # Bind UI events
        if "marker_style_selector" in document:
            document["marker_style_selector"].bind(
                "change", self.on_marker_style_change
            )

        if "source_selector" in document:
            document["source_selector"].bind("change", self.on_source_change)

        if "hide_no_data" in document:
            document["hide_no_data"].bind("change", self.on_hide_no_data_change)

        while self.running:
            print(
                f"[Monitor:{self.monitor_name}] Cycle running (interval: {self.acquisition_interval}s)"
            )

            await self.get_stations_metrics()

            # wait for next aquisition
            await aio.sleep(self.acquisition_interval)

    async def get_stations_metrics(self):
        query_data = urlencode({"source": self.source})
        url = f"{self.api_url}/v1/stations/metrics/latest?{query_data}"

        self.set_map_loading(True)
        try:
            response = await aio.get(url, cache=True)
            if response.status != 200:
                raise RuntimeError(f"station metrics returned HTTP {response.status}")
            data = json.loads(response.data)
            if not data or not isinstance(data, dict):
                print(f"[Monitor:{self.monitor_name}] Invalid data received: {data}")
                return

            for station in data.get("stations") or []:
                if not station or not isinstance(station, dict):
                    continue
                risk, waterlevel, diff_wl_bank = self.calculate_risk(station)
                station["risk"] = risk
                station["waterlevel"] = waterlevel
                station["diff_wl_bank"] = diff_wl_bank
                level = metric_infos.get_risk_level(risk)
                station["risk_color"] = level["color"]
                station["risk_percent"] = 100

            self.latest_data = data

            if "waterlevel" not in self.map.metric_types:
                self.map.metric_types.append("waterlevel")

            # Markers are coloured by risk, not by a metric scale, so the
            # legend has to describe the risk levels instead
            self.map.set_legend(
                metric_infos.RISK_LEVELS,
                "ระดับน้ำเทียบเกณฑ์เตือนภัย",
                metric_infos.RISK_LEVEL_TITLE,
            )

            await self.map.update("waterlevel", data)
            self.apply_marker_filters()
            self.update_zone_risks()
            self.render_data_list()
        except Exception as e:
            print(f"[Monitor:{self.monitor_name}] Error: {e}")
            self.render_data_error("โหลดข้อมูลสถานีไม่สำเร็จ กรุณาลองใหม่อีกครั้ง")
        finally:
            self.set_map_loading(False)

    def render_data_error(self, message):
        if "reservoir_data_list" not in document:
            return
        document["reservoir_data_list"].html = f"""
        <div class="flex flex-col items-center justify-center h-full text-center gap-2 px-4">
            <i class="ph ph-warning-circle text-4xl text-amber-500"></i>
            <div class="text-sm font-medium text-gray-600">{message}</div>
        </div>
        """

    def on_marker_style_change(self, ev):
        if hasattr(self, "map") and self.latest_data:
            style = ev.target.value
            self.map.marker_style = style
            aio.run(self._update_and_filter())

    def update_zone_shading_buttons(self, mode):
        if "zone_style_outline" in document and "zone_style_shaded" in document:
            btn_outline = document["zone_style_outline"]
            btn_shaded = document["zone_style_shaded"]
            if mode == "outline":
                btn_outline.classList.add(
                    "bg-white", "shadow-sm", "text-blue-700", "font-bold"
                )
                btn_outline.classList.remove("text-slate-600")
                btn_shaded.classList.remove(
                    "bg-white", "shadow-sm", "text-blue-700", "font-bold"
                )
                btn_shaded.classList.add("text-slate-600")
            else:
                btn_shaded.classList.add(
                    "bg-white", "shadow-sm", "text-blue-700", "font-bold"
                )
                btn_shaded.classList.remove("text-slate-600")
                btn_outline.classList.remove(
                    "bg-white", "shadow-sm", "text-blue-700", "font-bold"
                )
                btn_outline.classList.add("text-slate-600")

    def on_zone_shading_mode_click(self, mode):
        self.map.set_zone_shading_mode(mode)
        self.update_zone_shading_buttons(mode)
        try:
            window.localStorage.setItem("sindhu_zone_shading_mode", mode)
        except Exception:
            pass

    def on_toggle_zones_layer(self, ev):
        checked = bool(ev.target.checked)
        self.map.set_zones_visible(checked)
        for i in range(1, 5):
            el_id = f"toggle_zone_{i}"
            if el_id in document:
                document[el_id].checked = checked

    def on_toggle_single_zone(self, zone_num, ev):
        checked = bool(ev.target.checked)
        self.map.set_zone_visible(str(zone_num), checked)
        self.map.set_zone_visible(f"songkhla-zone-{zone_num}", checked)
        self.map.set_zone_visible(f"prototype-zone-{zone_num}", checked)
        all_checked = all(
            document[f"toggle_zone_{i}"].checked
            for i in range(1, 5)
            if f"toggle_zone_{i}" in document
        )
        if "toggle_zones_layer" in document:
            document["toggle_zones_layer"].checked = all_checked

    def on_toggle_boundary_layer(self, ev):
        self.map.set_reference_boundary_visible(bool(ev.target.checked))

    def get_selected_source(self):
        """The source picked in the dropdown, or "all" when nothing narrows it."""
        if "source_selector" in document:
            return document["source_selector"].value
        return "all"

    def is_source_matched(self, selected_source, station_source):
        """Return True if station_source matches selected_source filter.

        Handles legacy source names such as 'dwr_telemetry' matching 'dwr'.
        """
        if not selected_source or selected_source == "all":
            return True
        if not station_source:
            return False
        s_src = str(selected_source).lower()
        st_src = str(station_source).lower()
        if s_src == "dwr":
            return st_src in ("dwr", "dwr_telemetry")
        return st_src == s_src

    def source_marker_keys(self, limit_codes=None):
        """Marker keys of the stations the source filter keeps.

        The map is filtered by `(source, code)` rather than by code alone,
        because rid and dwr publish the same gauge codes — a code
        filter would leave the other source's marker on the map while
        `render_data_list` drops that station from the panel.

        `limit_codes` narrows the result further, e.g. to a zone's members.
        """
        selected_source = self.get_selected_source()
        allowed_codes = None if limit_codes is None else set(limit_codes)

        keys = []
        for station in self.latest_data.get("stations") or []:
            if not station or not self.is_source_matched(
                selected_source, station.get("source")
            ):
                continue
            code = station.get("code")
            if not code:
                continue
            if allowed_codes is not None and code not in allowed_codes:
                continue
            keys.append(self.map.marker_key(station.get("source"), code))
        return keys

    async def _update_and_filter(self):
        if not self.latest_data:
            return
        await self.map.update("waterlevel", self.latest_data)
        self.apply_marker_filters()

    def on_source_change(self, ev):
        if hasattr(self, "map") and self.latest_data:
            selected_source = ev.target.value

            if (
                hasattr(self.map, "_pin_mode_active")
                and self.map._pin_mode_active
                and self.map.user_coord
            ):
                lat, lng = self.map.user_coord
                aio.run(self.on_location_received(lat, lng))
                return

            self.apply_marker_filters()
            self.render_data_list()
            self.update_zone_risks()

    """
    ===========================================================================
    Risk-driven map state
    ===========================================================================
    """

    def hide_stations_without_data(self):
        return "hide_no_data" in document and document["hide_no_data"].checked

    def station_has_data(self, station):
        return bool(station and station.get("metrics"))

    def visible_marker_keys(self, zone_codes=None):
        """Which markers should be on the map right now.

        Source, zone and the no-data toggle all narrow the same set, so they
        are resolved together instead of each overwriting the last.
        """
        selected_source = "all"
        if "source_selector" in document:
            selected_source = document["source_selector"].value

        hide_empty = self.hide_stations_without_data()
        wanted_codes = (
            set(str(c) for c in zone_codes) if zone_codes is not None else None
        )

        keys = []
        for station in (self.latest_data or {}).get("stations") or []:
            if not station:
                continue
            code = station.get("code")
            if not code:
                continue
            if not self.is_source_matched(selected_source, station.get("source")):
                continue
            if wanted_codes is not None and str(code) not in wanted_codes:
                continue
            if hide_empty and not self.station_has_data(station):
                continue
            keys.append(self.map.marker_key(station.get("source"), code))
        return keys

    def apply_marker_filters(self, zone_codes=None):
        self.map.filter_markers_by_keys(self.visible_marker_keys(zone_codes))

    def zone_risk_level(self, zone):
        """Worst risk among the stations that sit in this zone."""
        selected_source = self.get_selected_source()
        stations_by_code = {}
        for station in (self.latest_data or {}).get("stations") or []:
            if station and station.get("code"):
                if not self.is_source_matched(selected_source, station.get("source")):
                    continue
                # Keep the reading that can actually be judged
                code = str(station["code"])
                if code not in stations_by_code or self.station_has_data(station):
                    stations_by_code[code] = station

        max_risk = -1
        for member in zone.get("stations") or []:
            if not member:
                continue
            station = stations_by_code.get(str(member.get("code")))
            if not station:
                continue
            risk, _, _ = self.calculate_risk(station)
            if risk > max_risk:
                max_risk = risk
        return metric_infos.get_risk_level(max_risk)

    def update_zone_risks(self):
        """Colour zones by active station alerts (warning, critical).
        Normal water levels preserve the zone's configured style."""
        for zone in self.zones or []:
            meta = zone.get("metadata") or zone.get("style") or {}
            if (
                meta.get("role") == "reference_boundary"
                or zone.get("code") == "hatyai-boundary"
            ):
                continue
            zone_id = str(zone.get("id", "") or "")
            if zone_id:
                self.map.set_zone_risk(zone_id, self.zone_risk_level(zone))

    def on_hide_no_data_change(self, ev):
        self.apply_marker_filters()

    def on_zone_stations_found(self, nearby_stations):
        if not self.latest_data:
            return

        zone_codes = []
        for s in nearby_stations or []:
            if not s:
                continue
            code = s.get("code", None)
            if code:
                zone_codes.append(code)

        self.apply_marker_filters(zone_codes)
        self.render_data_list(zone_codes)

    def on_zone_stations_empty(self, zone):
        if "reservoir_data_list" not in document:
            return

        zone_name = zone.get("name_th") or zone.get("name") or ""
        name_html = ""
        if zone_name:
            name_html = f'<div class="text-xs text-gray-400">{zone_name}</div>'

        document["reservoir_data_list"].html = f"""
        <div class="flex flex-col items-center justify-center h-full text-center gap-2 px-4">
            <i class="ph ph-map-trifold text-4xl text-gray-300"></i>
            <div class="text-sm font-medium text-gray-600">ไม่มีสถานีในโซนนี้</div>
            {name_html}
            <div class="text-xs text-gray-400 mt-1">กด "กลับสู่มุมมองเริ่มต้น" เพื่อดูสถานีทั้งหมด</div>
        </div>
        """

    def on_zone_stations_cleared(self):
        self.apply_marker_filters()
        if self.latest_data:
            self.render_data_list()

    def update_zone_properties(self, zone_geojson, nearby_stations):
        if not self.latest_data or not nearby_stations:
            return

        selected_source = self.get_selected_source()

        max_risk = -1  # -1 = Unknown, 0 = Normal, 1 = Warning, 2 = Critical

        stations_dict = {}
        for s in self.latest_data.get("stations") or []:
            if s and s.get("code"):
                if not self.is_source_matched(selected_source, s.get("source")):
                    continue
                code = str(s["code"])
                if code not in stations_dict or self.station_has_data(s):
                    stations_dict[code] = s

        for s in nearby_stations:
            if not s:
                continue
            code = s.get("code")
            if not code:
                continue

            db_station = stations_dict.get(str(code))
            if db_station:
                risk, _, _ = self.calculate_risk(db_station)

                if risk > max_risk:
                    max_risk = risk

        level = metric_infos.get_risk_level(max_risk)
        zone_geojson["properties"]["fillColor"] = level["color"]
        zone_geojson["properties"]["color"] = level["border"]
        zone_geojson["properties"]["fillOpacity"] = level["fill_opacity"]

    def render_data_list(self, filter_codes=None):
        if "reservoir_data_list" not in document:
            return

        if not self.latest_data:
            return

        stations = self.latest_data.get("stations") or []
        stations = [s for s in stations if s and isinstance(s, dict)]
        if filter_codes is not None:
            stations = [s for s in stations if s.get("code") in filter_codes]

        selected_source = self.get_selected_source()
        stations = [
            s
            for s in stations
            if self.is_source_matched(selected_source, s.get("source"))
        ]

        html_content = ""

        for station in stations:
            metrics = station.get("metrics") or []
            metrics = [m for m in metrics if m and isinstance(m, dict)]
            if not metrics:
                continue

            risk, waterlevel, diff_wl_bank = self.calculate_risk(station)

            # Only show stations that have valid water level data
            if waterlevel is None and diff_wl_bank is None:
                continue

            level = metric_infos.get_risk_level(risk)
            hex_color = level["color"]
            text_color = level["text"]
            label = level["label"]

            name = station.get("name_th") or station.get("name")
            location = self.format_location(station)

            # format other metrics
            other_html = ""
            for om in metrics:
                m_name = om.get("metric_type")
                if not m_name:
                    continue
                val = om.get("value")
                if val is None:
                    continue

                # Label from the shared metric names so the card and the map
                # tooltip call the same reading by the same name
                m_label = metric_infos.HTML_METRIC_NAMES.get(m_name, m_name)

                if m_name == "waterlevel_msl":
                    display_text = f'{m_label}: <span class="font-medium text-gray-700">{val} ม.รทก.</span>'
                elif m_name == "diff_wl_bank":
                    try:
                        v = float(val)
                        if v < 0:
                            display_text = f'{m_label}: <span class="font-medium text-gray-700">ต่ำกว่าตลิ่ง {abs(v):.2f} ม.</span>'
                        elif v > 0:
                            display_text = f'{m_label}: <span class="font-medium text-red-600">ล้นตลิ่ง {v:.2f} ม.</span>'
                        else:
                            display_text = f'{m_label}: <span class="font-medium text-yellow-600">เสมอระดับตลิ่งพอดี</span>'
                    except:
                        display_text = f'{m_label}: <span class="font-medium text-gray-700">{val} ม.</span>'
                else:
                    unit = metric_infos.HTML_METRIC_UNITS.get(m_name, "")
                    try:
                        value_text = f"{float(val):.2f} {unit}".strip()
                    except (TypeError, ValueError):
                        value_text = f"{val} {unit}".strip()
                    display_text = f'{m_label}: <span class="font-medium text-gray-700">{value_text}</span>'

                other_html += f'<div class="text-xs text-gray-500 bg-gray-50 px-2 py-1 rounded">{display_text}</div>'

            matched_cctv = self.find_matching_cctv(station)
            cctv_btn_html = ""
            if matched_cctv:
                cctv_src = str(matched_cctv.get("source", ""))
                cctv_up_id = str(matched_cctv.get("upstream_id", ""))
                cctv_title = str(
                    matched_cctv.get("title_th")
                    or matched_cctv.get("name_th")
                    or matched_cctv.get("name")
                    or "CCTV"
                )
                cctv_btn_html = f"""
                <div class="mt-2.5 pt-2 border-t border-gray-100 flex items-center justify-between gap-2">
                    <span class="text-[11px] text-blue-600 font-medium flex items-center gap-1 truncate" title="{cctv_title}">
                        <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor" class="shrink-0"><path d="M4 4h10a2 2 0 0 1 2 2v2.5l4-2.5v12l-4-2.5V18a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z"/></svg>
                        <span class="truncate">มีกล้อง: {cctv_title}</span>
                    </span>
                    <button type="button" onclick="event.stopPropagation(); if(window.open_cctv_detail)window.open_cctv_detail('{cctv_src}','{cctv_up_id}')"
                        class="btn btn-xs btn-primary text-white shrink-0 font-medium shadow-sm h-6 min-h-0 px-2.5">
                        ดูกล้อง
                    </button>
                </div>
                """

            html_content += f"""
            <div data-station-code="{station.get("code", "")}" data-station-source="{station.get("source", "")}"
                class="bg-white border border-gray-100 p-4 rounded-xl shadow-sm hover:shadow-md hover:border-blue-300 transition-all duration-200 cursor-pointer">
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
                {cctv_btn_html}
            </div>
            """

        if not html_content:
            html_content = '<div class="flex justify-center items-center h-full text-gray-500">ไม่พบข้อมูลสถานีวัดน้ำ</div>'

        document["reservoir_data_list"].html = html_content
        self.bind_station_cards()

    def format_location(self, station):
        """Province comes from the ETL inside `metadata`, not on the station."""
        metadata = station.get("metadata") or {}
        province = (
            metadata.get("province_name_th")
            or metadata.get("province")
            or station.get("province")
        )
        amphoe = metadata.get("amphoe_name_th")

        if province and amphoe:
            return f"อ.{amphoe} จ.{province}"
        if province:
            return f"จ.{province}"
        return "ไม่ระบุพื้นที่"

    def bind_station_cards(self):
        """Re-attach the flyTo handlers, the list markup is rebuilt every render."""
        if "reservoir_data_list" not in document:
            return

        for card in document["reservoir_data_list"].select("[data-station-code]"):
            code = card.getAttribute("data-station-code")
            if not code:
                continue
            source = card.getAttribute("data-station-source")
            card.bind("click", self._make_station_card_handler(card, code, source))

    def _make_station_card_handler(self, card, code, source):
        def on_click(ev):
            # rid and dwr share station codes, so the source is what
            # tells the two markers apart
            self.map.fly_to_station(code, source)
            self.highlight_station_card(card)

        return on_click

    def highlight_station_card(self, selected_card):
        for card in document["reservoir_data_list"].select("[data-station-code]"):
            card.classList.remove("ring-2", "ring-blue-500")
        selected_card.classList.add("ring-2", "ring-blue-500")
