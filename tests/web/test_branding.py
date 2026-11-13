import importlib
import os
import re
import struct
import unittest
import zlib
from pathlib import Path
from unittest import mock

from sindhu import default_settings

from . import shared_app

IMAGES = Path(__file__).resolve().parents[2] / "sindhu" / "web" / "static" / "images"

APP_NAME = "เฝ้าดู"


def _png_chunks(data):
    """Yield (type, payload) for each chunk of a PNG file."""
    assert data[:8] == b"\x89PNG\r\n\x1a\n", "not a PNG file"
    offset = 8
    while offset < len(data):
        (length,) = struct.unpack(">I", data[offset : offset + 4])
        kind = data[offset + 4 : offset + 8]
        yield kind, data[offset + 8 : offset + 8 + length]
        offset += 12 + length


class LogoFileTests(unittest.TestCase):
    # Read with the standard library only: Pillow is not a declared dependency.

    def test_logo_is_a_256px_image_with_an_alpha_channel(self):
        chunks = dict(_png_chunks((IMAGES / "logo.png").read_bytes()))
        width, height, depth, colour_type = struct.unpack(">IIBB", chunks[b"IHDR"][:10])
        self.assertEqual((width, height), (256, 256))
        self.assertEqual((depth, colour_type), (8, 6))  # 8-bit RGBA

    def test_logo_corner_is_transparent(self):
        data = (IMAGES / "logo.png").read_bytes()
        idat = b"".join(
            payload for kind, payload in _png_chunks(data) if kind == b"IDAT"
        )
        pixels = zlib.decompress(idat)
        # Byte 0 is the first row's filter type.  Every PNG filter leaves the
        # very first pixel unchanged (it has no left or upper neighbour), so
        # bytes 1–4 are its raw RGBA.
        self.assertEqual(pixels[4], 0)

    def test_favicon_holds_the_small_sizes_browsers_ask_for(self):
        data = (IMAGES / "favicon.ico").read_bytes()
        _, kind, count = struct.unpack("<HHH", data[:6])
        self.assertEqual(kind, 1)
        sizes = {data[6 + 16 * i] for i in range(count)}
        self.assertLessEqual({16, 32, 48}, sizes)


class AppNameTests(unittest.TestCase):
    def test_default_name_is_the_new_one(self):
        # Without APP_TITLE / PROJECT_NAME in the environment the built-in
        # default is used; that default is what this change sets.
        cleared = {
            k: v
            for k, v in os.environ.items()
            if k not in ("APP_TITLE", "PROJECT_NAME")
        }
        with mock.patch.dict(os.environ, cleared, clear=True):
            try:
                self.assertEqual(importlib.reload(default_settings).APP_TITLE, APP_NAME)
            finally:
                importlib.reload(default_settings)


class BrandingTemplateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = shared_app()
        cls.client = cls.app.test_client()
        cls.name = cls.app.config["APP_TITLE"]

    def _html(self, path):
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200)
        return response.get_data(as_text=True)

    def test_app_name_comes_from_the_default_settings(self):
        self.assertEqual(self.name, default_settings.APP_TITLE)

    def test_page_without_a_title_has_no_dangling_separator(self):
        self.assertIn(f"<title>{self.name}</title>", self._html("/th/"))

    def test_page_with_a_title_puts_it_first(self):
        self.assertIn(
            f"<title>เข้าสู่ระบบ | {self.name}</title>", self._html("/th/login")
        )

    def test_logo_replaces_the_placeholder_icon(self):
        for path in ("/th/", "/th/login"):
            with self.subTest(path=path):
                html = self._html(path)
                self.assertRegex(html, r'<img src="/static/images/logo\.png\?v=\d+"')
                self.assertRegex(
                    html, r'<link rel="icon" href="/static/images/favicon\.ico\?v=\d+"'
                )
                self.assertNotIn("ph-fill ph-waves", html)

    def test_asset_urls_stay_the_same_between_page_loads(self):
        # A changing ?v= would stop browsers caching the logo and favicon.
        pattern = re.compile(r"/static/images/(?:logo\.png|favicon\.ico)\?v=\d+")
        first = pattern.findall(self._html("/th/"))
        second = pattern.findall(self._html("/th/"))
        self.assertTrue(first)
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
