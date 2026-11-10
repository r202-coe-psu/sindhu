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

# Class lists: class="…" / className = "…", classList.add(…), f-strings and
# JS template literals (which may nest quotes), then any other short quoted
# string such as the branches of a JS ternary.
CLASS_ATTRIBUTE = re.compile(
    r"\bclass(?:Name)?\s*\+?=\s*(?P<quote>[\"'`])(?P<value>.*?)(?P=quote)", re.S
)
PLAIN_CLASS_STRING = re.compile(
    r"(?<!\w)f?(?P<quote>[\"'`])(?P<value>[^\"'`<>=\n]*)(?P=quote)"
)
CLASS_LIST_CALL = re.compile(r"\bclassList\.(?:add|toggle)\((?P<value>[^)]*)\)")
NESTING_STRING = re.compile(
    r"(?<!\w)f(?P<quote>[\"'])(?P<value>(?:(?!(?P=quote))[^<>=\n])*)(?P=quote)"
    r"|`(?P<template>[^`<>]*)`"
)
CLASS_TOKEN_NOISE = "'\"`{}()$"
SOLID_STATUS_SURFACE = re.compile(r"(?:btn|badge|bg|alert)-(?:info|success|warning|error|accent)")
TINT_OPACITY_LIMIT = 50  # bg-success/15 is a tint; /50 and above reads as solid
DIM_INK_TEXT = re.compile(r"text-ink-(?:50|100|200|300)")

# Style declarations whose value is a colour. A value may continue on
# indented lines without a colon (multi-line box-shadow in CSS files).
COLOUR_DECLARATION = re.compile(
    r"(?<![\w-])(?P<property>color|background(?:-color|-image)?|border(?:-[a-z]+)*"
    r"|fill|stroke|outline(?:-color)?|box-shadow)\s*:"
    r"(?P<value>[^;\"<>\n]*(?:\n[ \t]+[^;\"<>\n:]*)*)",
    re.IGNORECASE,
)
COLOUR_LITERAL = re.compile(
    r"(?<![\w-])(?P<hex>#(?:[0-9a-f]{8}|[0-9a-f]{6}|[0-9a-f]{3,4}))(?![0-9a-f])"
    r"|\brgba?\(\s*(?P<rgb>[^)]*)\)"
    r"|(?<![\w-])(?P<name>white|whitesmoke|snow|ghostwhite)(?![\w-])",
    re.IGNORECASE,
)
NAMED_COLOURS = {
    "white": "#ffffff",
    "whitesmoke": "#f5f5f5",
    "snow": "#fffafa",
    "ghostwhite": "#f8f8ff",
}
SURFACE_PROPERTY = re.compile(r"background|border|outline|box-shadow", re.IGNORECASE)
WHITE_LUMINANCE = 0.85  # near-white in any colour property
LIGHT_GREY_LUMINANCE = 0.35  # #a3a3a3 and lighter greys as a surface
PALE_TINT_LUMINANCE = 0.7  # #dbeafe, #fef3c7 … as a surface
NEUTRAL_CHANNEL_SPREAD = 0x20
VISIBLE_ALPHA = 0.5  # rgb(255 255 255 / 0.1) is an overlay tint, not a surface
# Literal light colours that are data, not theme, with the reason.
LIGHT_COLOUR_ALLOWLIST = {
    "#fef08a": "zone fill preset swatch in zones/index.html (user data colour)",
}

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


def _class_lists(source):
    """(offset, class names) for every class list in ``source``, once each."""
    covered = []
    for pattern in (CLASS_ATTRIBUTE, CLASS_LIST_CALL, NESTING_STRING, PLAIN_CLASS_STRING):
        for match in pattern.finditer(source):
            group = "template" if match.groupdict().get("template") else "value"
            if match.group(group) is None:
                continue
            start, end = match.span(group)
            if any(lo <= start and end <= hi for lo, hi in covered):
                continue
            covered.append((start, end))
            yield start, re.split(r"[\s,]+", match.group(group).strip())


def _class_parts(name):
    """('text-white', 90) for 'hover:text-white/90'; Jinja/JS quotes dropped."""
    name = name.strip(CLASS_TOKEN_NOISE)
    base, _, opacity = name.rsplit(":", 1)[-1].partition("/")
    base = base.strip(CLASS_TOKEN_NOISE)
    return base, int(opacity) if opacity.isdigit() else None


def _class_list_problems(classes):
    problems = []
    parts = [_class_parts(name) for name in classes]
    has_white_text = any(base == "text-white" for base, _ in parts)
    on_status_surface = any(
        SOLID_STATUS_SURFACE.fullmatch(base)
        and (opacity is None or opacity >= TINT_OPACITY_LIMIT)
        for base, opacity in parts
    )
    if has_white_text and on_status_surface:
        problems.append("text-white on a status colour; use its *-content colour")
    is_icon = any(base == "ph" or base.startswith("ph-") for base, _ in parts)
    if not is_icon and any(DIM_INK_TEXT.fullmatch(base) for base, _ in parts):
        problems.append("text-ink-50..300 is too dim for text; use ink-400 or above")
    return problems


def _rgb_hex_and_alpha(arguments):
    numbers = re.findall(r"[\d.]+%?", arguments)
    if len(numbers) < 3 or any(n.endswith("%") for n in numbers[:3]):
        return None, 1.0
    channels = [min(255, round(float(n))) for n in numbers[:3]]
    alpha = 1.0
    if len(numbers) > 3:
        raw = numbers[3]
        alpha = float(raw[:-1]) / 100 if raw.endswith("%") else float(raw)
    return "#" + "".join(f"{c:02x}" for c in channels), alpha


def _colour_literal(match):
    """(#rrggbb, alpha) of a COLOUR_LITERAL match, or (None, 1) if unknown."""
    if match.group("name"):
        return NAMED_COLOURS[match.group("name").lower()], 1.0
    if match.group("rgb") is not None:
        return _rgb_hex_and_alpha(match.group("rgb"))
    colour = match.group("hex").lower()
    if len(colour) in (5, 9):
        alpha = int(colour[-2:] if len(colour) == 9 else colour[-1] * 2, 16) / 255
        return _full_hex(colour[: len(colour) - (2 if len(colour) == 9 else 1)]), alpha
    return _full_hex(colour), 1.0


def _is_light_surface(hex_colour):
    channels = [int(hex_colour[i : i + 2], 16) for i in (1, 3, 5)]
    is_neutral = max(channels) - min(channels) <= NEUTRAL_CHANNEL_SPREAD
    limit = LIGHT_GREY_LUMINANCE if is_neutral else PALE_TINT_LUMINANCE
    return _luminance(hex_colour) > limit


def _style_problems(source):
    problems = []
    for declaration in COLOUR_DECLARATION.finditer(source):
        is_surface = SURFACE_PROPERTY.match(declaration.group("property"))
        for literal in COLOUR_LITERAL.finditer(declaration.group("value")):
            colour, alpha = _colour_literal(literal)
            if colour is None or alpha < VISIBLE_ALPHA:
                continue
            if colour in LIGHT_COLOUR_ALLOWLIST:
                continue
            if _luminance(colour) > WHITE_LUMINANCE or (
                is_surface and _is_light_surface(colour)
            ):
                problems.append((declaration.start(), declaration.group(0)))
                break
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
            for offset, classes in _class_lists(source):
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
            'class="btn btn-error md:text-white"',
            'class="bg-warning/80 text-white/90"',
            'class="hover:text-ink-300"',
            "class=\"badge {{ 'badge-warning' if x }} text-white\"",
            'el.className = ok ? "a" : "badge badge-warning text-white"',
            "el.classList.add('badge-warning', 'text-white')",
            "f\"btn {'btn-success' if ok else 'btn-error'} text-white\"",
            '`${ok ? "badge-warning" : ""} text-white`',
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
            'el.className = ok ? "badge badge-warning" : "text-white"',
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
            "border: 1px solid #e5e7eb",
            "border-top-color: white",
            "background: linear-gradient(#1f1f1f, #f3f4f6)",
            "color: rgba(255, 255, 255, 0.9)",
            "background: rgb(243 244 246)",
            "background: #ffffffcc",
            "box-shadow:\n    0 0 0 2px white;",
            "background: whitesmoke",
            "background: #dbeafe",
            "background: #a3a3a3",
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
            "background: rgb(255 255 255 / 0.1);",
            "box-shadow: 0 0 0 0 rgb(122 184 255 / 0.7);",
            "color: #fbbf24;",
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
