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
    r"|(?<!after:)\bbg-white\b(?!/(?:[0-9]|1[0-9]|20)\b)"
    r"|\btext-(?:red|orange|amber|yellow|lime|green|emerald|purple|violet|rose|pink)-[6-9]00\b"
    r"|\btext-secondary\b"
    r"|\bbtn-(?:info|success|warning|error|accent)\b[^\"'`]*\btext-white\b"
)

LIGHT_INLINE_COLOUR = re.compile(
    r"background(?:-color)?\s*:\s*(?:white|#fff(?:fff)?)\b"
    r"|#(?:e5e7eb|d1d5db|f3f4f6|f9fafb|e2e8f0|cbd5e1|f1f5f9|f8fafc)\b",
    re.IGNORECASE,
)

SEMANTIC_COLOURS = (
    "primary",
    "secondary",
    "accent",
    "neutral",
    "info",
    "success",
    "warning",
    "error",
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

    def test_inline_styles_use_tokens_for_light_surfaces(self):
        offenders = []
        for path in _source_files():
            for number, line in enumerate(path.read_text().splitlines(), 1):
                for match in LIGHT_INLINE_COLOUR.finditer(line):
                    offenders.append(
                        f"{path.relative_to(WEB)}:{number}: {match.group(0)}"
                    )
        self.assertEqual(offenders, [])

    def test_raw_colour_check_catches_known_slips(self):
        for snippet in (
            "bg-white",
            "bg-white/100",
            "bg-white/90",
            "text-yellow-600",
            "text-secondary",
            'class="btn btn-xs btn-info text-white"',
        ):
            with self.subTest(snippet=snippet):
                self.assertIsNotNone(RAW_COLOUR.search(snippet))
        for snippet in ("bg-white/10", "after:bg-white", "text-amber-400"):
            with self.subTest(snippet=snippet):
                self.assertIsNone(RAW_COLOUR.search(snippet))

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

    def test_content_colour_is_readable_on_every_semantic_colour(self):
        for name in SEMANTIC_COLOURS:
            with self.subTest(colour=name):
                self.assertGreaterEqual(
                    _contrast(_token(f"{name}-content"), _token(name)), 4.5
                )

    def test_status_colours_are_readable_as_text_on_surfaces(self):
        for name in ("info", "success", "warning", "error"):
            for surface in ("base-100", "base-200"):
                with self.subTest(colour=name, surface=surface):
                    self.assertGreaterEqual(
                        _contrast(_token(name), _token(surface)), 4.5
                    )

    def test_ink_scale_gets_lighter_as_the_number_grows(self):
        steps = (50, 100, 200, 300, 400, 500, 600, 700, 800, 900, 950)
        luminances = [_luminance(_token(f"ink-{step}")) for step in steps]
        self.assertEqual(luminances, sorted(luminances))
        self.assertEqual(len(set(luminances)), len(luminances))


if __name__ == "__main__":
    unittest.main()
