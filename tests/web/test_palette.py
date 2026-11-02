"""Guards for the site palette (#41).

The site has one dark theme built from the brand-* / ink-* tokens in
setup.css.  Raw Tailwind palettes (gray-*, slate-*, blue-* …) and bg-white
bypass those tokens and show up as light patches on the dark theme.
"""

import re
import unittest
from pathlib import Path

WEB = Path(__file__).resolve().parents[2] / "sindhu" / "web"
SETUP_CSS = WEB / "static" / "css" / "setup.css"

RAW_COLOUR = re.compile(
    r"\b(?:bg|text|border|ring|divide|from|to|via|fill|stroke|outline|placeholder)"
    r"-(?:gray|slate|zinc|neutral|stone|blue|sky|indigo|cyan)-\d{2,3}\b"
    r"|(?<!after:)\bbg-white\b(?!/10)"
)


def _source_files():
    yield from (WEB / "templates").rglob("*.html")
    for path in (WEB / "static" / "brython").rglob("*.py"):
        if "__pycache__" not in path.parts:
            yield path


def _token(name):
    match = re.search(rf"--color-{name}:\s*(#[0-9a-fA-F]{{6}})", SETUP_CSS.read_text())
    if not match:
        raise AssertionError(f"--color-{name} is not a hex colour in setup.css")
    return match.group(1)


def _luminance(hex_colour):
    channels = []
    for i in (1, 3, 5):
        c = int(hex_colour[i : i + 2], 16) / 255
        channels.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    r, g, b = channels
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast(a, b):
    high, low = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


class PaletteTests(unittest.TestCase):
    def test_templates_and_brython_use_palette_tokens(self):
        offenders = []
        for path in _source_files():
            for number, line in enumerate(path.read_text().splitlines(), 1):
                for match in RAW_COLOUR.finditer(line):
                    offenders.append(
                        f"{path.relative_to(WEB)}:{number}: {match.group(0)}"
                    )
        self.assertEqual(offenders, [])

    def test_theme_is_dark(self):
        css = SETUP_CSS.read_text()
        theme = css[css.index('@plugin "daisyui/theme"') :]
        self.assertIn("color-scheme: dark;", theme[: theme.index("}")])

    def test_text_tokens_are_readable_on_surfaces(self):
        surfaces = {name: _token(name) for name in ("base-100", "base-200")}
        for text in ("ink-400", "ink-500", "ink-900", "brand-600", "brand-700"):
            for surface, colour in surfaces.items():
                with self.subTest(text=text, surface=surface):
                    self.assertGreaterEqual(_contrast(_token(text), colour), 4.5)

    def test_white_text_is_readable_on_primary_buttons(self):
        self.assertGreaterEqual(_contrast("#ffffff", _token("primary")), 4.5)


if __name__ == "__main__":
    unittest.main()
