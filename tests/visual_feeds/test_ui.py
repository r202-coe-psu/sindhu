import asyncio
import datetime
import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


class _DummyDocument:
    hidden = False

    def __contains__(self, _key):
        return False

    def getElementById(self, _key):
        return None

    def bind(self, *_args):
        return None


class _DummyWindow:
    document = _DummyDocument()

    def bind(self, *_args):
        return None

    def setTimeout(self, *_args):
        return 1

    def clearTimeout(self, *_args):
        return None


def _load_ui_module():
    browser = types.ModuleType("browser")
    browser.aio = types.SimpleNamespace()
    browser.document = _DummyDocument()
    browser.window = _DummyWindow()
    with patch.dict("sys.modules", {"browser": browser}):
        path = (
            Path(__file__).parents[2]
            / "sindhu"
            / "web"
            / "static"
            / "brython"
            / "visual_feeds"
            / "__init__.py"
        )
        # Load as a package so its relative imports (labels, map_popup) resolve.
        spec = importlib.util.spec_from_file_location(
            "visual_feeds_ui", path, submodule_search_locations=[str(path.parent)]
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module


def _load_map_module(browser=None):
    map_path = (
        Path(__file__).parents[2]
        / "sindhu"
        / "web"
        / "static"
        / "brython"
        / "maps"
        / "map.py"
    )
    brython_path = str(map_path.parents[1])
    if browser is None:
        browser = types.ModuleType("browser")
        browser.alert = lambda *_args: None
        browser.window = _DummyWindow()
        browser.ajax = types.SimpleNamespace()
        browser.document = _DummyDocument()
        browser.aio = types.SimpleNamespace()

    sys.path.insert(0, brython_path)
    try:
        with patch.dict("sys.modules", {"browser": browser}):
            spec = importlib.util.spec_from_file_location("maps_map", map_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
    finally:
        sys.path.remove(brython_path)


ui = _load_ui_module()


class VisualFeedUiHelperTests(unittest.TestCase):
    def test_resolves_only_configured_dwr_snapshot_paths(self):
        api_url = "https://api.example.test"
        path = "/v1/visual-feeds/dwr/camera-1/snapshot?v=123"

        self.assertEqual(
            ui._resolve_image_url(path, api_url),
            f"{api_url}{path}",
        )
        self.assertIsNone(ui._resolve_image_url("//attacker.test/image.jpg", api_url))
        self.assertIsNone(ui._resolve_image_url("/provider/image.jpg", api_url))
        self.assertIsNone(ui._resolve_image_url("javascript:alert(1)", api_url))
        self.assertEqual(
            ui._resolve_image_url("https://images.example.test/camera.jpg", api_url),
            "https://images.example.test/camera.jpg",
        )

    def test_versions_mutable_image_with_capture_time_without_duplicate_v(self):
        captured = "2026-08-27T10:00:00+07:00"
        expected_suffix = str(
            int(datetime.datetime.fromisoformat(captured).timestamp())
        )

        self.assertEqual(
            ui._version_image_url("https://images.example.test/camera.jpg", captured),
            f"https://images.example.test/camera.jpg?v={expected_suffix}",
        )
        self.assertEqual(
            ui._version_image_url(
                "https://images.example.test/camera.jpg?v=42", captured
            ),
            "https://images.example.test/camera.jpg?v=42",
        )

    def test_history_date_is_valid_up_to_bangkok_today_with_no_fixed_lookback(self):
        before_midnight = datetime.datetime(
            2026, 9, 2, 16, 59, tzinfo=datetime.timezone.utc
        )
        at_midnight = datetime.datetime(2026, 9, 2, 17, 0, tzinfo=datetime.timezone.utc)

        self.assertEqual(ui._bangkok_today(before_midnight).isoformat(), "2026-09-02")
        self.assertEqual(ui._bangkok_today(at_midnight).isoformat(), "2026-09-03")
        # How far back history goes is the provider's decision (see available_dates).
        self.assertIsNotNone(ui._valid_history_date("2026-09-03", at_midnight))
        self.assertIsNotNone(ui._valid_history_date("2026-08-01", at_midnight))
        self.assertIsNone(ui._valid_history_date("2026-09-03", before_midnight))
        self.assertIsNone(ui._valid_history_date("2026-09-04", at_midnight))

    def test_short_date_label_adds_the_thai_year_only_outside_this_year(self):
        today = datetime.date(2026, 10, 29)

        self.assertEqual(
            ui.short_date_label(datetime.date(2026, 10, 20), today), "20 ต.ค."
        )
        self.assertEqual(
            ui.short_date_label(datetime.date(2025, 11, 20), today), "20 พ.ย. 68"
        )

    def test_coverage_label_is_thai_and_keeps_unknown_groups(self):
        self.assertEqual(ui.coverage_label("kho_hong"), "คอหงส์")
        self.assertEqual(ui.coverage_label("new_area"), "new_area")
        self.assertEqual(ui.coverage_label(None), "—")

    def test_stopped_history_names_its_last_day(self):
        monitor = ui.VisualFeedMonitor("https://api.example.test")
        monitor._history_range = (
            "2024-09-20T08:00:20Z",
            "2025-11-20T13:00:05Z",
            True,
        )

        self.assertTrue(monitor._history_is_stale())
        self.assertIn("20 พ.ย. 68", monitor._stale_history_message())

    def test_stopped_history_shows_the_latest_image_however_old(self):
        monitor = ui.VisualFeedMonitor("https://api.example.test")
        feed = {"source": ui.HATYAI_SOURCE, "upstream_id": "57"}
        monitor._active_feed = feed
        monitor._active_date = ui._bangkok_today().isoformat()
        monitor._history_available_dates = ["2025-11-19", "2025-11-20"]
        monitor._history_range = (None, "2025-11-20T13:00:05Z", True)
        rendered, messages = [], []
        monitor._render_realtime_frame = rendered.append
        monitor._set_history_message = messages.append
        monitor._set_history_load_state = lambda _state: None

        monitor._show_history_day()

        self.assertEqual(rendered, [feed])
        self.assertEqual(len(messages), 1)
        self.assertIn("หยุดอัปเดตตั้งแต่ 20 พ.ย. 68", messages[0])

    def test_arrows_cannot_step_into_days_of_a_history_that_stopped(self):
        monitor = ui.VisualFeedMonitor("https://api.example.test")
        monitor._mode = "history"
        monitor._active_date = ui._bangkok_today().isoformat()
        monitor._history_available_dates = ["2025-11-19", "2025-11-20"]
        monitor._history_range = (None, "2025-11-20T13:00:05Z", True)

        self.assertIsNone(monitor._adjacent_history_date(-1))

        monitor._history_range = (None, "2025-11-20T13:00:05Z", False)
        self.assertEqual(monitor._adjacent_history_date(-1), "2025-11-20")

    def test_history_timeout_keeps_showing_the_latest_image(self):
        monitor = ui.VisualFeedMonitor("https://api.example.test")
        feed = {"source": ui.HATYAI_SOURCE, "upstream_id": "9"}
        monitor._mode = "history"
        monitor._modal_open = True
        monitor._active_feed = feed
        monitor._active_date = "2026-10-29"
        shown, notices = [], []
        monitor._show_latest_snapshot_for_date = (
            lambda selected, day, message: shown.append((day, message)) or True
        )
        monitor._render_history_notice = lambda message: notices.append(message)
        monitor._set_history_load_state = lambda _state: None

        monitor._on_history_timeout(feed, monitor._history_generation)

        self.assertEqual(shown, [("2026-10-29", ui.HISTORY_LATEST_FALLBACK_MESSAGE)])
        self.assertEqual(notices, [])

    def test_filter_skips_non_objects_and_caps_at_max_feeds(self):
        feeds = ["not-a-feed"]
        feeds.extend(
            {"media_type": "cctv", "upstream_id": str(index)}
            for index in range(ui.MAX_CCTV_FEEDS + 5)
        )

        result = ui._filter_cctv_feeds(feeds)

        self.assertEqual(len(result), ui.MAX_CCTV_FEEDS)
        self.assertTrue(all(feed["media_type"] == "cctv" for feed in result))
        self.assertEqual(result[0]["upstream_id"], "0")
        self.assertEqual(result[-1]["upstream_id"], str(ui.MAX_CCTV_FEEDS - 1))

    def test_camera_visibility_does_not_depend_on_status_or_image_availability(self):
        for status in ("online", "stale", "degraded", "offline", "unknown"):
            self.assertTrue(
                ui._is_displayable_camera(
                    {"media_type": "cctv", "availability": status, "image_url": None}
                )
            )
        self.assertFalse(ui._is_displayable_camera("not-a-feed"))

    def test_image_freshness_uses_only_the_api_field_and_fails_closed(self):
        self.assertEqual(ui._image_freshness({"image_freshness": "fresh"}), "fresh")
        self.assertEqual(ui._image_freshness({"image_freshness": "stale"}), "stale")
        self.assertEqual(ui._image_freshness({"availability": "online"}), "stale")
        self.assertEqual(ui._image_freshness({"image_freshness": "unknown"}), "stale")
        self.assertEqual(ui._image_freshness_label("fresh"), "ออนไลน์")
        self.assertEqual(
            ui._image_freshness_label("stale"),
            "ขาดการเชื่อมต่อ",
        )
        self.assertEqual(
            ui._image_freshness_status_class("fresh"), "cctv-status--fresh"
        )
        self.assertEqual(
            ui._image_freshness_status_class("stale"), "cctv-status--stale"
        )

    def test_card_and_detail_badges_use_the_same_api_freshness(self):
        class FakeClassList:
            def __init__(self):
                self.classes = set()

            def add(self, *classes):
                self.classes.update(classes)

            def remove(self, *classes):
                self.classes.difference_update(classes)

        class FakeElement:
            def __init__(self, tag, class_name=None, text_value=None):
                self.tag = tag
                self.className = class_name or ""
                self.textContent = text_value or ""
                self.attrs = {}
                self.children = []
                self.classList = FakeClassList()

            def __le__(self, child):
                self.children.append(child)
                return child

            def bind(self, *_args):
                return None

        def factory(tag, class_name=None, text_value=None):
            return FakeElement(tag, class_name, text_value)

        feed = {
            "source": "dwr",
            "upstream_id": "camera-1",
            "media_type": "cctv",
            "availability": "offline",
            "image_freshness": "fresh",
            "title_th": "กล้องทดสอบ",
            "coverage_group": "หาดใหญ่",
            "image_url": None,
            "captured_at": "2026-09-26T08:47:00Z",
            "history_supported": False,
        }
        monitor = ui.VisualFeedMonitor("https://api.example.test")
        monitor.find_matching_station = lambda _feed: None

        def find_badge(root):
            if "cctv-status--fresh" in root.className:
                return root
            for child in root.children:
                badge = find_badge(child)
                if badge:
                    return badge
            return None

        with patch.object(ui, "_el", side_effect=factory):
            card = monitor._build_card(feed)
        card_badge = find_badge(card)
        self.assertEqual(card.attrs["data-image-freshness"], "fresh")
        self.assertIsNotNone(card_badge)
        self.assertEqual(card_badge.textContent, "ออนไลน์")

        heading, badge, meta, latest = [FakeElement("div") for _ in range(4)]
        elements = {
            "visual_feed_detail_title": heading,
            "visual_feed_detail_badge": badge,
            "visual_feed_detail_meta": meta,
            "visual_feed_detail_latest_image": latest,
        }
        with (
            patch.object(
                ui, "document", types.SimpleNamespace(getElementById=elements.get)
            ),
            patch.object(ui, "_el", side_effect=factory),
        ):
            monitor._populate_detail(feed)

        self.assertIn("cctv-status--fresh", badge.classList.classes)
        self.assertEqual(badge.textContent, card_badge.textContent)
        self.assertNotIn("ภาพล่าสุด", meta.textContent)
        self.assertNotIn("15:47", meta.textContent)

    def test_history_empty_and_failure_messages_name_selected_date_and_outage(self):
        self.assertEqual(
            ui._history_empty_message("2026-09-25"),
            "ไม่มีภาพวันที่ 25/09/2026 ในข้อมูลย้อนหลังที่ต้นทางส่งมา",
        )
        self.assertIn(
            "ไม่พร้อม",
            ui._history_request_error_message(503, "2026-09-25"),
        )
        self.assertIn(
            "ยืนยันภาพย้อนหลัง",
            ui._history_request_error_message(None, "2026-09-25"),
        )

    def test_history_failure_falls_back_to_latest_image_only_for_its_date(self):
        class Response:
            status = 503
            data = ""

        response = Response()

        async def get(_url, **_kwargs):
            return response

        today = ui._bangkok_today().isoformat()
        yesterday = (ui._bangkok_today() - datetime.timedelta(days=1)).isoformat()
        feed = {
            "source": ui.HATYAI_SOURCE,
            "upstream_id": "camera-1",
            "image_url": "https://hatyaicityclimate.org/latest.jpg",
            "captured_at": f"{today}T17:39:00+07:00",
        }

        for selected_date, status, data, should_fallback, expected_state in (
            (today, 503, "", True, "error"),
            (today, 200, '{"frames": []}', True, "empty"),
            (yesterday, 503, "", False, "error"),
        ):
            response.status = status
            response.data = data
            monitor = ui.VisualFeedMonitor("https://api.example.test")
            monitor._mode = "history"
            monitor._modal_open = True
            monitor._active_feed = feed
            monitor._active_date = selected_date
            monitor._history_generation = 1
            rendered = []
            messages = []
            states = []
            monitor._render_realtime_frame = rendered.append
            monitor._set_history_message = messages.append
            monitor._set_history_load_state = states.append

            with (
                patch.object(monitor, "_should_fetch_history", return_value=True),
                patch.object(ui.aio, "get", get, create=True),
            ):
                asyncio.run(monitor._fetch_history(feed, 1))

            self.assertEqual(bool(rendered), should_fallback)
            if should_fallback:
                self.assertEqual(rendered, [feed])
                self.assertEqual(messages[-1], ui.HISTORY_LATEST_FALLBACK_MESSAGE)
            else:
                self.assertIn("โหลดประวัติวันที่", messages[-1])
            self.assertEqual(states[-1], expected_state)

    def test_history_frames_are_sorted_from_oldest_to_newest(self):
        monitor = ui.VisualFeedMonitor("https://api.example.test")
        frames = monitor._normalize_history_frames(
            [
                {
                    "captured_at": "2026-09-14T09:00:00Z",
                    "image_url": "https://images.test/new.jpg",
                },
                {
                    "captured_at": "2026-09-14T08:00:00Z",
                    "image_url": "https://images.test/old.jpg",
                },
            ]
        )

        self.assertEqual(
            [frame["image_url"] for frame in frames],
            ["https://images.test/old.jpg", "https://images.test/new.jpg"],
        )

    def test_history_navigation_controls_stay_visible_and_disable_at_bounds(self):
        class FakeClassList:
            def __init__(self, *classes):
                self.classes = set(classes)

            def add(self, class_name):
                self.classes.add(class_name)

            def remove(self, class_name):
                self.classes.discard(class_name)

        class FakeElement:
            def __init__(self, *classes):
                self.classList = FakeClassList(*classes)
                self.attrs = {}
                self.disabled = False
                self.textContent = ""

        previous = FakeElement("hidden")
        following = FakeElement("hidden")
        counter = FakeElement()
        elements = {
            "visual_feed_history_previous": previous,
            "visual_feed_history_next": following,
            "visual_feed_history_counter": counter,
        }
        fake_document = types.SimpleNamespace(getElementById=elements.get)
        monitor = ui.VisualFeedMonitor("https://api.example.test")
        monitor._mode = "history"
        monitor._history_frames = [{"id": 1}, {"id": 2}]
        monitor._history_index = 1

        with patch.object(ui, "document", fake_document):
            monitor._update_history_navigation()
            self.assertNotIn("hidden", previous.classList.classes)
            self.assertNotIn("hidden", following.classList.classes)
            self.assertFalse(previous.disabled)
            self.assertTrue(following.disabled)
            self.assertEqual(counter.textContent, "ภาพที่ 2 จาก 2")

            monitor._history_index = 0
            monitor._update_history_navigation()
            self.assertTrue(previous.disabled)
            self.assertFalse(following.disabled)

            monitor._clear_history_frames()
            self.assertTrue(previous.disabled)
            self.assertTrue(following.disabled)
            self.assertEqual(counter.textContent, "")

    def test_history_arrows_cross_loaded_days_without_refetching(self):
        monitor = ui.VisualFeedMonitor("https://api.example.test")
        feed = {
            "source": "hatyai_city_climate",
            "upstream_id": "3",
            "history_supported": True,
        }
        monitor._mode = "history"
        monitor._active_feed = feed
        monitor._history_all_frames = monitor._normalize_history_frames(
            [
                # 23:30 and 00:30 Bangkok fall on different days.
                {
                    "captured_at": "2026-09-21T16:30:00Z",
                    "image_url": "https://i.test/a.jpg",
                },
                {
                    "captured_at": "2026-09-21T17:30:00Z",
                    "image_url": "https://i.test/b.jpg",
                },
                {
                    "captured_at": "2026-09-21T18:30:00Z",
                    "image_url": "https://i.test/c.jpg",
                },
            ]
        )
        monitor._history_loaded_key = monitor._feed_key(feed)
        monitor._history_available_dates = ["2026-09-21", "2026-09-22"]
        monitor._active_date = "2026-09-21"
        shown = []
        monitor._render_7days_rail = lambda: None
        monitor._render_history_frame = lambda: shown.append(
            monitor._history_frames[monitor._history_index]["image_url"]
        )
        monitor._set_history_message = lambda _message: None
        monitor._set_history_load_state = lambda _state: None

        with (
            patch.object(
                ui,
                "document",
                types.SimpleNamespace(
                    getElementById=lambda key: (
                        types.SimpleNamespace(html="")
                        if key == "visual_feed_history_frame"
                        else None
                    )
                ),
            ),
            patch.object(ui, "_valid_history_date", datetime.date.fromisoformat),
            patch.object(
                ui.aio, "run", side_effect=AssertionError("refetched"), create=True
            ),
        ):
            monitor._show_history_day()
            monitor._on_history_next()
            self.assertEqual(monitor._active_date, "2026-09-22")
            monitor._on_history_next()
            monitor._on_history_previous()
            monitor._on_history_previous()

        self.assertEqual(
            shown,
            [
                "https://i.test/a.jpg",
                "https://i.test/b.jpg",
                "https://i.test/c.jpg",
                "https://i.test/b.jpg",
                "https://i.test/a.jpg",
            ],
        )
        self.assertEqual(monitor._active_date, "2026-09-21")

    def test_open_detail_enters_today_history_when_supported(self):
        monitor = ui.VisualFeedMonitor("https://api.example.test")
        opened = []
        monitor._open_history = lambda feed, event=None: opened.append((feed, event))
        feed = {
            "source": ui.HATYAI_SOURCE,
            "history_supported": True,
            "upstream_id": "camera-1",
        }
        event = object()

        monitor._open_detail(feed, event)

        self.assertEqual(opened, [(feed, event)])

    def test_history_support_uses_api_capability_flag(self):
        self.assertTrue(ui._supports_history({"history_supported": True}))
        self.assertFalse(
            ui._supports_history(
                {"source": ui.HATYAI_SOURCE, "history_supported": False}
            )
        )

    def test_history_range_message_states_the_providers_real_coverage(self):
        message = ui._history_range_message(
            "2026-10-16T13:00:07Z", "2026-10-20T16:00:43Z", False
        )

        self.assertEqual(message, "ข้อมูลย้อนหลังจากต้นทาง 16/10/2026 – 20/10/2026")

    def test_history_range_message_flags_a_camera_whose_history_stopped(self):
        message = ui._history_range_message(
            "2026-09-21T15:00:58Z", "2026-09-26T17:00:22Z", True
        )

        self.assertIn("21/09/2026 – 27/09/2026", message)
        self.assertIn("หยุดอัปเดต", message)

    def test_history_range_message_is_empty_without_a_usable_range(self):
        self.assertEqual(ui._history_range_message(None, None, False), "")
        self.assertEqual(
            ui._history_range_message("nope", "2026-10-20T00:00:00Z", True), ""
        )

    def _open_detail_with_fake_dom(self, feed):
        class FakeClassList:
            def __init__(self, *classes):
                self.classes = set(classes)

            def add(self, class_name):
                self.classes.add(class_name)

            def remove(self, class_name):
                self.classes.discard(class_name)

        class FakeElement:
            def __init__(self, *classes):
                self.classList = FakeClassList(*classes)

        controls = FakeElement("hidden")
        frames = FakeElement("hidden")
        elements = {
            "visual_feed_history_controls": controls,
            "visual_feed_history_frames": frames,
        }
        monitor = ui.VisualFeedMonitor("https://api.example.test")
        monitor._populate_detail = lambda _feed: None
        monitor._configure_history_date = lambda target_date=None: None
        monitor._render_realtime_frame = lambda _feed: None
        monitor._open_modal = lambda: None

        def open_history(opened_feed, event=None, target_date=None):
            monitor._active_feed = opened_feed
            monitor._show_history_section()

        monitor._open_history = open_history

        with patch.object(
            ui, "document", types.SimpleNamespace(getElementById=elements.get)
        ):
            monitor._open_detail(feed)
        return controls, frames

    def test_realtime_only_detail_shows_the_image_without_day_controls(self):
        controls, frames = self._open_detail_with_fake_dom(
            {"source": "dwr", "history_supported": False, "upstream_id": "camera-1"}
        )

        self.assertIn("hidden", controls.classList.classes)
        self.assertNotIn("hidden", frames.classList.classes)

    def test_history_detail_shows_day_controls(self):
        controls, frames = self._open_detail_with_fake_dom(
            {
                "source": ui.HATYAI_SOURCE,
                "history_supported": True,
                "upstream_id": "camera-1",
            }
        )

        self.assertNotIn("hidden", controls.classList.classes)
        self.assertNotIn("hidden", frames.classList.classes)

    def test_realtime_camera_action_is_labeled_as_latest_not_today_history(self):
        self.assertEqual(
            ui._detail_action_label({"source": "dwr", "history_supported": False}),
            "ดูภาพล่าสุด",
        )
        self.assertEqual(
            ui._detail_action_label(
                {"source": ui.HATYAI_SOURCE, "history_supported": True}
            ),
            "ดูภาพวันนี้",
        )

    def test_map_marker_opens_the_same_detail_view_as_a_camera_card(self):
        monitor = ui.VisualFeedMonitor("https://api.example.test")
        opened = []
        feed = {"source": ui.HATYAI_SOURCE, "upstream_id": "camera-1"}
        monitor._open_detail = lambda selected: opened.append(selected)

        monitor._on_marker_click(feed)

        self.assertEqual(opened, [feed])

    def _show_on_map(self, feed, map_shows_pin=True):
        monitor = ui.VisualFeedMonitor("https://api.example.test")
        popups, opened = [], []

        class MockMap:
            def show_visual_feeds(self, feeds, on_feed_click=None):
                pass

            def open_visual_feed_popup(self, source, upstream_id, build_content):
                popups.append((source, upstream_id, build_content()))
                return map_shows_pin

        monitor.map_owner = MockMap()
        monitor._map_popup = lambda selected: "popup"
        monitor._open_detail = lambda selected, event=None: opened.append(selected)
        monitor._show_on_map(feed)
        return popups, opened

    def test_latest_image_button_opens_a_popup_on_the_camera_pin(self):
        feed = {
            "source": ui.HATYAI_SOURCE,
            "upstream_id": "1",
            "coordinates": {"type": "Point", "coordinates": [100.4, 7.0]},
        }

        popups, opened = self._show_on_map(feed)

        self.assertEqual(popups, [(ui.HATYAI_SOURCE, "1", "popup")])
        self.assertEqual(opened, [])

    def test_latest_image_button_falls_back_to_viewer_without_a_pin(self):
        feed = {"source": ui.HATYAI_SOURCE, "upstream_id": "1", "coordinates": None}

        popups, opened = self._show_on_map(feed)

        self.assertEqual(popups, [])
        self.assertEqual(opened, [feed])

    def test_latest_image_button_falls_back_when_the_map_hides_the_pin(self):
        feed = {
            "source": ui.HATYAI_SOURCE,
            "upstream_id": "1",
            "coordinates": {"type": "Point", "coordinates": [100.4, 7.0]},
        }

        _popups, opened = self._show_on_map(feed, map_shows_pin=False)

        self.assertEqual(opened, [feed])

    def test_history_pointer_swipe_moves_one_frame_in_the_expected_direction(self):
        monitor = ui.VisualFeedMonitor("https://api.example.test")
        monitor._history_frames = [{"id": 1}, {"id": 2}]
        monitor._history_index = 1
        monitor._render_history_frame = lambda: None

        def pointer(x):
            return types.SimpleNamespace(
                clientX=x,
                pointerId=1,
                pointerType="mouse",
                button=0,
                isPrimary=True,
            )

        monitor._on_history_pointer_start(pointer(100))
        monitor._on_history_pointer_end(pointer(180))
        self.assertEqual(monitor._history_index, 0)

        monitor._on_history_pointer_start(pointer(180))
        monitor._on_history_pointer_end(pointer(100))
        self.assertEqual(monitor._history_index, 1)

    def test_history_pointer_swipe_ignores_clicks_and_non_primary_pointers(self):
        monitor = ui.VisualFeedMonitor("https://api.example.test")
        monitor._history_frames = [{"id": 1}, {"id": 2}]
        monitor._history_index = 1
        monitor._render_history_frame = lambda: None

        def pointer(x, *, button=0, is_primary=True):
            return types.SimpleNamespace(
                clientX=x,
                pointerId=1,
                pointerType="mouse",
                button=button,
                isPrimary=is_primary,
            )

        monitor._on_history_pointer_start(pointer(100))
        monitor._on_history_pointer_end(pointer(130))
        self.assertEqual(monitor._history_index, 1)

        monitor._on_history_pointer_start(pointer(100, button=2))
        monitor._on_history_pointer_end(pointer(180, button=2))
        monitor._on_history_pointer_start(pointer(100, is_primary=False))
        monitor._on_history_pointer_end(pointer(180, is_primary=False))
        self.assertEqual(monitor._history_index, 1)

    def test_history_pointer_swipe_ignores_other_pointer_release(self):
        monitor = ui.VisualFeedMonitor("https://api.example.test")
        monitor._history_frames = [{"id": 1}, {"id": 2}]
        monitor._history_index = 1
        monitor._render_history_frame = lambda: None

        def pointer(x, pointer_id):
            return types.SimpleNamespace(
                clientX=x,
                pointerId=pointer_id,
                pointerType="touch",
                button=0,
                isPrimary=True,
            )

        monitor._on_history_pointer_start(pointer(100, 7))
        monitor._on_history_pointer_end(pointer(180, 8))
        self.assertEqual(monitor._history_index, 1)

        monitor._on_history_pointer_end(pointer(180, 7))
        self.assertEqual(monitor._history_index, 0)

    def test_format_time_normalizes_history_timestamp_string_to_bangkok(self):
        self.assertEqual(
            ui._format_time("2026-09-02T17:00:00Z"),
            "03/09/2026 00:00 น.",
        )

    async def _failed_refresh(self):
        monitor = ui.VisualFeedMonitor("https://api.example.test")
        monitor.running = True
        monitor._visual_panel_active = True
        monitor._mode = "latest"
        monitor._latest_generation = 1

        class Response:
            status = 503

        async def get(_url, **_kwargs):
            return Response()

        with patch.object(ui.aio, "get", get, create=True):
            result = await monitor.refresh()
        return result, monitor

    async def _successful_refresh_request(self):
        monitor = ui.VisualFeedMonitor("https://api.example.test")
        monitor.running = True
        monitor._visual_panel_active = True
        monitor._mode = "latest"
        monitor._latest_generation = 1
        seen = {}

        class Response:
            status = 200
            data = '{"visual_feeds": []}'

        async def get(url, **kwargs):
            seen["url"] = url
            seen["kwargs"] = kwargs
            return Response()

        with patch.object(ui.aio, "get", get, create=True):
            result = await monitor.refresh()
        return result, seen

    def test_failed_latest_attempt_arms_poll_backoff(self):
        result, monitor = __import__("asyncio").run(self._failed_refresh())

        self.assertFalse(result)
        self.assertIsNotNone(monitor._last_latest_fetch)

    def test_latest_request_uses_plain_endpoint_for_brython_aio(self):
        result, seen = __import__("asyncio").run(self._successful_refresh_request())

        self.assertTrue(result)
        self.assertEqual(
            seen,
            {
                "url": "https://api.example.test/v1/visual-feeds",
                "kwargs": {"cache": True},
            },
        )

    def test_has_coordinates_detects_valid_and_invalid_coordinates(self):
        self.assertTrue(
            ui._has_coordinates(
                {"coordinates": {"type": "Point", "coordinates": [100.4, 7.0]}}
            )
        )
        self.assertFalse(ui._has_coordinates({}))
        self.assertFalse(ui._has_coordinates({"coordinates": None}))
        self.assertFalse(
            ui._has_coordinates({"coordinates": {"type": "Point", "coordinates": []}})
        )
        self.assertFalse(
            ui._has_coordinates(
                {"coordinates": {"type": "Point", "coordinates": [None, 7.0]}}
            )
        )

    def test_update_map_markers_delegates_to_map_owner(self):
        monitor = ui.VisualFeedMonitor("https://api.example.test")
        feed_with_coords = {
            "source": "hatyai",
            "upstream_id": "1",
            "media_type": "cctv",
            "availability": "online",
            "image_url": "https://images.example.test/pic.jpg",
            "captured_at": "2026-09-05T07:00:00Z",
            "coordinates": {"type": "Point", "coordinates": [100.4, 7.0]},
        }
        feed_without_coords = {
            "source": "hatyai",
            "upstream_id": "2",
            "media_type": "cctv",
            "availability": "online",
            "image_url": "https://images.example.test/pic2.jpg",
            "coordinates": None,
        }
        unavailable_with_coords = {
            "source": "hatyai",
            "upstream_id": "3",
            "media_type": "cctv",
            "availability": "offline",
            "image_url": "https://images.example.test/offline.jpg",
            "coordinates": {"type": "Point", "coordinates": [100.5, 7.1]},
        }
        monitor.latest_feeds = [feed_with_coords, feed_without_coords]
        monitor.latest_feeds.append(unavailable_with_coords)

        rendered_feeds = []

        class MockMap:
            def show_visual_feeds(self, feeds, on_feed_click=None):
                rendered_feeds.extend(feeds)

        mock_map = MockMap()
        monitor.map_owner = mock_map
        monitor.update_map_markers()

        self.assertEqual([feed["upstream_id"] for feed in rendered_feeds], ["1", "3"])
        self.assertTrue(monitor._markers_initialized)

    def test_map_show_visual_feeds_clears_markers_when_empty(self):
        browser = types.ModuleType("browser")
        browser.alert = lambda *_args: None
        browser.window = _DummyWindow()
        browser.ajax = types.SimpleNamespace()
        browser.document = _DummyDocument()
        browser.aio = types.SimpleNamespace()

        map_module = _load_map_module(browser)
        map_obj = map_module.Map.__new__(map_module.Map)
        map_obj.map = types.SimpleNamespace(remove=lambda: None)
        map_obj.leaflet = True
        map_obj.visual_feeds = [{"id": 1}]
        map_obj.visual_feed_markers_by_id = {"hatyai_1": "marker"}
        rendered_layers = []
        map_obj.set_visual_feed_layer = lambda markers: rendered_layers.append(markers)

        map_obj.show_visual_feeds([])

        self.assertEqual(map_obj.visual_feeds, [])
        self.assertEqual(map_obj.visual_feed_markers_by_id, {})
        self.assertEqual(rendered_layers, [[]])

    def test_map_displays_unknown_camera_without_capture_timestamp(self):
        map_module = _load_map_module()

        class DummyMarker:
            def bindTooltip(self, *_args):
                return self

        class DummyLeaflet:
            @staticmethod
            def divIcon(options):
                return options

            @staticmethod
            def marker(*_args):
                return DummyMarker()

        map_obj = map_module.Map.__new__(map_module.Map)
        map_obj.map = types.SimpleNamespace(remove=lambda: None)
        map_obj.leaflet = DummyLeaflet()
        map_obj.visual_feeds = []
        map_obj.visual_feed_markers_by_id = {}
        map_obj.set_visual_feed_layer = lambda markers: setattr(
            map_obj, "visual_feed_markers", markers
        )

        map_obj.show_visual_feeds(
            [
                {
                    "source": "rid",
                    "upstream_id": "without-time",
                    "availability": "unknown",
                    "coordinates": {"coordinates": [100.4, 7.0]},
                }
            ]
        )

        self.assertEqual(len(map_obj.visual_feed_markers), 1)
        self.assertIn("rid_without-time", map_obj.visual_feed_markers_by_id)

    def test_map_camera_markers_use_api_freshness_even_if_provider_is_offline(self):
        map_module = _load_map_module()

        class DummyMarker:
            def __init__(self, _coords, options):
                self.options = options

            def bindTooltip(self, content, *_args):
                self.tooltip = content
                return self

        class DummyLeaflet:
            @staticmethod
            def divIcon(options):
                return options

            @staticmethod
            def marker(coords, options):
                return DummyMarker(coords, options)

        map_obj = map_module.Map.__new__(map_module.Map)
        map_obj.map = types.SimpleNamespace(remove=lambda: None)
        map_obj.leaflet = DummyLeaflet()
        map_obj.visual_feeds = []
        map_obj.visual_feed_markers_by_id = {}
        map_obj.set_visual_feed_layer = lambda markers: setattr(
            map_obj, "visual_feed_markers", markers
        )
        statuses = (
            ("online", "fresh"),
            ("stale", "stale"),
            ("degraded", "stale"),
            ("offline", "fresh"),
            ("unknown", "stale"),
        )

        map_obj.show_visual_feeds(
            [
                {
                    "source": "dwr",
                    "upstream_id": availability,
                    "availability": availability,
                    "image_freshness": freshness,
                    "captured_at": "2026-09-26T08:47:00Z",
                    "coordinates": {"coordinates": [100.4, 7.0]},
                }
                for availability, freshness in statuses
            ]
        )

        for availability, freshness in statuses:
            marker = map_obj.visual_feed_markers_by_id[f"dwr_{availability}"]
            icon_html = marker.options["icon"]["html"]
            expected_color = "#0284c7" if freshness == "fresh" else "#9ca3af"
            self.assertIn(f'fill="{expected_color}"', icon_html, availability)
            expected_label = "ออนไลน์" if freshness == "fresh" else "ขาดการเชื่อมต่อ"
            self.assertIn(expected_label, marker.tooltip, availability)
            self.assertNotIn("ภาพล่าสุด", marker.tooltip, availability)

    def test_map_marker_does_not_show_latest_capture_time(self):
        map_module = _load_map_module()

        class DummyMarker:
            def __init__(self, _coords, options):
                self.options = options

            def bindTooltip(self, content, *_args):
                self.tooltip = content
                return self

        class DummyLeaflet:
            @staticmethod
            def divIcon(options):
                return options

            @staticmethod
            def marker(coords, options):
                return DummyMarker(coords, options)

        map_obj = map_module.Map.__new__(map_module.Map)
        map_obj.map = types.SimpleNamespace(remove=lambda: None)
        map_obj.leaflet = DummyLeaflet()
        map_obj.visual_feeds = []
        map_obj.visual_feed_markers_by_id = {}
        map_obj.set_visual_feed_layer = lambda markers: setattr(
            map_obj, "visual_feed_markers", markers
        )
        map_obj.show_visual_feeds(
            [
                {
                    "source": "rid",
                    "upstream_id": "STN04",
                    "image_freshness": "fresh",
                    "captured_at": "2026-09-26T08:47:00Z",
                    "coordinates": {"coordinates": [100.4, 7.0]},
                }
            ]
        )

        marker = map_obj.visual_feed_markers_by_id["rid_STN04"]
        self.assertIn("ออนไลน์", marker.tooltip)
        self.assertNotIn("ภาพล่าสุด", marker.tooltip)
        self.assertNotIn("15:47", marker.tooltip)

    def test_hide_unconfirmed_cameras_toggle_filters_by_api_freshness(self):
        monitor = ui.VisualFeedMonitor("https://api.example.test")
        monitor.latest_feeds = [
            {
                "source": "rid",
                "upstream_id": "fresh_unknown_provider",
                "media_type": "cctv",
                "availability": "unknown",
                "image_freshness": "fresh",
                "image_url": "https://images.example.test/unknown.jpg",
                "coordinates": {"type": "Point", "coordinates": [100.4, 7.0]},
            },
            {
                "source": "rid",
                "upstream_id": "stale_online_provider",
                "media_type": "cctv",
                "availability": "online",
                "image_freshness": "stale",
                "image_url": "https://images.example.test/online.jpg",
                "coordinates": {"type": "Point", "coordinates": [100.5, 7.1]},
            },
            {
                "source": "rid",
                "upstream_id": "stale_offline_provider",
                "media_type": "cctv",
                "availability": "offline",
                "image_freshness": "stale",
                "image_url": "https://images.example.test/offline.jpg",
                "coordinates": {"type": "Point", "coordinates": [100.6, 7.2]},
            },
        ]

        class MockMap:
            def __init__(self):
                self.rendered_feeds = []

            def show_visual_feeds(self, feeds, on_feed_click=None):
                self.rendered_feeds = feeds

        mock_map = MockMap()
        monitor.map_owner = mock_map
        hide_toggle = types.SimpleNamespace(checked=False)

        def get_element(element_id):
            if element_id == "hide_unknown_cctv_markers":
                return hide_toggle
            return None

        with patch.object(ui.document, "getElementById", side_effect=get_element):
            monitor.update_map_markers()
            self.assertEqual(
                [feed["upstream_id"] for feed in mock_map.rendered_feeds],
                [
                    "fresh_unknown_provider",
                    "stale_online_provider",
                    "stale_offline_provider",
                ],
            )

            hide_toggle.checked = True
            monitor.update_map_markers()

        self.assertEqual(
            [feed["upstream_id"] for feed in mock_map.rendered_feeds],
            ["fresh_unknown_provider"],
        )

    def test_unconfirmed_camera_filter_is_disabled_when_cctv_layer_is_off(self):
        monitor = ui.VisualFeedMonitor("https://api.example.test")
        camera_toggle = types.SimpleNamespace(checked=False)
        unconfirmed_toggle = types.SimpleNamespace(checked=True, disabled=False)
        state_classes = set()
        state = types.SimpleNamespace(
            textContent="",
            classList=types.SimpleNamespace(
                add=state_classes.add,
                remove=state_classes.discard,
            ),
        )

        def get_element(element_id):
            if element_id == "toggle_cctv_markers":
                return camera_toggle
            if element_id == "hide_unknown_cctv_markers":
                return unconfirmed_toggle
            if element_id == "cctv_visibility_state":
                return state
            return None

        with patch.object(ui.document, "getElementById", side_effect=get_element):
            monitor._sync_unconfirmed_camera_filter()
            self.assertTrue(unconfirmed_toggle.disabled)
            self.assertEqual(state.textContent, "ซ่อนบนแผนที่")
            self.assertIn("cctv-map-state--hidden", state_classes)

            camera_toggle.checked = True
            monitor._sync_unconfirmed_camera_filter()

        self.assertFalse(unconfirmed_toggle.disabled)
        self.assertEqual(state.textContent, "แสดงบนแผนที่")
        self.assertIn("cctv-map-state--visible", state_classes)


class _PopupMarker:
    def __init__(self):
        self.popup = None
        self.opened = False
        self._on_close = None

    def bindPopup(self, content, _options):
        self.popup = content
        return self

    def unbindPopup(self):
        self.popup = None

    def once(self, event, handler):
        if event == "popupclose":
            self._on_close = handler

    def openPopup(self):
        self.opened = True

    def getLatLng(self):
        return (7.0, 100.4)

    def close_popup(self):
        if self.opened:
            self.opened = False
            handler, self._on_close = self._on_close, None
            if handler:
                handler(None)


class _PopupLayer:
    def __init__(self):
        self.markers = []

    def addLayer(self, marker):
        self.markers.append(marker)

    def addTo(self, leaflet_map):
        leaflet_map.layers.append(self)


class _PopupLeafletMap:
    def __init__(self):
        self.layers = []

    def remove(self):
        self.layers = []

    def hasLayer(self, layer):
        return layer in self.layers

    def removeLayer(self, layer):
        # Leaflet closes a marker's popup when its layer leaves the map.
        self.layers.remove(layer)
        for marker in layer.markers:
            marker.close_popup()

    def getContainer(self):
        rect = types.SimpleNamespace(top=0, bottom=400)
        return types.SimpleNamespace(getBoundingClientRect=lambda: rect)

    def getZoom(self):
        return 17

    def getCenter(self):
        return types.SimpleNamespace(equals=lambda _latlng: True)


class MapCameraPopupTests(unittest.TestCase):
    def setUp(self):
        browser = types.ModuleType("browser")
        browser.alert = lambda *_args: None
        browser.window = types.SimpleNamespace(innerHeight=800)
        browser.ajax = types.SimpleNamespace()
        self.map_module = map_module = _load_map_module(browser)
        self.map = map_module.Map.__new__(map_module.Map)
        self.map.map = _PopupLeafletMap()
        self.map.leaflet = types.SimpleNamespace(layerGroup=_PopupLayer)
        self.map.visual_feed_layer = None
        self.map.visual_feed_layer_visible = True
        self.first = _PopupMarker()
        self._show_markers(self.first)

    def _show_markers(self, marker):
        """What show_visual_feeds does on every poll: new marker objects."""
        self.map.visual_feed_markers_by_id = {"rid_STN04": marker}
        self.map.set_visual_feed_layer([marker])

    def test_popup_follows_the_camera_and_its_latest_data_across_rebuilds(self):
        contents = iter(["popup at 13:00", "popup at 13:02"])
        self.assertTrue(
            self.map.open_visual_feed_popup("rid", "STN04", lambda: next(contents))
        )
        self.assertEqual(self.first.popup, "popup at 13:00")

        rebuilt = _PopupMarker()
        self._show_markers(rebuilt)

        self.assertTrue(rebuilt.opened)
        self.assertEqual(rebuilt.popup, "popup at 13:02")
        self.assertIsNone(self.first.popup)

    def test_popup_the_user_closed_stays_closed_after_a_rebuild(self):
        self.map.open_visual_feed_popup("rid", "STN04", lambda: "popup")
        self.first.close_popup()

        rebuilt = _PopupMarker()
        self._show_markers(rebuilt)

        self.assertFalse(rebuilt.opened)
        self.assertIsNone(self.first.popup)

    def test_clicking_a_pin_that_shows_its_popup_does_not_open_the_viewer(self):
        opened = []
        marker = types.SimpleNamespace(getPopup=lambda: "popup")
        self.map_module._open_unless_popup(marker, "feed", opened.append)
        self.assertEqual(opened, [])

        marker = types.SimpleNamespace(getPopup=lambda: None)
        self.map_module._open_unless_popup(marker, "feed", opened.append)
        self.assertEqual(opened, ["feed"])

    def test_unknown_camera_falls_back_to_the_viewer(self):
        self.assertFalse(
            self.map.open_visual_feed_popup("rid", "NOPE", lambda: "popup")
        )


if __name__ == "__main__":
    unittest.main()
