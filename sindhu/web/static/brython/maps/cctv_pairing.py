"""Which CCTV camera belongs to which water station, and where its pin goes.

Kept free of ``browser``/``javascript`` imports so it can be unit tested in
CPython. The map, the water monitor and the CCTV panel all use these helpers,
so a camera and a station are linked by the same rule everywhere.
"""

import math

from maps.marker_sizes import CCTV, HIT_BOX_PX

# A camera and a station without a shared code are linked when they are at
# most this far apart
MATCH_RADIUS_M = 300

# Pin tip pushed this many px beyond the edge of the station hit box
PIN_GAP_PX = 1

# Direction used when the camera sits exactly on the station (screen
# coordinates, y grows downward): upper right
_DEFAULT_DIRECTION = (math.sqrt(0.5), -math.sqrt(0.5))


def haversine_distance(coord1, coord2):
    """Distance in meters between two [lon, lat] coordinates; inf if malformed."""
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


def geo_coords(item):
    """GeoJSON [lng, lat] of a station or feed dict, or None."""
    if not isinstance(item, dict):
        return None
    obj = item.get("coordinates")
    coords = obj.get("coordinates") if isinstance(obj, dict) else None
    if not coords or len(coords) < 2:
        return None
    return coords


def _code(item):
    return str(item.get("code") or "").strip().lower()


def find_match(item, candidates):
    """The candidate linked to ``item``: same code first, else nearest in range.

    Works in both directions (station -> cameras, camera -> stations).
    """
    if not isinstance(item, dict) or not candidates:
        return None
    code = _code(item)
    coords = geo_coords(item)

    best = None
    min_dist = float("inf")
    for cand in candidates:
        if not isinstance(cand, dict):
            continue
        if code and code == _code(cand):
            return cand
        cand_coords = geo_coords(cand)
        if coords and cand_coords:
            dist = haversine_distance(coords, cand_coords)
            if dist <= MATCH_RADIUS_M and dist < min_dist:
                min_dist = dist
                best = cand
    return best


def _away_from_zero(value):
    return int(math.copysign(math.ceil(abs(value)), value))


def pin_shift(dx, dy):
    """Pixels to move a camera pin so its station's hit box does not cover it.

    ``dx``/``dy`` is the camera minus the station in screen pixels at the
    current zoom. The pin (CCTV.pin, tip at the camera point) is pushed along
    the station -> camera direction until it clears the station hit box.
    Returns (0, 0) when they already do not overlap.
    """
    half = HIT_BOX_PX / 2 + PIN_GAP_PX
    pin_w, pin_h = CCTV.pin
    left, right = dx - pin_w / 2, dx + pin_w / 2
    top, bottom = dy - pin_h, dy
    if right <= -half or left >= half or bottom <= -half or top >= half:
        return (0, 0)

    dist = math.hypot(dx, dy)
    if dist < 1:
        ux, uy = _DEFAULT_DIRECTION
    else:
        ux, uy = dx / dist, dy / dist

    # Smallest push along (ux, uy) that clears the box on either axis
    steps = []
    if ux > 0:
        steps.append((half - left) / ux)
    elif ux < 0:
        steps.append((right + half) / -ux)
    if uy > 0:
        steps.append((half - top) / uy)
    elif uy < 0:
        steps.append((bottom + half) / -uy)
    t = min(steps)
    return (_away_from_zero(ux * t), _away_from_zero(uy * t))
