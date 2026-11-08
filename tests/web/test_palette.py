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
SITE_CSS = (SETUP_CSS, WEB / "static" / "css" / "map.css")

RAW_COLOUR = re.compile(
    r"\b(?:bg|text|border|ring|divide|from|to|via|fill|stroke|outline|placeholder)"
    r"-(?:gray|slate|zinc|neutral|stone|blue|sky|indigo|cyan)-\d{2,3}\b"
    r"|(?<!after:)\bbg-white\b(?!/(?:[0-9]|1[0-9]|20)\b)"
    r"|\btext-(?:red|orange|amber|yellow|lime|green|emerald|rose|pink|purple|violet)"
    r"-\d{2,3}\b"
    r"|\btext-secondary\b"
)

CLASS_ATTRIBUTE = re.compile(
    r"\bclass(?:Name)?\s*=\s*(?P<quote>[\"'`])(?P<value>.*?)(?P=quote)", re.S
)
PLAIN_CLASS_STRING = re.compile(
    r"(?<!\w)f?(?P<quote>[\"'])(?P<value>[^\"'<>=\n]*)(?P=quote)"
)
SOLID_STATUS_SURFACE = re.compile(
    r"^(?:[a-z-]+:)*(?:btn|badge|bg|alert)-(?:info|success|warning|error|accent)$"
)
DIM_INK_TEXT = re.compile(r"^text-ink-(?:50|100|200|300)$")

WHITE_COLOUR_VALUE = re.compile(
    r"(?<![\w-])(?:color|background(?:-color)?|border(?:-[a-z]+)?|fill|stroke"
    r"|outline(?:-color)?|box-shadow)\s*:[^;\"\n]*?(?<![\w-])'?(?:white|#fff(?:fff)?)'?"
    r"(?![\w-])",
    re.IGNORECASE,
)
LITERAL_BACKGROUND = re.compile(
    r"(?<![\w-])background(?:-color)?\s*:[^;\"\n]*?(?P<hex>#[0-9a-fA-F]{6}|#[0-9a-fA-F]{3})"
    r"(?![0-9a-fA-F])"
)
LIGHT_SURFACE_LUMINANCE = 0.5
NEUTRAL_CHANNEL_SPREAD = 0x20

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


def _full_hex(colour):
    if len(colour) == 4:
        return "#" + "".join(c * 2 for c in colour[1:])
    return colour


def _luminance(hex_colour):
    hex_colour = _full_hex(hex_colour)
    channels = []
    for i in (1, 3, 5):
        c = int(hex_colour[i : i + 2], 16) / 255
        channels.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    r, g, b = channels
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast(a, b):
    high, low = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def _class_lists(source, python=False):
    for match in CLASS_ATTRIBUTE.finditer(source):
        yield match.start(), match.group("value").split()
    if python:
        for match in PLAIN_CLASS_STRING.finditer(source):
            yield match.start(), match.group("value").split()


def _class_list_problems(classes):
    problems = []
    if "text-white" in classes and any(
        SOLID_STATUS_SURFACE.match(name) for name in classes
    ):
        problems.append("text-white on a status colour; use its *-content colour")
    is_icon = "ph" in classes or any(name.startswith("ph-") for name in classes)
    if not is_icon and any(DIM_INK_TEXT.match(name) for name in classes):
        problems.append("text-ink-50..300 is too dim for text; use ink-400 or above")
    return problems


def _is_light_grey(hex_colour):
    hex_colour = _full_hex(hex_colour)
    channels = [int(hex_colour[i : i + 2], 16) for i in (1, 3, 5)]
    is_neutral = max(channels) - min(channels) <= NEUTRAL_CHANNEL_SPREAD
    return is_neutral and _luminance(hex_colour) > LIGHT_SURFACE_LUMINANCE


def _style_problems(source):
    problems = [(m.start(), m.group(0)) for m in WHITE_COLOUR_VALUE.finditer(source)]
    for match in LITERAL_BACKGROUND.finditer(source):
        if _is_light_grey(match.group("hex")):
            problems.append((match.start(), match.group(0)))
    return problems


def _line(source, offset):
    return source.count("\n", 0, offset) + 1


def _resolve_css_colour(value, variables):
    value = value.strip()
    match = re.fullmatch(r"var\(--color-([\w-]+)\)", value)
    if match:
        return _token(match.group(1))
    match = re.fullmatch(r"var\(--([\w-]+)\)", value)
    if match:
        return _resolve_css_colour(variables[match.group(1)], variables)
    if re.fullmatch(r"#[0-9a-fA-F]{3}|#[0-9a-fA-F]{6}", value):
        return _full_hex(value)
    raise AssertionError(f"cannot resolve colour {value!r}")


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

    def test_class_lists_keep_text_readable(self):
        offenders = []
        for path in _source_files():
            source = path.read_text()
            for offset, classes in _class_lists(source, python=path.suffix == ".py"):
                for problem in _class_list_problems(classes):
                    offenders.append(
                        f"{path.relative_to(WEB)}:{_line(source, offset)}: {problem}"
                    )
        self.assertEqual(offenders, [])

    def test_styles_use_tokens_instead_of_white_or_light_surfaces(self):
        offenders = []
        for path in (*_source_files(), *SITE_CSS):
            source = path.read_text()
            for offset, text in _style_problems(source):
                offenders.append(
                    f"{path.relative_to(WEB)}:{_line(source, offset)}: {text[:60]}"
                )
        self.assertEqual(offenders, [])

    def test_class_checks_catch_known_slips(self):
        flagged = (
            'class="btn btn-xs btn-info text-white"',
            'class="text-white btn-success"',
            'class="bg-success text-white"',
            'class="btn\n    btn-error\n    text-white"',
            'className = "badge badge-warning text-white"',
            '<span class="text-ink-300">ข้อความ</span>',
        )
        for snippet in flagged:
            with self.subTest(snippet=snippet):
                problems = [
                    problem
                    for _, classes in _class_lists(snippet)
                    for problem in _class_list_problems(classes)
                ]
                self.assertTrue(problems)
        passed = (
            'class="btn btn-primary text-white"',
            'class="bg-success/15 text-white"',
            '<i class="ph ph-map-trifold text-4xl text-ink-300"></i>',
        )
        for snippet in passed:
            with self.subTest(snippet=snippet):
                problems = [
                    problem
                    for _, classes in _class_lists(snippet)
                    for problem in _class_list_problems(classes)
                ]
                self.assertEqual(problems, [])

    def test_style_checks_catch_known_slips(self):
        flagged = (
            "border: 2px solid white",
            "background-color: {'white'};",
            "color:white;",
            "background: #fff;",
            "background: #e5e7eb",
            "background: conic-gradient(red 50%, #cbd5e1 0)",
        )
        for snippet in flagged:
            with self.subTest(snippet=snippet):
                self.assertTrue(_style_problems(snippet))
        passed = (
            "white-space: nowrap;",
            'style="color: var(--x)" class="text-white"',
            "background: #f97316;",
            "background-color: #FEF08A;",
            "background: var(--color-ink-950);",
        )
        for snippet in passed:
            with self.subTest(snippet=snippet):
                self.assertEqual(_style_problems(snippet), [])

    def test_raw_colour_check_catches_known_slips(self):
        for snippet in (
            "bg-white",
            "bg-white/100",
            "bg-white/90",
            "text-yellow-600",
            "text-amber-400",
            "hover:text-red-200",
            "text-secondary",
        ):
            with self.subTest(snippet=snippet):
                self.assertIsNotNone(RAW_COLOUR.search(snippet))
        for snippet in (
            "bg-white/10",
            "after:bg-white",
            "text-warning",
            "bg-amber-500",
        ):
            with self.subTest(snippet=snippet):
                self.assertIsNone(RAW_COLOUR.search(snippet))

    def test_cctv_status_labels_are_readable(self):
        css = SETUP_CSS.read_text()
        variables = dict(re.findall(r"--(cctv-[\w-]+):\s*([^;]+);", css))
        states = re.findall(r"\.cctv-status--([\w-]+)\s*\{([^}]*)\}", css)
        self.assertGreaterEqual({name for name, _ in states}, {"fresh", "stale"})
        for name, body in states:
            with self.subTest(state=name):
                background = re.search(r"background:\s*([^;]+);", body).group(1)
                colour = re.search(r"(?<![\w-])color:\s*([^;]+);", body).group(1)
                self.assertGreaterEqual(
                    _contrast(
                        _resolve_css_colour(background, variables),
                        _resolve_css_colour(colour, variables),
                    ),
                    4.5,
                )

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
