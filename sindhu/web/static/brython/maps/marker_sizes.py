"""Marker size constants and pure helpers for the maps package.

Kept free of ``browser``/``javascript`` imports so they can be unit tested in
CPython.

Every Leaflet icon uses a transparent hit box (``iconSize``) of at least
HIT_BOX_PX so it stays easy to tap, and the smaller visual is centered inside
it. Anchors are expressed in hit box pixels.
"""

# Transparent click/tap target around every marker
HIT_BOX_PX = 28

# Station markers (donut / drop / tank / bubble / pulse / wind arrow)
STATION_DOT_PX = 16
STATION_TANK = (10, 20)
BUBBLE_MIN_PX = 8
BUBBLE_MAX_PX = 24
WIND_ARROW_PX = 12
PULSE_PX = 12
STATION_TOOLTIP_OFFSET = (0, 26)


class PinSpec:
    """Sizes of a pin whose tip marks the point.

    ``pin`` is the visual (width, height), ``hit_box`` the transparent
    (width, height) around it, and ``popup_offset_y`` how far above the tip
    popups and tooltips open.
    """

    def __init__(self, pin, hit_box, popup_offset_y):
        self.pin = pin
        self.hit_box = hit_box
        self.popup_offset_y = popup_offset_y

    @property
    def anchor(self):
        """The pin tip: horizontal center, bottom of the hit box."""
        return (self.hit_box[0] // 2, self.hit_box[1])


CCTV = PinSpec(pin=(20, 25), hit_box=(28, 32), popup_offset_y=-24)
# Pin dropped by the user (place_pin)
USER = PinSpec(pin=(22, 30), hit_box=(28, 32), popup_offset_y=-27)
# "My location" pin; an icon font glyph, so pin[1] is its font size
MY_LOCATION = PinSpec(pin=(22, 22), hit_box=(28, 28), popup_offset_y=-24)

# Zoom levels at or below this are "far" (city overview)
FAR_ZOOM_MAX = 11


def bubble_size(percent):
    """Bubble diameter in px for a 0-100 fill percent, clamped to 8-24."""
    return max(BUBBLE_MIN_PX, min(percent / 4, BUBBLE_MAX_PX))


def is_far_zoom(zoom):
    """True when the map is zoomed out far enough to use smaller markers."""
    return zoom is not None and zoom <= FAR_ZOOM_MAX


def hit_box_html(inner_html, width=HIT_BOX_PX, height=HIT_BOX_PX, align="center"):
    """Wrap a marker visual in a transparent hit box.

    align is "center" (visual centered) or "bottom" (visual centered
    horizontally and flush with the bottom edge, for pins whose tip anchors
    the icon).
    """
    items = "flex-end" if align == "bottom" else "center"
    return (
        f'<div style="width: {width}px; height: {height}px; display: flex; '
        f'align-items: {items}; justify-content: center;">{inner_html}</div>'
    )


def station_dot_html(width, height, style, inner_html=""):
    """A station visual: the .station-dot box (shrunk at far zoom by CSS)."""
    return (
        f'<div class="station-dot" style="width: {width}px; height: {height}px; '
        f'{style}">{inner_html}</div>'
    )
