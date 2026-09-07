"""CCTV-only UI controller for the Hatyai monitor page.

The controller consumes the public visual-feed DTO. It deliberately has no
map dependency: CCTV cards and the detail/history dialog are useful while the
water map is still loading, and CCTV coordinates are not rendered here.
"""

from browser import aio, document, window
import datetime
import json
import math
import time
from urllib.parse import quote, urljoin, urlparse


def _haversine_distance(coord1, coord2):
    """Calculate distance in meters between two [lon, lat] coordinates."""
    try:
        lon1, lat1 = float(coord1[0]), float(coord1[1])
        lon2, lat2 = float(coord2[0]), float(coord2[1])
        r = 6371000.0
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlam = math.radians(lon2 - lon1)
        a = (
            math.sin(dphi / 2) ** 2
            + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
        )
        return 2 * r * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    except Exception:
        return float("inf")


POLL_INTERVAL_SECONDS = 120
IMAGE_STALE_AFTER_MINUTES = 30
BANGKOK_TZ = datetime.timezone(datetime.timedelta(hours=7))
HISTORY_DAYS = 7
MAX_CCTV_FEEDS = 30

HATYAI_SOURCE = "hatyai_city_climate"

AVAILABILITY_LABELS = {
    "online": "ออนไลน์",
    "stale": "ข้อมูลเก่า",
    "degraded": "ขัดข้องบางส่วน",
    "offline": "ออฟไลน์",
    "unknown": "ไม่ทราบสถานะ",
}

AVAILABILITY_COLORS = {
    "online": "#16a34a",
    "stale": "#d97706",
    "degraded": "#ea580c",
    "offline": "#dc2626",
    "unknown": "#64748b",
}

SOURCE_LABELS = {
    HATYAI_SOURCE: "Hatyai City Climate",
    "dwr": "กรมทรัพยากรน้ำ (DWR)",
}


def _as_dict(value):
    return value if isinstance(value, dict) else {}


def _text(value, fallback="—"):
    if value is None:
        return fallback
    value = str(value).strip()
    return value if value else fallback


def _safe_http_url(value):
    """Return an absolute HTTP(S) URL without credentials or fragments."""
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not value:
        return None
    parsed = _url_parts(value)
    if parsed is None:
        return None
    scheme, netloc, _path, _params, _query, fragment = parsed
    if scheme.lower() not in ("http", "https"):
        return None
    if not netloc or "@" in netloc or fragment:
        return None
    return value


def _url_parts(value):
    """Read urlparse's six sequence fields (also works in Brython)."""
    try:
        parsed = urlparse(value)
        return tuple(str(parsed[index]) for index in range(6))
    except Exception:
        return None


def _resolve_image_url(value, api_url):
    """Resolve only public image URLs accepted by the visual-feed contract.

    DWR returns a root-relative public snapshot path. It is joined to the
    configured API origin; protocol-relative, javascript, and arbitrary
    relative provider URLs are rejected.
    """
    absolute = _safe_http_url(value)
    if absolute:
        return absolute
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not value.startswith("/") or value.startswith("//"):
        return None
    if not value.startswith("/v1/visual-feeds/dwr/"):
        return None
    base = _safe_http_url(api_url)
    if not base:
        return None
    resolved = urljoin(base.rstrip("/") + "/", value)
    parsed = _url_parts(resolved)
    if parsed is None:
        return None
    scheme, netloc, path, _params, _query, fragment = parsed
    if (
        scheme.lower() not in ("http", "https")
        or not netloc
        or "@" in netloc
        or fragment
        or not path.startswith("/v1/visual-feeds/dwr/")
    ):
        return None
    return resolved


def _version_image_url(image_url, captured_at):
    """Version a mutable image with trusted capture time, once only."""
    image_url = _safe_http_url(image_url)
    captured = _parse_utc(captured_at)
    if not image_url or captured is None:
        return image_url
    parsed = _url_parts(image_url)
    if parsed is None:
        return image_url
    query = parsed[4]
    query_parts = query.split("&")
    if any(part.split("=", 1)[0].lower() == "v" for part in query_parts if part):
        return image_url
    separator = "&" if query else "?"
    return f"{image_url}{separator}v={int(captured.timestamp())}"


def _parse_utc(value):
    if not value:
        return None
    try:
        normalized = str(value).replace("Z", "+00:00")
        parsed = datetime.datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=datetime.timezone.utc)
        return parsed.astimezone(datetime.timezone.utc)
    except (TypeError, ValueError):
        return None


def _now_utc(value=None):
    value = value or datetime.datetime.now(datetime.timezone.utc)
    if value.tzinfo is None:
        value = value.replace(tzinfo=datetime.timezone.utc)
    return value.astimezone(datetime.timezone.utc)


def _bangkok_today(now=None):
    """Return today's Bangkok calendar date, independent of browser timezone."""
    return _now_utc(now).astimezone(BANGKOK_TZ).date()


def _history_date_window(now=None):
    today = _bangkok_today(now)
    return today - datetime.timedelta(days=HISTORY_DAYS - 1), today


def _valid_history_date(value, now=None):
    try:
        if isinstance(value, datetime.datetime):
            selected = value.date()
        elif isinstance(value, datetime.date):
            selected = value
        else:
            selected = datetime.date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    earliest, latest = _history_date_window(now)
    return selected if earliest <= selected <= latest else None


def _is_latest_stale(feed, now=None):
    """Age-based stale labeling applies to latest images only."""
    captured = _parse_utc(_as_dict(feed).get("captured_at"))
    if captured is None:
        return False
    age = _now_utc(now) - captured
    return (
        datetime.timedelta(0)
        <= age
        > datetime.timedelta(minutes=IMAGE_STALE_AFTER_MINUTES)
    )


def _filter_cctv_feeds(feeds, limit=MAX_CCTV_FEEDS):
    """Keep the public UI bounded to the registered CCTV set."""
    if not isinstance(feeds, list) or limit <= 0:
        return []
    result = []
    for feed in feeds:
        if not isinstance(feed, dict):
            continue
        if str(feed.get("media_type", "")).lower() != "cctv":
            continue
        result.append(feed)
        if len(result) >= limit:
            break
    return result


def _availability(feed):
    value = str(_as_dict(feed).get("availability", "unknown")).lower().strip()
    return value if value in AVAILABILITY_LABELS else "unknown"


def _el(tag, class_name=None, text_value=None):
    element = document.createElement(tag)
    if class_name:
        element.className = class_name
    if text_value is not None:
        # Provider values always enter the DOM through textContent/attributes.
        element.textContent = _text(text_value, "")
    return element


def _append(parent, child):
    parent <= child
    return child


def _has_coordinates(feed):
    coords_obj = _as_dict(feed).get("coordinates")
    if not coords_obj or not isinstance(coords_obj, dict):
        return False
    coords = coords_obj.get("coordinates")
    return (
        isinstance(coords, list)
        and len(coords) >= 2
        and coords[0] is not None
        and coords[1] is not None
    )


class VisualFeedMonitor:
    def __init__(self, api_url, poll_interval=POLL_INTERVAL_SECONDS):
        self.api_url = (api_url or "").rstrip("/")
        self.endpoint = f"{self.api_url}/v1/visual-feeds"
        self.poll_interval = poll_interval
        self.running = False
        self.latest_data = None
        self.latest_feeds = []

        self.map_owner = None
        self._markers_initialized = False

        self.view_mode = "list"
        self._bound = False
        self._monitor_started = False
        self._poll_started = False
        self._request_in_flight = False
        self._latest_generation = 0
        self._history_generation = 0
        self._last_latest_fetch = None
        # The monitor is a CCTV-first page.  Keep the state in sync with the
        # server-rendered default panel so initial polling and marker updates
        # behave exactly like a user selecting the CCTV tab.
        self._visual_panel_active = True
        self._mode = "latest"
        self._modal_open = False
        self._active_feed = None
        self._active_date = None
        self._history_frames = []
        self._focus_return = None

    def start(self, map_owner=None):
        """Bind controls and fetch initial CCTV feeds so markers appear on map."""
        self.map_owner = map_owner
        self.running = True
        try:
            window.open_cctv_detail = (
                lambda source, upstream_id: self._open_detail_by_id(source, upstream_id)
            )
            window.focus_water_station_from_modal = (
                lambda code, source=None: self._focus_water_station_from_modal(
                    code, source
                )
            )
        except Exception:
            pass
        self._bind_controls()
        self._show_visual_panel(None)
        if not self._monitor_started:
            self._monitor_started = True
            aio.run(self.monitor())
        aio.run(self._initial_load())

    def _focus_water_station_from_modal(self, code, source=None):
        self._close_detail()
        if hasattr(window, "focus_water_station"):
            window.focus_water_station(code, source)

    def find_matching_station(self, feed):
        """Find the nearest co-located water station for a given CCTV camera."""
        stations = []
        if self.map_owner:
            if hasattr(self.map_owner, "data") and isinstance(
                self.map_owner.data, dict
            ):
                stations = self.map_owner.data.get("stations", [])
            elif hasattr(self.map_owner, "map") and hasattr(
                self.map_owner.map, "latest_stations"
            ):
                stations = self.map_owner.map.latest_stations
        if not stations:
            m = self._get_map()
            if m and hasattr(m, "latest_stations"):
                stations = m.latest_stations
        if not stations:
            return None

        c_code = str(feed.get("code") or "").strip().lower()
        ccoord_obj = feed.get("coordinates")
        c_coords = (
            ccoord_obj.get("coordinates") if isinstance(ccoord_obj, dict) else None
        )

        best = None
        min_dist = float("inf")
        for st in stations:
            s_code = str(st.get("code") or "").strip().lower()
            if c_code and s_code and c_code == s_code:
                return st
            scoord_obj = st.get("coordinates")
            s_coords = (
                scoord_obj.get("coordinates") if isinstance(scoord_obj, dict) else None
            )
            if s_coords and c_coords and len(s_coords) >= 2 and len(c_coords) >= 2:
                dist = _haversine_distance(s_coords, c_coords)
                if dist <= 300 and dist < min_dist:
                    min_dist = dist
                    best = st
        return best

    async def _initial_load(self):
        """Load CCTV feeds immediately so markers are placed on the map on startup."""
        await self.refresh(force=True)
        for _ in range(50):
            m = self._get_map()
            if m and hasattr(m, "show_visual_feeds"):
                self.update_map_markers()
                break
            await aio.sleep(0.2)

    def _open_detail_by_id(self, source, upstream_id):
        for feed in self.latest_feeds:
            if str(feed.get("source")) == str(source) and str(
                feed.get("upstream_id")
            ) == str(upstream_id):
                self._open_detail(feed)
                break

    def _get_map(self):
        if self.map_owner is None:
            return None
        if hasattr(self.map_owner, "show_visual_feeds"):
            return self.map_owner
        if hasattr(self.map_owner, "map") and self.map_owner.map:
            target = self.map_owner.map
            if hasattr(target, "show_visual_feeds"):
                return target
            return target
        return None

    def update_map_markers(self, feeds=None):
        m = self._get_map()
        if not m or not hasattr(m, "show_visual_feeds"):
            return
        target_feeds = self.latest_feeds if feeds is None else feeds
        marker_feeds = []
        for feed in target_feeds:
            if not _has_coordinates(feed):
                continue
            f_copy = dict(feed)
            img = _resolve_image_url(f_copy.get("image_url"), self.api_url)
            f_copy["image_url"] = _version_image_url(img, f_copy.get("captured_at"))
            marker_feeds.append(f_copy)
        m.show_visual_feeds(marker_feeds, on_feed_click=self._on_marker_click)
        chk = document.getElementById("toggle_cctv_markers")
        if chk and hasattr(m, "set_visual_feed_layer_visible"):
            m.set_visual_feed_layer_visible(chk.checked)
        self._markers_initialized = True

    def _on_marker_click(self, feed):
        source = str(feed.get("source", ""))
        upstream_id = str(feed.get("upstream_id", ""))
        card_id = f"cctv_card_{source}_{upstream_id}"
        if card_id in document:
            card_el = document[card_id]
            try:
                card_el.scrollIntoView({"behavior": "smooth", "block": "center"})
                card_el.classList.add("ring-2", "ring-blue-500")
                if hasattr(window, "setTimeout"):
                    window.setTimeout(
                        lambda: card_el.classList.remove("ring-2", "ring-blue-500"),
                        2000,
                    )
            except Exception:
                pass

    def _fly_to_camera(self, feed):
        m = self._get_map()
        if not m:
            return
        source = str(feed.get("source", ""))
        upstream_id = str(feed.get("upstream_id", ""))
        if hasattr(m, "fly_to_visual_feed"):
            m.fly_to_visual_feed(source, upstream_id)
        elif hasattr(m, "map") and hasattr(m.map, "flyTo"):
            coords_obj = _as_dict(feed).get("coordinates", {})
            coords = coords_obj.get("coordinates", [])
            if len(coords) >= 2:
                m.map.flyTo([coords[1], coords[0]], 17)

    def stop(self):
        self.running = False
        self._invalidate_latest()
        self._history_generation += 1

    async def monitor(self):
        """One lifetime-owned poll loop; hidden modes simply do no I/O."""
        while self.running:
            await aio.sleep(0.25)
            if not self._poll_started or not self._should_poll_latest():
                continue
            if self._last_latest_fetch is None or (
                time.monotonic() - self._last_latest_fetch >= self.poll_interval
            ):
                await self.refresh()

    def _bind_controls(self):
        if self._bound:
            return
        self._bound = True

        for element_id in (
            "visual_feed_group_filter",
            "visual_feed_availability_filter",
        ):
            if element_id in document:
                document[element_id].bind("change", self._on_filter)
        if "visual_feed_search" in document:
            document["visual_feed_search"].bind("input", self._on_filter)
        if "visual_feed_search_clear" in document:
            document["visual_feed_search_clear"].bind("click", self._on_clear_search)
        if "visual_feed_view_list" in document:
            document["visual_feed_view_list"].bind("click", self._on_set_view_list)
        if "visual_feed_view_grid" in document:
            document["visual_feed_view_grid"].bind("click", self._on_set_view_grid)
        if "toggle_cctv_markers" in document:
            document["toggle_cctv_markers"].bind("change", self._on_toggle_cctv_markers)
        if "visual_feed_retry" in document:
            document["visual_feed_retry"].bind("click", self._on_retry)
        if "visual_feed_panel_tab" in document:
            document["visual_feed_panel_tab"].bind("click", self._show_visual_panel)
        if "water_panel_tab" in document:
            document["water_panel_tab"].bind("click", self._show_water_panel)
        if "visual_feed_detail_dialog" in document:
            dialog = document["visual_feed_detail_dialog"]
            dialog.bind("keydown", self._on_modal_keydown)
            dialog.bind("cancel", self._on_modal_cancel)
            dialog.bind("click", self._on_modal_click)
        if "visual_feed_detail_close" in document:
            document["visual_feed_detail_close"].bind("click", self._on_close_detail)
        if "visual_feed_history_button" in document:
            document["visual_feed_history_button"].bind(
                "click", self._on_detail_history
            )
        if "visual_feed_history_date" in document:
            document["visual_feed_history_date"].bind(
                "change", self._on_history_date_change
            )
        if "visual_feed_history_back_latest" in document:
            document["visual_feed_history_back_latest"].bind(
                "click", self._on_back_to_latest
            )
        document.bind("visibilitychange", self._on_visibility_change)
        window.bind("keydown", self._on_global_keydown)

    def _on_set_view_list(self, _event=None):
        if self.view_mode == "list":
            return
        self.view_mode = "list"
        self._update_view_toggle_ui()
        self.render_cards()

    def _on_set_view_grid(self, _event=None):
        if self.view_mode == "grid":
            return
        self.view_mode = "grid"
        self._update_view_toggle_ui()
        self.render_cards()

    def _update_view_toggle_ui(self):
        btn_list = document.getElementById("visual_feed_view_list")
        btn_grid = document.getElementById("visual_feed_view_grid")
        container = document.getElementById("visual_feed_cards")
        if btn_list:
            if self.view_mode == "list":
                btn_list.classList.add("active-view-btn")
            else:
                btn_list.classList.remove("active-view-btn")
        if btn_grid:
            if self.view_mode == "grid":
                btn_grid.classList.add("active-view-btn")
            else:
                btn_grid.classList.remove("active-view-btn")
        if container:
            if self.view_mode == "grid":
                container.classList.remove("grid-cols-1", "p-3.5", "gap-3.5")
                container.classList.add("grid-cols-2", "p-2.5", "gap-2.5")
            else:
                container.classList.remove("grid-cols-2", "p-2.5", "gap-2.5")
                container.classList.add("grid-cols-1", "p-3.5", "gap-3.5")

    def _on_toggle_cctv_markers(self, event):
        visible = getattr(event.target, "checked", True)
        m = self._get_map()
        if m and hasattr(m, "set_visual_feed_layer_visible"):
            m.set_visual_feed_layer_visible(visible)

    def _on_filter(self, _event):
        self.render_cards()

    def _on_clear_search(self, _event=None):
        if "visual_feed_search" in document:
            document["visual_feed_search"].value = ""
        if "visual_feed_search_clear" in document:
            document["visual_feed_search_clear"].classList.add("hidden")
        self.render_cards()

    def _on_retry(self, _event):
        if self._should_poll_latest():
            aio.run(self.refresh())

    def _on_visibility_change(self, _event):
        if not self._browser_visible():
            self._invalidate_latest()
            self._history_generation += 1
            return
        if self._should_poll_latest():
            self._poll_started = True
            aio.run(self.refresh())

    def _show_visual_panel(self, _event):
        visual_panel = document.getElementById("visual_feed_panel")
        water_panel = document.getElementById("reservoir_data_list")
        water_controls = document.getElementById("water_panel_controls")
        if visual_panel:
            visual_panel.classList.remove("hidden")
            visual_panel.classList.add("flex")
        if water_panel:
            water_panel.classList.add("hidden")
        if water_controls:
            water_controls.classList.add("hidden")
        self._set_tab_state("visual_feed_panel_tab", "water_panel_tab")

        header_title = document.getElementById("panel_header_title")
        if header_title:
            header_title.html = """<i class="ph ph-video-camera text-xl text-blue-200"></i><span>กล้อง CCTV เฝ้าระวังน้ำท่วม</span>"""
        header_subtitle = document.getElementById("panel_header_subtitle")
        if header_subtitle:
            header_subtitle.textContent = "ภาพถ่ายสดและประวัติ 7 วันจากจุดเฝ้าระวัง"

        self._visual_panel_active = True
        self._mode = "latest"
        self._history_generation += 1
        self._latest_generation += 1
        self._poll_started = True
        m = self._get_map()
        if m and hasattr(m, "set_visual_feed_layer_visible"):
            chk = document.getElementById("toggle_cctv_markers")
            visible = chk.checked if chk else True
            m.set_visual_feed_layer_visible(visible)
        self.update_map_markers()
        # This is the only path that performs the first latest fetch.
        aio.run(self.refresh())

    def _show_water_panel(self, _event):
        visual_panel = document.getElementById("visual_feed_panel")
        water_panel = document.getElementById("reservoir_data_list")
        water_controls = document.getElementById("water_panel_controls")
        if visual_panel:
            visual_panel.classList.add("hidden")
            visual_panel.classList.remove("flex")
        if water_panel:
            water_panel.classList.remove("hidden")
        if water_controls:
            water_controls.classList.remove("hidden")
        self._set_tab_state("water_panel_tab", "visual_feed_panel_tab")

        header_title = document.getElementById("panel_header_title")
        if header_title:
            header_title.html = """<svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 text-blue-200" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 002-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" /></svg><span>สถานการณ์ระดับน้ำและเตือนภัย</span>"""
        header_subtitle = document.getElementById("panel_header_subtitle")
        if header_subtitle:
            header_subtitle.textContent = "ข้อมูลสถานีวัดน้ำและจุดเฝ้าระวัง"

        self._visual_panel_active = False
        self._mode = "latest"
        self._invalidate_latest()
        self._history_generation += 1
        self._close_detail(restore_focus=False)
        m = self._get_map()
        if m and hasattr(m, "set_visual_feed_layer_visible"):
            chk = document.getElementById("toggle_cctv_markers")
            visible = chk.checked if chk else True
            m.set_visual_feed_layer_visible(visible)

    def _set_tab_state(self, selected_id, other_id):
        selected = document.getElementById(selected_id)
        other = document.getElementById(other_id)
        if selected:
            selected.attrs["aria-selected"] = "true"
        if other:
            other.attrs["aria-selected"] = "false"

    def _browser_visible(self):
        try:
            hidden = getattr(document, "hidden", None)
            if hidden is None:
                hidden = getattr(getattr(window, "document", None), "hidden", False)
            return not bool(hidden)
        except Exception:
            return True

    def _should_poll_latest(self):
        return bool(
            self.running
            and self._visual_panel_active
            and self._mode == "latest"
            and self._browser_visible()
        )

    def _should_fetch_history(self):
        return bool(
            self.running
            and self._visual_panel_active
            and self._mode == "history"
            and self._modal_open
            and self._browser_visible()
        )

    def _invalidate_latest(self):
        self._latest_generation += 1
        self._last_latest_fetch = None

    async def refresh(self, force=False):
        if (not force and not self._should_poll_latest()) or self._request_in_flight:
            return False
        generation = self._latest_generation
        self._request_in_flight = True
        # Failed attempts must not spin the poll loop while the source is down.
        self._last_latest_fetch = time.monotonic()
        try:
            # The backend cache is authoritative; do not add a cache-buster.
            response = await aio.get(f"{self.endpoint}?media_type=cctv", cache=True)
            if (
                getattr(response, "status", 200) < 200
                or getattr(response, "status", 200) >= 300
            ):
                raise ValueError("latest request failed")
            parsed = json.loads(response.data)
            if not isinstance(parsed, dict) or not isinstance(
                parsed.get("visual_feeds"), list
            ):
                raise ValueError("latest response invalid")
            if not force and (
                generation != self._latest_generation or not self._should_poll_latest()
            ):
                return False

            feeds = _filter_cctv_feeds(parsed["visual_feeds"])
            self.latest_data = dict(parsed)
            self.latest_data["visual_feeds"] = feeds
            self.latest_data["count"] = len(feeds)
            self.latest_feeds = feeds
            self._last_latest_fetch = time.monotonic()
            badge = document.getElementById("cctv_tab_badge")
            if badge:
                badge.textContent = str(len(feeds))
                badge.classList.remove("hidden")
            self._refresh_group_options()
            self.render_cards()
            self._set_source_health(parsed.get("source_health"))
            self._refresh_open_latest_detail()
            self.update_map_markers()
            if self.map_owner and hasattr(self.map_owner, "render_stations"):
                try:
                    self.map_owner.render_stations()
                except Exception:
                    pass
            return True
        except Exception:
            if (force or generation == self._latest_generation) and (
                force or self._should_poll_latest()
            ):
                if self.latest_data is None:
                    self._set_summary("โหลดข้อมูลกล้องไม่สำเร็จ ลองรีเฟรชอีกครั้ง")
                    self._set_cards_message("ยังไม่มีข้อมูลกล้อง")
                else:
                    self._set_summary("แสดงข้อมูลรอบล่าสุด · รอบใหม่โหลดไม่สำเร็จ")
                    self._set_source_health({"status": "degraded"})
            return False
        finally:
            self._request_in_flight = False

    def _refresh_group_options(self):
        selector = document.getElementById("visual_feed_group_filter")
        if not selector:
            return
        groups = sorted(
            set(
                str(feed.get("coverage_group", "")).strip()
                for feed in self.latest_feeds
                if str(feed.get("coverage_group", "")).strip()
            )
        )
        selected = selector.value
        selector.html = ""
        option = _el("option", text_value="พื้นที่: ทั้งหมด")
        option.attrs["value"] = "all"
        selector <= option
        for group in groups:
            option = _el("option", text_value=group)
            option.attrs["value"] = group
            selector <= option
        selector.value = selected if selected == "all" or selected in groups else "all"

    def render_cards(self):
        if self.latest_data is None:
            return
        group = self._selected_value("visual_feed_group_filter")
        availability = self._selected_value("visual_feed_availability_filter")

        query = ""
        search_box = document.getElementById("visual_feed_search")
        if search_box:
            query = str(search_box.value or "").strip().lower()
            clear_btn = document.getElementById("visual_feed_search_clear")
            if clear_btn:
                if query:
                    clear_btn.classList.remove("hidden")
                else:
                    clear_btn.classList.add("hidden")

        visible = []
        for feed in self.latest_feeds:
            feed_group = str(feed.get("coverage_group", ""))
            feed_availability = _availability(feed)
            if group != "all" and feed_group != group:
                continue
            if availability != "all" and feed_availability != availability:
                continue
            if query:
                searchable = (
                    str(feed.get("title_th") or "")
                    + " " + str(feed.get("name_th") or "")
                    + " " + str(feed.get("name") or "")
                    + " " + str(feed.get("code") or "")
                    + " " + str(feed.get("coverage_group") or "")
                ).lower()
                if query not in searchable:
                    continue
            visible.append(feed)

        container = document.getElementById("visual_feed_cards")
        if not container:
            return
        container.html = ""
        if not visible:
            self._set_cards_message("ไม่พบกล้องตามตัวกรองนี้")
        else:
            for feed in visible:
                container <= self._build_card(feed)

        total = len(self.latest_feeds)
        self._set_summary(
            f"กล้อง CCTV {total} รายการ · กำลังแสดง {len(visible)} รายการ"
        )
        self.update_map_markers(visible)

    def _build_card(self, feed):
        availability = _availability(feed)
        source = str(feed.get("source", ""))
        upstream_id = str(feed.get("upstream_id", ""))
        is_stale = _is_latest_stale(feed)
        title = _text(feed.get("title_th") or feed.get("name_th") or feed.get("name"))
        captured = _parse_utc(feed.get("captured_at"))
        time_str = _format_time(captured)
        coverage = _text(feed.get("coverage_group"))
        source_lbl = _source_label(feed.get("source"))

        image_url = _resolve_image_url(feed.get("image_url"), self.api_url)
        image_url = _version_image_url(image_url, feed.get("captured_at"))

        if self.view_mode == "grid":
            # Grid View (2 columns, compact)
            card = _el(
                "article",
                "visual-feed-card group relative overflow-hidden rounded-xl border border-slate-200/90 bg-white shadow-xs hover:shadow-md transition-all duration-200 flex flex-col justify-between",
            )
            card.attrs["data-availability"] = availability
            card.attrs["id"] = f"cctv_card_{source}_{upstream_id}"
            if is_stale:
                card.attrs["data-latest-stale"] = "true"

            # Image section
            img_container = _el("div", "relative aspect-video bg-slate-900 overflow-hidden cursor-pointer")
            if image_url:
                img_view = self._image_view(image_url, title, latest=True)
                img_view.classList.add("group-hover:scale-105", "transition-transform", "duration-300")
                img_container <= img_view
            else:
                img_container <= _el(
                    "div",
                    "flex h-full w-full items-center justify-center bg-slate-800 text-[10px] text-slate-400",
                    "ไม่มีภาพ",
                )
            img_container.bind("click", lambda event, selected=feed: self._open_detail(selected, event))

            # Status pill top-left
            status_pill = _el(
                "span",
                "absolute top-1.5 left-1.5 z-10 flex items-center gap-1 px-1.5 py-0.5 rounded-md text-[9px] font-bold text-white shadow-xs",
            )
            status_pill.style.backgroundColor = AVAILABILITY_COLORS[availability]
            if availability == "online":
                status_pill.html = """<span class="w-1.5 h-1.5 rounded-full bg-white animate-pulse"></span><span>สด</span>"""
            else:
                status_pill.textContent = AVAILABILITY_LABELS[availability]
            img_container <= status_pill

            # Timestamp pill bottom-right
            time_short = time_str.split(" ")[1] if " " in time_str else time_str
            time_pill = _el(
                "span",
                "absolute bottom-1 right-1 z-10 px-1.5 py-0.2 rounded text-[9px] font-medium bg-black/70 text-white/90 backdrop-blur-xs",
                time_short,
            )
            img_container <= time_pill
            _append(card, img_container)

            # Body
            body = _append(card, _el("div", "p-2.5 flex flex-col justify-between flex-1 space-y-1.5"))

            # Title
            title_btn = _el(
                "button",
                "text-left text-xs font-bold leading-snug text-slate-800 hover:text-blue-600 transition-colors line-clamp-2",
            )
            title_btn.attrs["type"] = "button"
            title_btn.attrs["aria-label"] = f"เปิดรายละเอียด {title}"
            title_btn.textContent = title
            title_btn.bind("click", lambda event, selected=feed: self._open_detail(selected, event))
            _append(body, title_btn)

            # Group / Location
            meta_div = _append(body, _el("div", "text-[10px] text-slate-500 truncate"))
            meta_div.textContent = f"{coverage} · {source_lbl}"

            # Actions
            actions = _append(body, _el("div", "flex flex-wrap items-center gap-1 pt-1.5 border-t border-slate-100"))

            detail_btn = _append(actions, _el("button", "btn btn-xs btn-primary flex-1 text-[10px] font-semibold h-6 min-h-0 px-2 rounded-md", "ดูรายละเอียด"))
            detail_btn.attrs["type"] = "button"
            detail_btn.bind("click", lambda event, selected=feed: self._open_detail(selected, event))

            if _supports_history(feed):
                hist_btn = _append(actions, _el("button", "btn btn-xs btn-outline flex-1 text-[10px] font-semibold h-6 min-h-0 px-1.5 rounded-md text-blue-600 border-slate-200 hover:bg-blue-50", "ดูประวัติ 7 วัน"))
                hist_btn.attrs["type"] = "button"
                hist_btn.bind("click", lambda event, selected=feed: self._open_history(selected, event))

            if _has_coordinates(feed):
                map_btn = _append(actions, _el("button", "btn btn-xs btn-ghost text-[10px] text-blue-600 h-6 min-h-0 px-1.5 rounded-md hover:bg-blue-50", "ดูบนแผนที่"))
                map_btn.attrs["type"] = "button"
                map_btn.bind("click", lambda event, selected=feed: self._fly_to_camera(selected))

            matched_st = self.find_matching_station(feed)
            if matched_st:
                st_code = str(matched_st.get("code", ""))
                st_src = str(matched_st.get("source", ""))
                water_btn = _append(actions, _el("button", "btn btn-xs btn-info btn-outline text-[10px] h-6 min-h-0 px-1.5 rounded-md font-medium", "🌊 ดูระดับน้ำ"))
                water_btn.attrs["type"] = "button"
                water_btn.bind("click", lambda event, code=st_code, src=st_src: self._on_view_station(code, src, event))

            detail_url = _safe_http_url(feed.get("detail_url"))
            if detail_url:
                link = _append(actions, _el("a", "btn btn-xs btn-ghost text-[10px] h-6 min-h-0 px-1 rounded-md text-slate-500", "ต้นทาง"))
                link.attrs["href"] = detail_url
                link.attrs["target"] = "_blank"
                link.attrs["rel"] = "noopener noreferrer"

            return card

        # List View (1 column, full-width 16:9 images)
        card = _el(
            "article",
            "visual-feed-card group relative overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-xs hover:shadow-md transition-all duration-200 flex flex-col",
        )
        card.attrs["data-availability"] = availability
        card.attrs["id"] = f"cctv_card_{source}_{upstream_id}"
        if is_stale:
            card.attrs["data-latest-stale"] = "true"

        # Image Container
        img_container = _el("div", "relative aspect-video bg-slate-900 overflow-hidden cursor-pointer")
        if image_url:
            img_view = self._image_view(image_url, title, latest=True)
            img_view.classList.add("group-hover:scale-105", "transition-transform", "duration-300")
            img_container <= img_view
        else:
            img_container <= _el(
                "div",
                "flex h-full w-full items-center justify-center bg-slate-800 text-xs text-slate-400",
                "ไม่มีภาพตัวอย่าง",
            )
        img_container.bind("click", lambda event, selected=feed: self._open_detail(selected, event))

        # Status badge top-left
        status_badge = _el(
            "span",
            "absolute top-2.5 left-2.5 z-10 flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-bold text-white shadow-sm backdrop-blur-md",
        )
        status_badge.style.backgroundColor = AVAILABILITY_COLORS[availability]
        if availability == "online":
            status_badge.html = """<span class="w-2 h-2 rounded-full bg-white animate-pulse"></span><span>ออนไลน์ LIVE</span>"""
        else:
            status_badge.textContent = AVAILABILITY_LABELS[availability]
        img_container <= status_badge

        # Stale alert top-right if stale
        if is_stale:
            stale_badge = _el(
                "span",
                "absolute top-2.5 right-2.5 z-10 flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-semibold bg-amber-500/90 text-white backdrop-blur-xs shadow-xs",
                "ภาพเก่า (>30น.)",
            )
            stale_badge.attrs["aria-label"] = "ภาพล่าสุดเก่ากว่า 30 นาที"
            img_container <= stale_badge

        # Timestamp badge bottom-right
        time_badge = _el(
            "span",
            "absolute bottom-2.5 right-2.5 z-10 flex items-center gap-1 px-2 py-0.5 rounded-md text-[11px] font-medium bg-black/65 text-white backdrop-blur-xs shadow-xs",
        )
        time_badge.html = f"""<i class="ph ph-clock text-xs"></i><span>{time_str}</span>"""
        img_container <= time_badge

        _append(card, img_container)

        # Body
        body = _append(card, _el("div", "p-3.5 space-y-2.5"))

        # Title button
        title_btn = _el(
            "button",
            "min-w-0 text-left text-sm font-bold leading-snug text-slate-900 hover:text-blue-600 transition-colors",
        )
        title_btn.attrs["type"] = "button"
        title_btn.attrs["aria-label"] = f"เปิดรายละเอียด {title}"
        title_btn.textContent = title
        title_btn.bind("click", lambda event, selected=feed: self._open_detail(selected, event))
        _append(body, title_btn)

        # Tags row (Source & Area)
        tags_row = _append(body, _el("div", "flex flex-wrap items-center gap-1.5"))
        source_tag = _append(
            tags_row,
            _el("span", "inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-slate-100 text-slate-600 text-[11px] font-medium"),
        )
        source_tag.textContent = source_lbl

        if coverage and coverage != "—":
            group_tag = _append(
                tags_row,
                _el("span", "inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-blue-50 text-blue-700 text-[11px] font-medium"),
            )
            group_tag.textContent = coverage

        attr = _attribution_text(feed)
        if attr:
            attr_el = _append(body, _el("div", "text-[10px] text-slate-400"))
            attr_el.textContent = f"ที่มา: {_text(attr)}"

        # Actions row
        actions = _append(body, _el("div", "flex flex-wrap items-center gap-2 pt-2 border-t border-slate-100"))

        detail_btn = _append(actions, _el("button", "btn btn-sm btn-primary flex-1 min-w-[100px] text-xs font-semibold rounded-lg shadow-xs h-8 min-h-0", "ดูรายละเอียด"))
        detail_btn.attrs["type"] = "button"
        detail_btn.bind("click", lambda event, selected=feed: self._open_detail(selected, event))

        if _supports_history(feed):
            hist_btn = _append(actions, _el("button", "btn btn-sm btn-outline flex-1 min-w-[100px] text-xs font-semibold rounded-lg text-blue-600 border-slate-200 hover:bg-blue-50 h-8 min-h-0", "ดูประวัติ 7 วัน"))
            hist_btn.attrs["type"] = "button"
            hist_btn.bind("click", lambda event, selected=feed: self._open_history(selected, event))

        if _has_coordinates(feed):
            map_btn = _append(actions, _el("button", "btn btn-sm btn-ghost text-xs text-blue-600 hover:bg-blue-50 px-2.5 rounded-lg h-8 min-h-0", "ดูบนแผนที่"))
            map_btn.attrs["type"] = "button"
            map_btn.bind("click", lambda event, selected=feed: self._fly_to_camera(selected))

        matched_st = self.find_matching_station(feed)
        if matched_st:
            st_code = str(matched_st.get("code", ""))
            st_src = str(matched_st.get("source", ""))
            water_btn = _append(actions, _el("button", "btn btn-sm btn-info btn-outline text-xs h-8 min-h-0 px-2.5 font-medium rounded-lg", "🌊 ดูระดับน้ำ"))
            water_btn.attrs["type"] = "button"
            water_btn.bind("click", lambda event, code=st_code, src=st_src: self._on_view_station(code, src, event))

        detail_url = _safe_http_url(feed.get("detail_url"))
        if detail_url:
            link = _append(actions, _el("a", "btn btn-sm btn-ghost text-xs text-slate-500 hover:bg-slate-100 px-2 rounded-lg h-8 min-h-0", "เปิดต้นทาง"))
            link.attrs["href"] = detail_url
            link.attrs["target"] = "_blank"
            link.attrs["rel"] = "noopener noreferrer"

        return card

    def _on_view_station(self, code, source=None, event=None):
        if hasattr(window, "focus_water_station"):
            window.focus_water_station(code, source)

    def _image_view(self, image_url, title, latest=False):
        wrapper = _el(
            "div",
            "relative w-full aspect-video min-h-[140px] bg-slate-900 overflow-hidden flex items-center justify-center",
        )
        image = _el("img", "block h-full w-full object-cover")
        # The panel is a nested scroll container; browser lazy-loading can
        # leave every camera image as a row of placeholders on first paint.
        image.attrs["loading"] = "eager"
        image.attrs["decoding"] = "async"
        image.attrs["alt"] = title or "ภาพ CCTV"
        image.attrs["src"] = image_url
        state = _append(
            wrapper,
            _el(
                "span",
                "absolute bottom-2 left-2 rounded bg-slate-900/75 px-2 py-1 text-[10px] text-white",
                "กำลังโหลดภาพ...",
            ),
        )
        state.attrs["role"] = "status"
        state.attrs["aria-live"] = "polite"
        state.classList.add("sr-only")
        image.bind("load", lambda event: self._on_image_load(image, state))
        image.bind("error", lambda event: self._on_image_error(image, state))
        wrapper <= image
        return wrapper

    def _on_image_load(self, image, state):
        image.attrs["data-image-state"] = "loaded"
        state.textContent = "ภาพพร้อมแสดง"
        state.classList.add("sr-only")

    def _on_image_error(self, image, state):
        # This is a local browser rendering state, never a hardware status.
        image.attrs["data-image-state"] = "error"
        image.style.display = "none"
        state.className = "flex flex-col items-center justify-center gap-1 text-slate-400 text-xs p-3 text-center"
        state.html = """<i class="ph ph-video-camera-slash text-2xl text-slate-500"></i><span>ภาพไม่สามารถแสดงได้ในขณะนี้</span>"""

    def _selected_value(self, element_id):
        element = document.getElementById(element_id)
        return str(element.value) if element else "all"

    def _set_cards_message(self, message):
        container = document.getElementById("visual_feed_cards")
        if container:
            container.html = ""
            container <= _el(
                "div",
                "col-span-full flex min-h-32 items-center justify-center text-xs text-slate-500",
                message,
            )

    def _set_summary(self, message):
        summary = document.getElementById("visual_feed_summary")
        if summary:
            summary.textContent = _text(message, "")

    def _set_source_health(self, health):
        target = document.getElementById("visual_feed_source_health")
        if not target:
            return
        if not isinstance(health, dict) or not health:
            target.textContent = "สถานะต้นทางไม่ทราบ"
            return
        labels = []
        for source in (HATYAI_SOURCE, "dwr"):
            source_health = _as_dict(health.get(source))
            if not source_health:
                continue
            status = str(source_health.get("status", "unknown")).lower()
            status_label = {
                "healthy": "ปกติ",
                "ok": "ปกติ",
                "degraded": "ขัดข้องบางส่วน",
                "offline": "ออฟไลน์",
                "unknown": "ไม่ทราบ",
            }.get(status, "ไม่ทราบ")
            labels.append(f"{_source_label(source)}: {status_label}")
        target.textContent = " · ".join(labels) if labels else "สถานะต้นทางไม่ทราบ"

    def _open_detail(self, feed, event=None):
        if not isinstance(feed, dict):
            return
        self._focus_return = getattr(event, "target", None) if event else None
        self._active_feed = feed
        self._mode = "latest"
        self._history_generation += 1
        self._latest_generation += 1
        self._populate_detail(feed)
        self._show_latest_section()
        self._open_modal()

    def _detail_history_supported(self):
        return bool(self._active_feed and _supports_history(self._active_feed))

    def _on_detail_history(self, event):
        if self._detail_history_supported():
            # Keep the original card trigger as the focus-return target.
            self._open_history(self._active_feed)

    def _open_history(self, feed, event=None):
        if not _supports_history(feed):
            return
        if event is not None:
            self._focus_return = getattr(event, "target", None)
        elif not self._modal_open:
            self._focus_return = None
        self._active_feed = feed
        self._mode = "history"
        self._history_generation += 1
        generation = self._history_generation
        self._populate_detail(feed)
        self._configure_history_date()
        self._show_history_section()
        self._open_modal()
        self._set_history_message("กำลังโหลดประวัติภาพ...")
        picker = document.getElementById("visual_feed_history_date")
        self._active_date = picker.value if picker else _bangkok_today().isoformat()
        aio.run(self._fetch_history(feed, self._active_date, generation))

    def _open_modal(self):
        modal = document.getElementById("visual_feed_detail_dialog")
        if not modal:
            return
        self._modal_open = True
        modal.classList.remove("hidden")
        try:
            modal.showModal()
        except Exception:
            modal.attrs["open"] = "open"
        try:
            modal.focus()
        except Exception:
            pass

    def _close_detail(self, event=None, restore_focus=True):
        if not self._modal_open and not document.getElementById(
            "visual_feed_detail_dialog"
        ):
            return
        self._modal_open = False
        self._mode = "latest"
        self._history_generation += 1
        modal = document.getElementById("visual_feed_detail_dialog")
        if modal:
            try:
                modal.close()
            except Exception:
                modal.attrs.pop("open", None)
            modal.classList.add("hidden")
        if restore_focus and self._focus_return:
            try:
                self._focus_return.focus()
            except Exception:
                pass
        self._focus_return = None

    def _on_close_detail(self, event):
        self._close_detail(event)

    def _on_modal_cancel(self, event):
        try:
            event.preventDefault()
        except Exception:
            pass
        self._close_detail(event)

    def _on_modal_keydown(self, event):
        key = getattr(event, "key", None) or getattr(event, "keyCode", None)
        if key in ("Escape", "Esc", 27):
            try:
                event.preventDefault()
            except Exception:
                pass
            self._close_detail(event)

    def _on_global_keydown(self, event):
        if self._modal_open:
            self._on_modal_keydown(event)

    def _on_modal_click(self, event):
        modal = document.getElementById("visual_feed_detail_dialog")
        if modal and getattr(event, "target", None) == modal:
            self._close_detail(event)

    def _configure_history_date(self):
        picker = document.getElementById("visual_feed_history_date")
        if not picker:
            return
        earliest, latest = _history_date_window()
        picker.attrs["min"] = earliest.isoformat()
        picker.attrs["max"] = latest.isoformat()
        picker.value = latest.isoformat()

    def _on_history_date_change(self, _event):
        if self._mode != "history" or not self._active_feed:
            return
        picker = document.getElementById("visual_feed_history_date")
        selected = _valid_history_date(picker.value if picker else None)
        if selected is None:
            self._set_history_message("เลือกวันที่ย้อนหลังไม่เกิน 7 วันในเวลาไทย")
            return
        self._active_date = selected.isoformat()
        self._history_generation += 1
        generation = self._history_generation
        self._set_history_message("กำลังโหลดประวัติภาพ...")
        aio.run(self._fetch_history(self._active_feed, self._active_date, generation))

    def _on_back_to_latest(self, _event):
        if not self._active_feed:
            return
        self._mode = "latest"
        self._history_generation += 1
        self._latest_generation += 1
        self._populate_detail(self._active_feed)
        self._show_latest_section()
        if self._should_poll_latest():
            aio.run(self.refresh())

    async def _fetch_history(self, feed, selected_date, generation):
        if not self._should_fetch_history() or generation != self._history_generation:
            return False
        source = quote(str(feed.get("source", "")), safe="")
        upstream_id = quote(str(feed.get("upstream_id", "")), safe="")
        url = f"{self.endpoint}/{source}/{upstream_id}/history?date={selected_date}"
        try:
            response = await aio.get(url, cache=True)
            if (
                getattr(response, "status", 200) < 200
                or getattr(response, "status", 200) >= 300
            ):
                raise ValueError("history request failed")
            parsed = json.loads(response.data)
            if not isinstance(parsed, dict) or not isinstance(
                parsed.get("frames"), list
            ):
                raise ValueError("history response invalid")
            if (
                generation != self._history_generation
                or not self._should_fetch_history()
                or self._feed_key(self._active_feed) != self._feed_key(feed)
                or self._active_date != selected_date
            ):
                return False
            self._history_frames = self._normalize_history_frames(parsed["frames"])
            self._render_history_frames(
                self._history_frames, bool(parsed.get("possibly_truncated"))
            )
            return True
        except Exception:
            if generation == self._history_generation and self._should_fetch_history():
                self._set_history_message("โหลดประวัติภาพไม่สำเร็จ ลองเลือกวันที่ใหม่")
            return False

    def _normalize_history_frames(self, frames):
        normalized = []
        for frame in frames:
            if not isinstance(frame, dict):
                continue
            captured = _parse_utc(frame.get("captured_at"))
            if captured is None:
                continue
            image_url = _resolve_image_url(frame.get("image_url"), self.api_url)
            thumbnail_url = _resolve_image_url(frame.get("thumbnail_url"), self.api_url)
            if not image_url and not thumbnail_url:
                continue
            normalized.append(
                {
                    "captured_at": captured,
                    "image_url": image_url,
                    "thumbnail_url": thumbnail_url,
                }
            )
        return normalized

    def _render_history_frames(self, frames, possibly_truncated=False):
        container = document.getElementById("visual_feed_history_frames")
        if not container:
            return
        container.html = ""
        if not frames:
            self._set_history_message("วันนี้ยังไม่มีภาพประวัติจากต้นทาง")
            return
        suffix = " · แสดงได้ไม่ครบทุกภาพจากต้นทาง" if possibly_truncated else ""
        self._set_history_message(f"ประวัติภาพ {len(frames)} ภาพ{suffix}")
        for frame in frames:
            figure = _append(
                container,
                _el(
                    "figure",
                    "group overflow-hidden rounded-xl border border-slate-200 bg-white shadow-xs hover:shadow-md transition-all duration-200 flex flex-col",
                ),
            )
            full_url = frame.get("image_url") or frame.get("thumbnail_url")
            thumbnail_url = frame.get("thumbnail_url") or full_url
            if thumbnail_url:
                link = _append(figure, _el("a", "block relative aspect-video bg-slate-900 overflow-hidden"))
                link.attrs["href"] = full_url
                link.attrs["target"] = "_blank"
                link.attrs["rel"] = "noopener noreferrer"
                img_view = self._image_view(thumbnail_url, "ภาพประวัติ CCTV")
                img_view.classList.add("group-hover:scale-105", "transition-transform", "duration-200")
                link <= img_view
            caption = _append(
                figure, _el("figcaption", "p-2.5 text-xs font-semibold text-slate-700 bg-slate-50 border-t border-slate-100 flex items-center justify-between")
            )
            caption.textContent = _format_time(frame.get("captured_at"))

    def _set_history_message(self, message):
        target = document.getElementById("visual_feed_history_status")
        if target:
            target.textContent = _text(message, "")

    def _show_latest_section(self):
        latest = document.getElementById("visual_feed_detail_latest")
        controls = document.getElementById("visual_feed_history_controls")
        frames = document.getElementById("visual_feed_history_frames")
        if latest:
            latest.classList.remove("hidden")
        if controls:
            controls.classList.add("hidden")
        if frames:
            frames.classList.add("hidden")

    def _show_history_section(self):
        latest = document.getElementById("visual_feed_detail_latest")
        controls = document.getElementById("visual_feed_history_controls")
        frames = document.getElementById("visual_feed_history_frames")
        if latest:
            latest.classList.add("hidden")
        if controls:
            controls.classList.remove("hidden")
        if frames:
            frames.classList.remove("hidden")

    def _populate_detail(self, feed):
        title = _text(feed.get("title_th") or feed.get("name_th") or feed.get("name"))
        availability = _availability(feed)
        heading = document.getElementById("visual_feed_detail_title")
        meta = document.getElementById("visual_feed_detail_meta")
        badge = document.getElementById("visual_feed_detail_badge")
        latest_container = document.getElementById("visual_feed_detail_latest_image")
        history_button = document.getElementById("visual_feed_history_button")
        if heading:
            heading.textContent = title
        if badge:
            badge.style.backgroundColor = AVAILABILITY_COLORS[availability]
            if availability == "online":
                badge.html = """<span class="w-1.5 h-1.5 rounded-full bg-white animate-pulse"></span><span>ออนไลน์ LIVE</span>"""
            else:
                badge.textContent = AVAILABILITY_LABELS[availability]
        if meta:
            meta.textContent = (
                f"{_source_label(feed.get('source'))} · "
                f"{_text(feed.get('coverage_group'))}"
            )
        if latest_container:
            latest_container.html = ""
            image_url = _resolve_image_url(feed.get("image_url"), self.api_url)
            image_url = _version_image_url(image_url, feed.get("captured_at"))
            if image_url:
                latest_container <= self._image_view(image_url, title, latest=True)
            else:
                latest_container <= _el(
                    "div",
                    "flex aspect-video items-center justify-center rounded-lg bg-slate-900 text-xs text-slate-400",
                    "ไม่มีภาพล่าสุด",
                )
        latest_meta = document.getElementById("visual_feed_detail_latest_meta")
        if latest_meta:
            captured = _parse_utc(feed.get("captured_at"))
            status = (
                "ภาพล่าสุดเก่ากว่า 30 นาที"
                if _is_latest_stale(feed)
                else AVAILABILITY_LABELS[availability]
            )
            latest_meta.textContent = f"สถานะ: {status} · ภาพถ่ายเมื่อ: {_format_time(captured)}"
        station_link = document.getElementById("visual_feed_detail_station_link")
        if station_link:
            matched_st = self.find_matching_station(feed)
            if matched_st:
                st_code = str(matched_st.get("code", ""))
                st_name = str(matched_st.get("name_th") or matched_st.get("name", ""))
                st_src = str(matched_st.get("source", ""))
                wl_val = None
                for m in matched_st.get("metrics") or []:
                    if str(m.get("metric_type", "")).lower() == "waterlevel":
                        wl_val = m.get("value")
                        break
                wl_str = ""
                if wl_val is not None:
                    try:
                        wl_str = f" · ระดับน้ำ {float(wl_val):.2f} ม."
                    except Exception:
                        pass

                station_link.html = f"""
                <div class="my-2 p-3 rounded-xl bg-blue-50/80 border border-blue-200 flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                    <div class="flex items-center gap-2.5">
                        <span class="text-xl">🌊</span>
                        <div>
                            <div class="font-bold text-xs text-blue-950">สถานีวัดน้ำที่ตั้งเดียวกัน: {st_name}</div>
                            <div class="text-[11px] text-blue-700">รหัสสถานี #{st_code}{wl_str}</div>
                        </div>
                    </div>
                    <button type="button" onclick="if(window.focus_water_station_from_modal)window.focus_water_station_from_modal('{st_code}','{st_src}')"
                        class="btn btn-xs btn-primary gap-1 text-white shrink-0 shadow-sm font-medium">
                        <i class="ph ph-waves"></i> ดูกราฟระดับน้ำ
                    </button>
                </div>
                """
                station_link.classList.remove("hidden")
            else:
                station_link.html = ""
                station_link.classList.add("hidden")
        if history_button:
            if _supports_history(feed):
                history_button.classList.remove("hidden")
            else:
                history_button.classList.add("hidden")

    def _refresh_open_latest_detail(self):
        if self._modal_open and self._mode == "latest" and self._active_feed:
            key = self._feed_key(self._active_feed)
            for feed in self.latest_feeds:
                if self._feed_key(feed) == key:
                    self._active_feed = feed
                    self._populate_detail(feed)
                    return

    def _feed_key(self, feed):
        feed = _as_dict(feed)
        return (str(feed.get("source", "")), str(feed.get("upstream_id", "")))


def _supports_history(feed):
    feed = _as_dict(feed)
    return feed.get("source") == HATYAI_SOURCE and feed.get("history_supported") is True


def _source_label(source):
    source = str(source or "").strip()
    return SOURCE_LABELS.get(source, _text(source, "ไม่ทราบต้นทาง"))


def _attribution_text(feed):
    attribution = _as_dict(_as_dict(feed).get("attribution"))
    return attribution.get("provider") or attribution.get("source_url") or ""


def _format_time(value):
    if value is None:
        return "ไม่ทราบเวลา"
    if not isinstance(value, datetime.datetime):
        value = _parse_utc(value)
    if value is None:
        return "ไม่ทราบเวลา"
    return value.astimezone(BANGKOK_TZ).strftime("%d/%m/%Y %H:%M น.")
