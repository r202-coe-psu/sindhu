import datetime
import importlib.util
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
        spec = importlib.util.spec_from_file_location("visual_feeds_ui", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module


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

    def test_bangkok_date_window_is_inclusive_at_utc_boundary(self):
        before_midnight = datetime.datetime(
            2026, 9, 2, 16, 59, tzinfo=datetime.timezone.utc
        )
        at_midnight = datetime.datetime(2026, 9, 2, 17, 0, tzinfo=datetime.timezone.utc)

        self.assertEqual(ui._bangkok_today(before_midnight).isoformat(), "2026-09-02")
        self.assertEqual(ui._bangkok_today(at_midnight).isoformat(), "2026-09-03")
        self.assertEqual(
            tuple(value.isoformat() for value in ui._history_date_window(at_midnight)),
            ("2026-08-28", "2026-09-03"),
        )
        self.assertIsNotNone(ui._valid_history_date("2026-08-28", at_midnight))
        self.assertIsNone(ui._valid_history_date("2026-08-27", at_midnight))
        self.assertIsNone(ui._valid_history_date("2026-09-04", at_midnight))

    def test_filter_keeps_cctv_only_and_caps_at_thirty(self):
        feeds = [{"media_type": "radar", "upstream_id": "radar"}]
        feeds.extend(
            {"media_type": "cctv", "upstream_id": str(index)} for index in range(35)
        )

        result = ui._filter_cctv_feeds(feeds)

        self.assertEqual(len(result), 30)
        self.assertTrue(all(feed["media_type"] == "cctv" for feed in result))
        self.assertEqual(result[0]["upstream_id"], "0")
        self.assertEqual(result[-1]["upstream_id"], "29")

    def test_format_time_normalizes_history_timestamp_string_to_bangkok(self):
        self.assertEqual(
            ui._format_time("2026-09-02T17:00:00Z"),
            "03/09/2026 00:00 น.",
        )

    def test_stale_classification_is_latest_only_and_has_no_future_clock_skew(self):
        now = datetime.datetime(2026, 9, 3, 5, 0, tzinfo=datetime.timezone.utc)
        self.assertTrue(
            ui._is_latest_stale({"captured_at": "2026-09-03T04:29:00Z"}, now)
        )
        self.assertFalse(
            ui._is_latest_stale({"captured_at": "2026-09-03T04:31:00Z"}, now)
        )
        self.assertFalse(
            ui._is_latest_stale({"captured_at": "2026-09-03T06:00:00Z"}, now)
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

    def test_latest_request_keeps_media_query_intact_for_brython_aio(self):
        result, seen = __import__("asyncio").run(self._successful_refresh_request())

        self.assertTrue(result)
        self.assertEqual(
            seen,
            {
                "url": "https://api.example.test/v1/visual-feeds?media_type=cctv",
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
            "image_url": "https://images.example.test/pic.jpg",
            "captured_at": "2026-09-05T07:00:00Z",
            "coordinates": {"type": "Point", "coordinates": [100.4, 7.0]},
        }
        feed_without_coords = {
            "source": "hatyai",
            "upstream_id": "2",
            "media_type": "cctv",
            "image_url": "https://images.example.test/pic2.jpg",
            "coordinates": None,
        }
        monitor.latest_feeds = [feed_with_coords, feed_without_coords]

        rendered_feeds = []

        class MockMap:
            def show_visual_feeds(self, feeds, on_feed_click=None):
                rendered_feeds.extend(feeds)

        mock_map = MockMap()
        monitor.map_owner = mock_map
        monitor.update_map_markers()

        self.assertEqual(len(rendered_feeds), 1)
        self.assertEqual(rendered_feeds[0]["upstream_id"], "1")
        self.assertTrue(monitor._markers_initialized)


if __name__ == "__main__":
    unittest.main()
