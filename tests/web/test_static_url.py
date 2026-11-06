import os
import unittest

from sindhu.web.utils import template_filters

from . import shared_app


class StaticUrlTests(unittest.TestCase):
    """static_url versions files by modification time so browsers can cache them."""

    @classmethod
    def setUpClass(cls):
        cls.app = shared_app()

    def url(self, filename):
        with self.app.test_request_context("/"):
            return template_filters.static_url(filename)

    def test_version_is_the_file_modification_time(self):
        path = os.path.join(self.app.static_folder, "images", "logo.png")
        self.assertEqual(
            self.url("images/logo.png"),
            f"/static/images/logo.png?v={int(os.path.getmtime(path))}",
        )

    def test_same_url_on_every_call(self):
        self.assertEqual(self.url("images/logo.png"), self.url("images/logo.png"))

    def test_missing_file_still_gets_a_stable_url(self):
        first = self.url("images/does-not-exist.png")
        self.assertTrue(first.startswith("/static/images/does-not-exist.png?v="))
        self.assertEqual(first, self.url("images/does-not-exist.png"))


if __name__ == "__main__":
    unittest.main()
