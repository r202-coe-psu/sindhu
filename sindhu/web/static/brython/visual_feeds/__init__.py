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
THAI_DAYS_SHORT = ["จ.", "อ.", "พ.", "พฤ.", "ศ.", "ส.", "อา."]
THAI_MONTHS_SHORT = [
    "",
    "ม.ค.",
    "ก.พ.",
    "มี.ค.",
    "เม.ย.",
    "พ.ค.",
    "มิ.ย.",
    "ก.ค.",
    "ส.ค.",
    "ก.ย.",
    "ต.ค.",
    "พ.ย.",
    "ธ.ค.",
]
# 28 Hatyai + 2 DWR + 11 RID cameras are currently catalogued.  Keep a
# little headroom while retaining a client-side safety cap.
MAX_CCTV_FEEDS = 50

HATYAI_SOURCE = "hatyai_city_climate"

AVAILABILITY_LABELS = {
    "online": "ออนไลน์",
    "stale": "ข้อมูลเก่า",
    "degraded": "ขัดข้องบางส่วน",
    "offline": "ออฟไลน์",
    "unknown": "ไม่ทราบสถานะ",
}

SOURCE_LABELS = {
    HATYAI_SOURCE: "Hatyai City Climate",
    "dwr": "กรมทรัพยากรน้ำ (DWR)",
    "rid": "กรมชลประทาน (RID)",
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
    if not (
        value.startswith("/v1/visual-feeds/dwr/")
        or value.startswith("/v1/visual-feeds/rid/")
    ):
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
        or not (
            path.startswith("/v1/visual-feeds/dwr/")
            or path.startswith("/v1/visual-feeds/rid/")
        )
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


def _availability_status_class(availability):
    """Map all camera states to the two-state visual language."""
    return (
        "cctv-status--online"
        if availability == "online"
        else "cctv-status--unavailable"
    )


def _is_displayable_camera(feed):
    """The public monitor shows only cameras that are online with an image."""
    feed = _as_dict(feed)
    return _availability(feed) == "online" and bool(
        str(feed.get("image_url") or "").strip()
    )


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
        # Water is the default panel. CCTV still loads once so its online map
        # markers are available without starting background CCTV polling.
        self._visual_panel_active = False
        self._mode = "latest"
        self._modal_open = False
        self._active_feed = None
        self._active_date = None
        self._history_frames = []
        self._history_index = -1
        self._touch_start_x = None
        self._focus_return = None

    def start(self, map_owner=None):
        """Bind controls and fetch initial CCTV feeds so markers appear on map."""
        self.map_owner = map_owner
        self.running = True
        try:
            window.open_cctv_detail = (
                lambda source, upstream_id, date_iso=None: self._open_detail_by_id(
                    source, upstream_id, date_iso
                )
            )
            window.focus_water_station_from_modal = (
                lambda code, source=None: self._focus_water_station_from_modal(
                    code, source
                )
            )
        except Exception:
            pass
        self._bind_controls()
        self._show_water_panel(None)
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
        if not stations and hasattr(window, "monitors"):
            mon = getattr(window, "monitors", None)
            if mon and hasattr(mon, "data") and isinstance(mon.data, dict):
                stations = mon.data.get("stations", [])
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
        """Load once for map markers while the water panel remains the default."""
        await self.refresh(force=True)
        for _ in range(50):
            m = self._get_map()
            if m and hasattr(m, "show_visual_feeds"):
                self.update_map_markers()
                break
            await aio.sleep(0.2)

    def _open_detail_by_id(self, source, upstream_id, target_date=None):
        for feed in self.latest_feeds:
            if str(feed.get("source")) == str(source) and str(
                feed.get("upstream_id")
            ) == str(upstream_id):
                if target_date and _supports_history(feed):
                    self._open_history(feed, target_date=target_date)
                else:
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
            if not _is_displayable_camera(feed) or not _has_coordinates(feed):
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

    def on_water_stations_updated(self):
        """Refresh camera actions once co-located water stations are ready."""
        if self.latest_data is None:
            return
        self.render_cards()
        self._refresh_open_detail()

    def _on_marker_click(self, feed):
        """Open the same camera viewer from a map pin as from a card.

        Map pins previously opened a separate Leaflet popup while cards opened
        the full viewer.  That split made the selected day and image differ
        between entry points, especially on a phone.  One controller now owns
        the viewer state regardless of how the user chose the camera.
        """
        self._open_detail(feed)

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

        for element_id in ("visual_feed_group_filter",):
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
        if "visual_feed_history_date" in document:
            document["visual_feed_history_date"].bind(
                "change", self._on_history_date_change
            )
        if "visual_feed_day_slide_prev" in document:
            document["visual_feed_day_slide_prev"].bind(
                "click", self._on_day_slide_prev
            )
        if "visual_feed_day_slide_next" in document:
            document["visual_feed_day_slide_next"].bind(
                "click", self._on_day_slide_next
            )
        if "visual_feed_history_previous" in document:
            document["visual_feed_history_previous"].bind(
                "click", self._on_history_previous
            )
        if "visual_feed_history_next" in document:
            document["visual_feed_history_next"].bind("click", self._on_history_next)
        if "visual_feed_history_viewport" in document:
            viewport = document["visual_feed_history_viewport"]
            viewport.bind("touchstart", self._on_history_touch_start)
            viewport.bind("touchend", self._on_history_touch_end)
            viewport.bind("touchcancel", self._on_history_touch_cancel)
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
                for cls in ("grid-cols-1", "p-3.5", "gap-3.5", "gap-0", "px-3"):
                    container.classList.remove(cls)
                container.classList.add("grid-cols-2")
                container.classList.add("p-2.5")
                container.classList.add("gap-2.5")
            else:
                for cls in ("grid-cols-2", "p-2.5", "gap-2.5"):
                    container.classList.remove(cls)
                container.classList.add("grid-cols-1")
                container.classList.add("gap-0")
                container.classList.add("px-3")

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
            header_title.html = """<i class="ph ph-video-camera text-xl text-blue-200" aria-hidden="true"></i><span>กล้อง CCTV เฝ้าระวังน้ำท่วม</span>"""
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
            header_title.html = """<i class="ph ph-waves text-xl text-blue-200" aria-hidden="true"></i><span>สถานการณ์ระดับน้ำและเตือนภัย</span>"""
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

            feeds = [
                feed
                for feed in _filter_cctv_feeds(parsed["visual_feeds"])
                if _is_displayable_camera(feed)
            ]
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
            if group != "all" and feed_group != group:
                continue
            if query:
                searchable = (
                    str(feed.get("title_th") or "")
                    + " "
                    + str(feed.get("name_th") or "")
                    + " "
                    + str(feed.get("name") or "")
                    + " "
                    + str(feed.get("code") or "")
                    + " "
                    + str(feed.get("coverage_group") or "")
                ).lower()
                if query not in searchable:
                    continue
            visible.append(feed)

        container = document.getElementById("visual_feed_cards")
        if not container:
            return
        container.html = ""
        if not visible:
            message = (
                "ขณะนี้ไม่มีกล้อง CCTV ที่พร้อมใช้งาน"
                if not self.latest_feeds
                else "ไม่พบกล้องตามคำค้นหาหรือพื้นที่ที่เลือก"
            )
            self._set_cards_message(message)
        else:
            for feed in visible:
                container <= self._build_card(feed)

        total = len(self.latest_feeds)
        if total:
            if len(visible) == total:
                self._set_summary(f"พร้อมใช้งาน {total} จุด")
            else:
                self._set_summary(f"แสดง {len(visible)} จาก {total} จุด")
        else:
            self._set_summary("ไม่มีกล้องพร้อมใช้งาน")
        self.update_map_markers(visible)

    def _build_card(self, feed):
        availability = _availability(feed)
        source = str(feed.get("source", ""))
        upstream_id = str(feed.get("upstream_id", ""))
        title = _text(feed.get("title_th") or feed.get("name_th") or feed.get("name"))
        coverage = _text(feed.get("coverage_group"))
        source_lbl = _source_label(feed.get("source"))

        image_url = _resolve_image_url(feed.get("image_url"), self.api_url)
        image_url = _version_image_url(image_url, feed.get("captured_at"))

        if self.view_mode == "grid":
            # Grid View (2 columns, compact)
            card = _el(
                "article",
                "visual-feed-card cctv-list-item group relative overflow-hidden rounded-xl border border-slate-200/90 bg-white transition-shadow duration-200 flex flex-col justify-between",
            )
            card.attrs["data-availability"] = availability
            card.attrs["id"] = f"cctv_card_{source}_{upstream_id}"

            # Image section
            img_container = _el(
                "div",
                "visual-feed-media relative aspect-video bg-slate-900 overflow-hidden cursor-pointer",
            )
            if image_url:
                img_view = self._image_view(image_url, title, latest=True)
                img_container <= img_view
            else:
                img_container <= _el(
                    "div",
                    "flex h-full w-full items-center justify-center bg-slate-800 text-[10px] text-slate-400",
                    "ไม่มีภาพ",
                )
            img_container.bind(
                "click", lambda event, selected=feed: self._open_detail(selected, event)
            )

            _append(card, img_container)

            # Body
            body = _append(
                card,
                _el("div", "p-2.5 flex flex-col justify-between flex-1 space-y-1.5"),
            )

            # Title
            title_btn = _el(
                "button",
                "text-left text-xs font-bold leading-snug text-slate-800 hover:text-blue-600 transition-colors line-clamp-2",
            )
            title_btn.attrs["type"] = "button"
            title_btn.attrs["aria-label"] = f"เปิดรายละเอียด {title}"
            title_btn.textContent = title
            title_btn.bind(
                "click", lambda event, selected=feed: self._open_detail(selected, event)
            )
            _append(body, title_btn)

            # Status stays beside the details so the camera image stays clear.
            meta_div = _append(body, _el("div", "text-[10px] text-slate-500 truncate"))
            meta_div.textContent = f"ออนไลน์ · {coverage} · {source_lbl}"

            # Actions
            actions = _append(
                body,
                _el(
                    "div",
                    "flex items-center gap-1 pt-1.5 border-t border-slate-100",
                ),
            )

            detail_label = "ดูภาพวันนี้"
            detail_btn = _append(
                actions,
                _el(
                    "button",
                    "btn btn-xs btn-primary flex-1 min-w-0 text-[10px] font-semibold h-7 min-h-0 px-2 rounded-lg truncate",
                    detail_label,
                ),
            )
            detail_btn.attrs["type"] = "button"
            detail_btn.attrs["title"] = detail_label
            detail_btn.bind(
                "click", lambda event, selected=feed: self._open_detail(selected, event)
            )

            if _has_coordinates(feed):
                map_btn = _append(
                    actions,
                    _el(
                        "button",
                        "btn btn-xs btn-ghost h-7 w-7 min-h-0 shrink-0 rounded-lg p-0 text-blue-600 hover:bg-blue-50 flex items-center justify-center",
                    ),
                )
                map_btn.attrs["type"] = "button"
                map_btn.attrs["title"] = "ดูบนแผนที่"
                map_btn.attrs["aria-label"] = f"ดู {title} บนแผนที่"
                map_btn.html = '<i class="ph ph-map-pin text-sm" aria-hidden="true"></i>'
                map_btn.bind(
                    "click", lambda event, selected=feed: self._fly_to_camera(selected)
                )

            matched_st = self.find_matching_station(feed)
            if matched_st:
                st_code = str(matched_st.get("code", ""))
                st_src = str(matched_st.get("source", ""))
                water_btn = _append(
                    actions,
                    _el(
                        "button",
                        "btn btn-xs btn-outline h-7 w-7 min-h-0 shrink-0 rounded-lg p-0 border-sky-200 bg-sky-50 text-sky-700 hover:bg-sky-100 flex items-center justify-center",
                    ),
                )
                water_btn.attrs["type"] = "button"
                water_btn.attrs["title"] = "ดูระดับน้ำ"
                water_btn.attrs["aria-label"] = f"ดูระดับน้ำใกล้ {title}"
                water_btn.html = '<i class="ph ph-waves text-sm" aria-hidden="true"></i>'
                water_btn.bind(
                    "click",
                    lambda event, code=st_code, src=st_src: self._on_view_station(
                        code, src, event
                    ),
                )

            return card

        # List View (1 column, full-width 16:9 images)
        card = _el(
            "article",
            "visual-feed-card cctv-list-item group relative border-b bg-transparent py-3 transition-colors duration-150 flex flex-col",
        )
        card.attrs["data-availability"] = availability
        card.attrs["id"] = f"cctv_card_{source}_{upstream_id}"

        # Image Container
        img_container = _el(
            "div",
            "visual-feed-media relative aspect-video bg-slate-900 overflow-hidden cursor-pointer rounded-xl shadow-sm",
        )
        if image_url:
            img_view = self._image_view(image_url, title, latest=True)
            img_container <= img_view
        else:
            img_container <= _el(
                "div",
                "flex h-full w-full items-center justify-center bg-slate-800 text-xs text-slate-400",
                "ไม่มีภาพตัวอย่าง",
            )
        img_container.bind(
            "click", lambda event, selected=feed: self._open_detail(selected, event)
        )

        _append(card, img_container)

        # Body
        body = _append(card, _el("div", "px-1 pt-3 space-y-2.5"))

        # Title button
        title_btn = _el(
            "button",
            "min-w-0 text-left text-sm font-bold leading-snug text-slate-900 hover:text-blue-600 transition-colors",
        )
        title_btn.attrs["type"] = "button"
        title_btn.attrs["aria-label"] = f"เปิดรายละเอียด {title}"
        title_btn.textContent = title
        title_btn.bind(
            "click", lambda event, selected=feed: self._open_detail(selected, event)
        )
        _append(body, title_btn)

        # Keep availability out of the image, then keep source context quiet.
        meta_parts = ["ออนไลน์", source_lbl]
        if coverage and coverage != "—":
            meta_parts.append(coverage)
        meta_line = _append(
            body, _el("p", "truncate text-[11px] font-medium text-slate-500")
        )
        meta_line.textContent = " · ".join(meta_parts)

        attr = _attribution_text(feed)
        if attr:
            attr_el = _append(body, _el("div", "text-[10px] text-slate-400"))
            attr_el.textContent = f"ที่มา: {_text(attr)}"

        # Actions row
        actions = _append(
            body,
            _el(
                "div",
                "flex flex-wrap items-center gap-1.5 pt-2 border-t border-slate-200",
            ),
        )

        # Keep the main action identical for every camera.  Providers without
        # history simply open their current image in the same viewer.
        detail_label = "ดูภาพวันนี้"
        detail_btn = _append(
            actions,
            _el(
                "button",
                "btn btn-sm btn-primary flex-1 min-w-0 whitespace-nowrap text-xs font-semibold rounded-lg shadow-xs h-9 min-h-0",
                detail_label,
            ),
        )
        detail_btn.attrs["type"] = "button"
        detail_btn.bind(
            "click", lambda event, selected=feed: self._open_detail(selected, event)
        )

        if _has_coordinates(feed):
            map_btn = _append(
                actions,
                _el(
                    "button",
                    "btn btn-sm btn-ghost h-9 min-h-0 w-9 shrink-0 rounded-lg p-0 text-blue-600 hover:bg-blue-50",
                ),
            )
            map_btn.attrs["type"] = "button"
            map_btn.attrs["aria-label"] = f"ดู {title} บนแผนที่"
            map_btn.attrs["title"] = "ดูบนแผนที่"
            map_btn.html = '<i class="ph ph-map-pin text-base" aria-hidden="true"></i>'
            map_btn.bind(
                "click", lambda event, selected=feed: self._fly_to_camera(selected)
            )

        matched_st = self.find_matching_station(feed)
        if matched_st:
            st_code = str(matched_st.get("code", ""))
            st_src = str(matched_st.get("source", ""))
            water_btn = _append(
                actions,
                _el(
                    "button",
                    "btn btn-sm btn-outline h-9 min-h-0 shrink-0 gap-1 rounded-lg border-sky-200 bg-sky-50 px-2 text-xs text-sky-700 hover:bg-sky-100",
                ),
            )
            water_btn.attrs["type"] = "button"
            water_btn.attrs["aria-label"] = f"ดูระดับน้ำใกล้ {title}"
            water_btn.attrs["title"] = "ดูระดับน้ำ"
            water_btn.html = '<i class="ph ph-waves text-base" aria-hidden="true"></i><span>ดูระดับน้ำ</span>'
            water_btn.bind(
                "click",
                lambda event, code=st_code, src=st_src: self._on_view_station(
                    code, src, event
                ),
            )

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
        for source in (HATYAI_SOURCE, "dwr", "rid"):
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
        if _supports_history(feed):
            self._open_history(feed, event)
            return
        if event is not None:
            self._focus_return = getattr(event, "target", None)
        elif not self._modal_open:
            self._focus_return = None
        self._active_feed = feed
        self._mode = "realtime"
        self._history_generation += 1
        self._latest_generation += 1
        self._populate_detail(feed)
        self._configure_history_date()
        self._show_history_section()
        self._render_realtime_frame(feed)
        self._open_modal()

    def _render_realtime_frame(self, feed):
        container = document.getElementById("visual_feed_history_frame")
        if not container:
            return
        container.html = ""
        image_url = _resolve_image_url(feed.get("image_url"), self.api_url)
        image_url = _version_image_url(image_url, feed.get("captured_at"))
        title = _text(feed.get("title_th") or feed.get("name_th") or feed.get("name"))
        if image_url:
            figure = _append(
                container,
                _el("figure", "is-entering overflow-hidden bg-slate-100"),
            )
            image_view = self._image_view(image_url, title, latest=True)
            image_view.attrs["data-full-image-url"] = image_url
            figure <= image_view
        else:
            container <= _el(
                "div",
                "flex h-full w-full items-center justify-center bg-slate-800 text-xs text-slate-400",
                "ไม่มีภาพตัวอย่าง",
            )
        previous = document.getElementById("visual_feed_history_previous")
        following = document.getElementById("visual_feed_history_next")
        counter = document.getElementById("visual_feed_history_counter")
        if previous:
            previous.classList.add("hidden")
        if following:
            following.classList.add("hidden")
        if counter:
            counter.textContent = ""
        self._set_history_message("")

    def _detail_history_supported(self):
        return bool(self._active_feed and _supports_history(self._active_feed))

    def _on_detail_history(self, event):
        if self._detail_history_supported():
            # Keep the original card trigger as the focus-return target.
            self._open_history(self._active_feed)

    def _open_history(self, feed, event=None, target_date=None):
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
        self._configure_history_date(target_date=target_date)
        self._show_history_section()
        self._open_modal()
        self._set_history_message("กำลังโหลดประวัติภาพ…")
        self._set_history_load_state("loading")
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
        self._position_modal_over_map(modal)
        try:
            modal.focus()
        except Exception:
            pass

    def _position_modal_over_map(self, modal):
        """Keep the compact viewer inside the map on desktop-sized layouts.

        The same viewer is used by cards and map pins.  Centering a dialog in
        the full browser viewport made it spill over the data panel, so use the
        visible map bounds as the placement context whenever there is room.
        Mobile keeps the normal centred dialog because the map and list stack.
        """
        try:
            viewport_width = float(window.innerWidth)
            map_element = document.getElementById("mapid")
            if not map_element or viewport_width < 1024:
                modal.style.inset = ""
                modal.style.left = ""
                modal.style.top = ""
                modal.style.right = ""
                modal.style.bottom = ""
                modal.style.margin = ""
                return

            map_rect = map_element.getBoundingClientRect()
            modal_rect = modal.getBoundingClientRect()
            if map_rect.width <= 0 or map_rect.height <= 0 or modal_rect.width <= 0:
                return

            left = map_rect.left + max(12, (map_rect.width - modal_rect.width) / 2)
            top = map_rect.top + max(12, (map_rect.height - modal_rect.height) / 2)
            modal.style.inset = "auto"
            modal.style.left = f"{int(left)}px"
            modal.style.top = f"{int(top)}px"
            modal.style.right = "auto"
            modal.style.bottom = "auto"
            modal.style.margin = "0"
        except Exception:
            # CSS provides the safe centred fallback when map measurement is
            # unavailable, such as a partially loaded map.
            pass

    def _close_detail(self, event=None, restore_focus=True):
        modal = document.getElementById("visual_feed_detail_dialog")
        if modal:
            try:
                modal.close()
            except Exception:
                modal.removeAttribute("open")
            modal.classList.add("hidden")
            try:
                modal.style.inset = ""
                modal.style.left = ""
                modal.style.top = ""
                modal.style.right = ""
                modal.style.bottom = ""
                modal.style.margin = ""
            except Exception:
                pass
        self._modal_open = False
        self._active_feed = None
        self._mode = "latest"
        self._history_generation += 1
        self._latest_generation += 1
        return_target = self._focus_return
        self._focus_return = None
        if restore_focus and return_target and hasattr(return_target, "focus"):
            try:
                return_target.focus()
            except Exception:
                pass

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

    def _configure_history_date(self, target_date=None):
        picker = document.getElementById("visual_feed_history_date")
        earliest, latest = _history_date_window()
        chosen = _valid_history_date(target_date) if target_date else None
        selected = chosen.isoformat() if chosen else latest.isoformat()
        if picker:
            picker.attrs["min"] = earliest.isoformat()
            picker.attrs["max"] = latest.isoformat()
            picker.value = selected
        self._active_date = selected
        self._render_7days_rail()

    def _render_7days_rail(self):
        rail = document.getElementById("visual_feed_7days_rail")
        if not rail:
            return
        rail.html = ""
        earliest, latest = _history_date_window()
        today = latest
        active_iso = self._active_date or today.isoformat()

        days = [earliest + datetime.timedelta(days=i) for i in range(HISTORY_DAYS)]
        active_card = None
        for d in days:
            d_iso = d.isoformat()
            is_active = d_iso == active_iso
            if d == today:
                top_text = "วันนี้"
            elif d == today - datetime.timedelta(days=1):
                top_text = "เมื่อวาน"
            else:
                top_text = THAI_DAYS_SHORT[d.weekday()]
            bottom_text = f"{d.day} {THAI_MONTHS_SHORT[d.month]}"

            btn = _el(
                "button",
                "cctv-day-card flex flex-col items-center justify-center min-w-[64px] sm:min-w-[78px] py-1.5 px-1.5 sm:px-2 rounded-xl border transition-all cursor-pointer select-none shrink-0 touch-manipulation active:scale-95"
                + (
                    " is-active bg-sky-50 text-sky-700 border-sky-300 ring-2 ring-sky-400/30 shadow-xs font-bold"
                    if is_active
                    else " bg-white hover:bg-slate-100 text-slate-600 hover:text-slate-900 border-slate-200 shadow-2xs font-medium"
                ),
            )
            btn.attrs["type"] = "button"
            btn.attrs["id"] = f"cctv_day_{d_iso}"
            btn.attrs["data-date"] = d_iso
            btn.attrs["role"] = "tab"
            btn.attrs["aria-selected"] = "true" if is_active else "false"
            top_color = "text-sky-600 font-bold" if is_active else "text-slate-700"
            btn.html = (
                f'<span class="text-[11px] leading-tight {top_color}">{top_text}</span>'
                f'<span class="text-[10px] leading-tight text-slate-400 mt-0.5 font-mono">{bottom_text}</span>'
            )
            btn.bind("click", lambda ev, target_d=d_iso: self._on_select_day(target_d))
            rail <= btn

            if is_active:
                active_card = btn

        if active_card:
            try:
                active_card.scrollIntoView(
                    {"behavior": "smooth", "inline": "center", "block": "nearest"}
                )
            except Exception:
                pass

        self._update_day_slide_buttons()

    def _update_day_slide_buttons(self):
        earliest, latest = _history_date_window()
        btn_prev = document.getElementById("visual_feed_day_slide_prev")
        btn_next = document.getElementById("visual_feed_day_slide_next")
        label_el = document.getElementById("visual_feed_selected_day_label")
        if self._active_date:
            try:
                curr = datetime.date.fromisoformat(self._active_date)
                if btn_prev:
                    btn_prev.disabled = curr <= earliest
                if btn_next:
                    btn_next.disabled = curr >= latest
                if label_el:
                    if curr == latest:
                        label_el.textContent = "(วันนี้)"
                    elif curr == latest - datetime.timedelta(days=1):
                        label_el.textContent = "(เมื่อวาน)"
                    else:
                        label_el.textContent = (
                            f"({curr.day} {THAI_MONTHS_SHORT[curr.month]})"
                        )
            except Exception:
                pass

    def _on_select_day(self, date_str):
        if not self._active_feed:
            return
        selected = _valid_history_date(date_str)
        if selected is None:
            return
        if self._active_date == selected.isoformat():
            return
        self._active_date = selected.isoformat()
        picker = document.getElementById("visual_feed_history_date")
        if picker:
            picker.value = self._active_date
        self._render_7days_rail()

        if not _supports_history(self._active_feed):
            earliest, latest = _history_date_window()
            container = document.getElementById("visual_feed_history_frame")
            counter = document.getElementById("visual_feed_history_counter")
            if counter:
                counter.textContent = ""
            prev_btn = document.getElementById("visual_feed_history_previous")
            next_btn = document.getElementById("visual_feed_history_next")
            if prev_btn:
                prev_btn.classList.add("hidden")
            if next_btn:
                next_btn.classList.add("hidden")

            if selected == latest:
                self._render_realtime_frame(self._active_feed)
            else:
                if container:
                    container.html = ""
                    notice = _append(
                        container,
                        _el(
                            "div",
                            "flex flex-col items-center justify-center gap-2 h-full w-full bg-slate-50 text-slate-500 text-xs p-6 text-center select-none",
                        ),
                    )
                    notice.html = '<i class="ph ph-video-camera-slash text-3xl text-slate-400" aria-hidden="true"></i><span>กล้องจุดนี้ให้บริการเฉพาะภาพสด Realtime<br><span class="text-[11px] text-slate-400 mt-1 block">(ไม่มีข้อมูลภาพย้อนหลัง 7 วัน)</span></span>'
                self._set_history_message("กล้องนี้มีเฉพาะภาพสด Realtime")
            return

        self._history_generation += 1
        generation = self._history_generation
        self._set_history_message("กำลังโหลดประวัติภาพ…")
        self._set_history_load_state("loading")
        aio.run(self._fetch_history(self._active_feed, self._active_date, generation))

    def _on_day_slide_prev(self, _event=None):
        if not self._active_date:
            return
        earliest, latest = _history_date_window()
        curr = datetime.date.fromisoformat(self._active_date)
        prev_d = curr - datetime.timedelta(days=1)
        if prev_d >= earliest:
            self._on_select_day(prev_d.isoformat())

    def _on_day_slide_next(self, _event=None):
        if not self._active_date:
            return
        earliest, latest = _history_date_window()
        curr = datetime.date.fromisoformat(self._active_date)
        next_d = curr + datetime.timedelta(days=1)
        if next_d <= latest:
            self._on_select_day(next_d.isoformat())

    def _on_history_date_change(self, _event):
        if not self._active_feed:
            return
        picker = document.getElementById("visual_feed_history_date")
        selected = _valid_history_date(picker.value if picker else None)
        if selected is None:
            self._set_history_message("เลือกวันที่ย้อนหลังไม่เกิน 7 วันในเวลาไทย")
            self._set_history_load_state("error")
            return
        self._on_select_day(selected.isoformat())

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
            self._set_history_load_state("success")
            return True
        except Exception:
            if generation == self._history_generation and self._should_fetch_history():
                self._set_history_message("โหลดประวัติภาพไม่สำเร็จ ลองเลือกวันที่ใหม่")
                self._set_history_load_state("error")
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
        normalized.sort(key=lambda frame: frame["captured_at"])
        return normalized

    def _render_history_frames(self, frames, possibly_truncated=False):
        frame_container = document.getElementById("visual_feed_history_frame")
        if not frame_container:
            return
        frame_container.html = ""
        if not frames:
            self._history_index = -1
            self._update_history_navigation()
            self._set_history_message("วันนี้ยังไม่มีภาพประวัติจากต้นทาง")
            return
        suffix = " · แสดงได้ไม่ครบทุกภาพจากต้นทาง" if possibly_truncated else ""
        self._set_history_message(suffix.lstrip(" ·"))
        self._history_index = len(frames) - 1
        self._render_history_frame()

    def _render_history_frame(self):
        container = document.getElementById("visual_feed_history_frame")
        if not container or not self._history_frames:
            self._update_history_navigation()
            return
        self._history_index = max(
            0, min(self._history_index, len(self._history_frames) - 1)
        )
        frame = self._history_frames[self._history_index]
        container.html = ""
        figure = _append(
            container,
            _el("figure", "is-entering overflow-hidden bg-slate-100"),
        )
        full_url = frame.get("image_url") or frame.get("thumbnail_url")
        image_url = full_url
        if image_url:
            image_view = self._image_view(image_url, "ภาพประวัติ CCTV")
            image_view.attrs["data-full-image-url"] = full_url or ""
            figure <= image_view
        self._update_history_navigation()

    def _update_history_navigation(self):
        total = len(self._history_frames)
        previous = document.getElementById("visual_feed_history_previous")
        following = document.getElementById("visual_feed_history_next")
        counter = document.getElementById("visual_feed_history_counter")
        has_previous = total > 0 and self._history_index > 0
        has_next = total > 0 and self._history_index < total - 1
        if previous:
            (
                previous.classList.remove("hidden")
                if has_previous
                else previous.classList.add("hidden")
            )
        if following:
            (
                following.classList.remove("hidden")
                if has_next
                else following.classList.add("hidden")
            )
        if counter:
            counter.textContent = (
                f"ภาพที่ {self._history_index + 1} จาก {total}" if total else ""
            )

    def _on_history_previous(self, _event=None):
        if self._history_index > 0:
            self._history_index -= 1
            self._render_history_frame()

    def _on_history_next(self, _event=None):
        if self._history_index < len(self._history_frames) - 1:
            self._history_index += 1
            self._render_history_frame()

    def _on_history_slider_input(self, event=None):
        try:
            slider = (
                event.target
                if event
                else document.getElementById("visual_feed_history_slider")
            )
            if slider and self._history_frames:
                val = int(slider.value)
                if 0 <= val < len(self._history_frames):
                    self._history_index = val
                    self._render_history_frame()
        except Exception:
            pass

    def _on_modal_chip_click(self, chip_val):
        if not self._history_frames:
            return
        if chip_val == "live":
            self._history_index = len(self._history_frames) - 1
        else:
            try:
                target_hour = int(chip_val)
                best_idx = 0
                best_diff = 999
                for i, frame in enumerate(self._history_frames):
                    captured = frame.get("captured_at")
                    h = _get_bangkok_hour(captured)
                    diff = abs(h - target_hour)
                    if diff < best_diff:
                        best_diff = diff
                        best_idx = i
                self._history_index = best_idx
            except Exception:
                pass
        self._render_history_frame()

    def _on_history_touch_start(self, event):
        try:
            self._touch_start_x = float(event.touches[0].clientX)
        except Exception:
            self._touch_start_x = None

    def _on_history_touch_end(self, event):
        if self._touch_start_x is None:
            return
        try:
            end_x = float(event.changedTouches[0].clientX)
        except Exception:
            self._touch_start_x = None
            return
        distance = end_x - self._touch_start_x
        self._touch_start_x = None
        if abs(distance) < 48:
            return
        if distance > 0:
            self._on_history_previous()
        else:
            self._on_history_next()

    def _on_history_touch_cancel(self, _event=None):
        self._touch_start_x = None

    def _set_history_message(self, message):
        target = document.getElementById("visual_feed_history_status")
        if target:
            target.textContent = _text(message, "")

    def _set_history_load_state(self, state):
        for element_id in (
            "visual_feed_history_date",
            "visual_feed_history_frames",
        ):
            element = document.getElementById(element_id)
            if element:
                element.attrs["data-state"] = state
        frames = document.getElementById("visual_feed_history_frames")
        if frames:
            frames.attrs["aria-busy"] = "true" if state == "loading" else "false"

    def _show_latest_section(self):
        latest = document.getElementById("visual_feed_detail_latest")
        controls = document.getElementById("visual_feed_history_controls")
        frames = document.getElementById("visual_feed_history_frames")
        if latest:
            latest.classList.add("hidden")
        if controls:
            controls.classList.add("hidden")
        if frames:
            frames.classList.remove("hidden")
        self._history_index = -1
        self._update_history_navigation()

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
        if heading:
            heading.textContent = title
        if badge:
            badge.classList.remove("cctv-status--online", "cctv-status--unavailable")
            badge.classList.add("cctv-status", _availability_status_class(availability))
            if availability == "online":
                badge.html = """<span class="w-1.5 h-1.5 rounded-full bg-white"></span><span>ออนไลน์</span>"""
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
                    "flex aspect-video items-center justify-center rounded-lg bg-slate-100 text-xs text-slate-500",
                    "ไม่มีภาพล่าสุด",
                )
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
                <div class="rounded-2xl border border-blue-200/80 bg-blue-50/50 p-3.5 flex flex-col sm:flex-row sm:items-center justify-between gap-2.5 shadow-2xs">
                    <div class="flex items-center gap-3 min-w-0">
                        <i class="ph ph-waves text-2xl text-blue-600 shrink-0" aria-hidden="true"></i>
                        <div class="min-w-0">
                            <div class="font-bold text-xs sm:text-sm text-blue-950 truncate">สถานีวัดน้ำที่ตั้งเดียวกัน: {st_name}</div>
                            <div class="text-[11px] text-blue-700 font-medium">รหัสสถานี #{st_code}{wl_str}</div>
                        </div>
                    </div>
                    <button type="button" onclick="if(window.focus_water_station_from_modal)window.focus_water_station_from_modal('{st_code}','{st_src}')"
                        class="btn btn-sm btn-primary gap-1.5 text-white shrink-0 font-medium rounded-xl shadow-xs px-3.5">
                        <i class="ph ph-waves"></i> ดูระดับน้ำ
                    </button>
                </div>
                """
                station_link.classList.remove("hidden")
            else:
                station_link.html = ""
                station_link.classList.add("hidden")

    def _refresh_open_detail(self):
        if self._modal_open and self._active_feed:
            key = self._feed_key(self._active_feed)
            for feed in self.latest_feeds:
                if self._feed_key(feed) == key:
                    self._active_feed = feed
                    self._populate_detail(feed)
                    return
            self._populate_detail(self._active_feed)

    def _refresh_open_latest_detail(self):
        self._refresh_open_detail()

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


def _get_bangkok_hour(value):
    if value is None:
        return 12
    if not isinstance(value, datetime.datetime):
        value = _parse_utc(value)
    if value is None:
        return 12
    return value.astimezone(BANGKOK_TZ).hour
