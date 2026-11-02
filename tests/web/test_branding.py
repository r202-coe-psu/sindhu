import struct
import unittest
from pathlib import Path

from PIL import Image

from sindhu import web

IMAGES = Path(__file__).resolve().parents[2] / "sindhu" / "web" / "static" / "images"


class LogoFileTests(unittest.TestCase):
    def test_logo_has_a_transparent_background(self):
        with Image.open(IMAGES / "logo.png") as logo:
            self.assertEqual(logo.size, (256, 256))
            self.assertEqual(logo.convert("RGBA").getpixel((0, 0))[3], 0)

    def test_favicon_holds_the_small_sizes_browsers_ask_for(self):
        data = (IMAGES / "favicon.ico").read_bytes()
        _, kind, count = struct.unpack("<HHH", data[:6])
        self.assertEqual(kind, 1)
        sizes = {data[6 + 16 * i] for i in range(count)}
        self.assertLessEqual({16, 32, 48}, sizes)


class BrandingTemplateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = web.create_app()
        cls.app.config["APP_TITLE"] = "เฝ้าดู (FoundDoo)"
        cls.client = cls.app.test_client()

    def _html(self, path):
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200)
        return response.get_data(as_text=True)

    def test_page_without_a_title_has_no_dangling_separator(self):
        self.assertIn("<title>เฝ้าดู (FoundDoo)</title>", self._html("/th/"))

    def test_page_with_a_title_puts_it_first(self):
        self.assertIn(
            "<title>เข้าสู่ระบบ | เฝ้าดู (FoundDoo)</title>", self._html("/th/login")
        )

    def test_logo_replaces_the_placeholder_icon(self):
        for path in ("/th/", "/th/login"):
            html = self._html(path)
            self.assertIn("images/logo.png", html)
            self.assertIn('rel="icon"', html)
            self.assertNotIn("ph-fill ph-waves", html)


if __name__ == "__main__":
    unittest.main()
