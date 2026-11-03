"""Marker size constants and pure helpers for the maps package.

Kept free of ``browser``/``javascript`` imports so they can be unit tested in
CPython.

Every Leaflet icon uses a transparent hit box (``iconSize``) of at least
HIT_BOX_PX so it stays easy to tap, and the smaller visual is centered inside
it. Anchors are expressed in hit box pixels.
"""

import math

# Transparent click/tap target around every marker
HIT_BOX_PX = 28

# Station markers (donut / drop / tank / bubble / pulse / wind arrow)
STATION_DOT_PX = 16
STATION_DOT_FAR_PX = 12  # visual size at far zoom (CSS scale 0.75 of 16)
STATION_TANK = (10, 20)
BUBBLE_MIN_PX = 8
BUBBLE_MAX_PX = 24
WIND_ARROW_PX = 12
PULSE_PX = 12
STATION_TOOLTIP_OFFSET = (0, 26)

# CCTV pin: visual size, hit box, tip anchor, popup/tooltip offset
CCTV_PIN = (20, 25)
CCTV_HIT_BOX = (28, 32)
CCTV_ANCHOR = (14, 32)  # pin tip: horizontal center, bottom of the hit box
CCTV_POPUP_OFFSET_Y = -24
# A camera paired with a station is shifted by this much (right, up) so its
# pin sits upper-right of the station dot instead of covering it
CCTV_PAIRED_SHIFT = (8, 8)
PAIRED_RADIUS_M = 300

# Pin dropped by the user (place_pin) and the "my location" pin
USER_PIN = (22, 30)
USER_HIT_BOX = (28, 32)
USER_ANCHOR = (14, 32)
USER_POPUP_OFFSET_Y = -27
MY_LOCATION_PX = 22
MY_LOCATION_HIT_BOX = (28, 28)
MY_LOCATION_ANCHOR = (14, 28)
MY_LOCATION_POPUP_OFFSET_Y = -24

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


def haversine_distance(coord1, coord2):
    """Calculate distance in meters between two [lon, lat] coordinates."""
    try:
        lon1, lat1 = float(coord1[0]), float(coord1[1])
        lon2, lat2 = float(coord2[0]), float(coord2[1])
        r = 6371000.0
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlam = math.radians(lon2 - lon1)
        a = (
            math.sin(dphi / 2) ** 2
            + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
        )
        return 2 * r * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    except Exception:
        return float("inf")


def is_paired_with_station(feed_coords, station_coords_list):
    """True if the camera is within PAIRED_RADIUS_M of any station.

    Coordinates are GeoJSON [lng, lat]. Empty or malformed input is unpaired.
    """
    if not feed_coords or len(feed_coords) < 2 or not station_coords_list:
        return False
    for s_coords in station_coords_list:
        if not s_coords or len(s_coords) < 2:
            continue
        if haversine_distance(feed_coords, s_coords) <= PAIRED_RADIUS_M:
            return True
    return False
