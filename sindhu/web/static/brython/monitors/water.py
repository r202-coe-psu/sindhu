from browser import document, aio, ajax
import javascript as js
import datetime
from urllib.parse import urlencode

from .base import BaseMonitor
from stations import metric_infos
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
        self.latest_data = None

    def calculate_risk(self, station):
        if not station or not isinstance(station, dict):
            return -1, None, None

        metadata = station.get("metadata") or {}
        if not isinstance(metadata, dict):
            metadata = {}

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

        if "hide_no_data" in document:
            document["hide_no_data"].bind("change", self.on_hide_no_data_change)

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
            if not data or not isinstance(data, dict):
                print(f"monitor: error data is invalid: {data}")
                return

            for station in data.get("stations") or []:
                if not station or not isinstance(station, dict):
                    continue
                risk, _, _ = self.calculate_risk(station)
                level = metric_infos.get_risk_level(risk)
                station["risk"] = risk
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
            print(f"monitor: error {e}")
        finally:
            self.set_map_loading(False)

    def on_marker_style_change(self, ev):
        if hasattr(self, "map") and self.latest_data:
            style = ev.target.value
            self.map.marker_style = style
            aio.run(self._update_and_filter())

    def get_selected_source(self):
        """The source picked in the dropdown, or "all" when nothing narrows it."""
        if "source_selector" in document:
            return document["source_selector"].value
        return "all"

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
            if not station or station.get("source") != selected_source:
                continue
            code = station.get("code")
            if not code:
                continue
            if allowed_codes is not None and code not in allowed_codes:
                continue
            keys.append(self.map.marker_key(selected_source, code))
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
            if selected_source != "all" and station.get("source") != selected_source:
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
        stations_by_code = {}
        for station in (self.latest_data or {}).get("stations") or []:
            if station and station.get("code"):
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
        """Colour every zone by its worst station, so the whole province can
        be read at a glance without picking a zone first."""
        for zone in self.zones or []:
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

        max_risk = (
            -1
        )  # -1 = Unknown, 0 = Normal, 1 = Warning, 2 = Critical, 3 = Evacuation

        stations_dict = {
            s.get("code"): s
            for s in (self.latest_data.get("stations") or [])
            if s and s.get("code")
        }

        for s in nearby_stations:
            if not s:
                continue
            code = s.get("code")
            if not code:
                continue

            db_station = stations_dict.get(code)
            if db_station:
                if (
                    selected_source != "all"
                    and db_station.get("source") != selected_source
                ):
                    continue

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
        if selected_source != "all":
            stations = [s for s in stations if s.get("source") == selected_source]

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
