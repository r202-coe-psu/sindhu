import re
import unittest

from . import shared_app


class MapPageLayoutTests(unittest.TestCase):
    """The monitor page is a full-window map with floating cards (#67)."""

    @classmethod
    def setUpClass(cls):
        cls.app = shared_app()
        cls.client = cls.app.test_client()

    def _html(self, path):
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200)
        return response.get_data(as_text=True)

    def test_monitor_has_no_sidebar_or_header_bar(self):
        html = self._html("/th/monitor")
        self.assertIn('class="map-page"', html)
        self.assertNotIn('id="app-sidebar"', html)
        self.assertNotIn('id="toggle-sidebar-btn"', html)

    def test_monitor_keeps_the_menu_in_a_floating_card(self):
        html = self._html("/th/monitor")
        self.assertIn('id="map_menu_btn"', html)
        menu = re.search(r'<nav id="map_menu".*?</nav>', html, re.S).group(0)
        self.assertIn('href="/th/"', menu)
        self.assertIn('href="/th/monitor"', menu)
        # Guests see no admin links, same as the sidebar.
        self.assertNotIn("จัดการโซน", menu)

    def test_monitor_keeps_login_locate_and_panel(self):
        html = self._html("/th/monitor")
        self.assertIn('href="/th/login"', html)
        self.assertIn('id="my_locate"', html)
        self.assertIn('id="monitor_panel"', html)
        self.assertIn('id="monitor_panel_toggle"', html)
        self.assertIn('id="mapid"', html)

    def test_floating_cards_are_marked_for_focus_mode(self):
        html = self._html("/th/monitor")
        for element_id in ("my_locate", "monitor_panel"):
            tag = re.search(rf'<[a-z]+ id="{element_id}"[^>]*>', html).group(0)
            self.assertIn("map-ui", tag, element_id)

    def test_page_starts_in_standards_mode(self):
        self.assertTrue(
            self._html("/th/monitor").lstrip().startswith("<!DOCTYPE html>")
        )

    def test_site_stylesheet_loads_after_leaflet(self):
        html = self._html("/th/monitor")
        self.assertLess(html.index("leaflet.css"), html.index("css/app.css"))

    def test_site_stylesheet_loads_after_leaflet_draw_on_the_zones_page(self):
        class _User:
            is_authenticated = True
            data = {"username": "admin", "roles": ["admin"]}

        with self.app.test_request_context("/th/zones/"):
            from flask import g, render_template

            g.lang_code = "th"
            html = render_template("zones/index.html", current_user=_User())

        self.assertLess(html.index("leaflet.css"), html.index("css/app.css"))
        self.assertLess(html.index("leaflet.draw.css"), html.index("css/app.css"))

    def test_leaflet_draw_icons_are_inverted_for_the_dark_toolbar(self):
        from pathlib import Path

        css = (
            Path(__file__).resolve().parents[2]
            / "sindhu"
            / "web"
            / "static"
            / "css"
            / "map.css"
        ).read_text()
        rule = re.search(r"\.leaflet-draw-toolbar a,[^{]*\{([^}]*)\}", css)
        self.assertIsNotNone(rule)
        self.assertIn("filter: invert(1)", rule.group(1))
        self.assertIn("var(--color-ink-700)", rule.group(1))

    def test_panel_is_folded_in_the_markup(self):
        html = self._html("/th/monitor")
        panel = re.search(r'<section id="monitor_panel"[^>]*>', html).group(0)
        toggle = re.search(
            r'<button id="monitor_panel_toggle"[^>]*>', html, re.S
        ).group(0)
        self.assertIn("is-collapsed", panel)
        self.assertIn('aria-expanded="false"', toggle)

    def test_monitor_title_names_the_page(self):
        self.assertIn(
            f"<title>ติดตามสถานการณ์ | {self.app.config['APP_TITLE']}</title>",
            self._html("/th/monitor"),
        )

    def test_signed_in_user_gets_admin_links_and_user_menu_in_cards(self):
        class _User:
            is_authenticated = True
            data = {"username": "admin"}

        with self.app.test_request_context("/th/monitor"):
            from flask import g, render_template

            g.lang_code = "th"
            # An explicit current_user wins over Flask-Login's context processor.
            html = render_template(
                "sites/monitor.html", current_user=_User(), api_url="", source="all"
            )

        menu = re.search(r'<nav id="map_menu".*?</nav>', html, re.S).group(0)
        for label in ("จัดการโซน", "จัดการสถานี", "ตั้งค่าระบบ"):
            self.assertIn(label, menu)
        user_card = html[html.index("map-user-card") : html.index("map-focus-hint")]
        self.assertIn("ออกจากระบบ", user_card)
        self.assertNotIn("/th/login", user_card)

    def test_other_pages_keep_the_sidebar_and_header(self):
        # default_page.html now includes the shared menu partials.
        html = self._html("/th/")
        self.assertIn('id="app-sidebar"', html)
        self.assertIn('id="toggle-sidebar-btn"', html)
        self.assertIn('href="/th/monitor"', html)
        self.assertIn('href="/th/login"', html)
        self.assertNotIn('class="map-page"', html)


if __name__ == "__main__":
    unittest.main()
