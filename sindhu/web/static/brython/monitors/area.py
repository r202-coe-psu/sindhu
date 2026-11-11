"""Pure helpers for the monitor's area (zone / tambon) selector.

No browser imports here so the logic can be tested in plain CPython.
"""

ALL_AREAS = ""
ZONE_PREFIX = "zone:"
TAMBON_PREFIX = "tambon:"

# Where an area selection came from.
SOURCE_MAP = "map"
SOURCE_LIST = "list"
SOURCE_LOCATION = "location"

# Kinds accepted by location_message().
MSG_IN_ZONE = "in_zone"
MSG_OUTSIDE = "outside"
MSG_DENIED = "denied"
MSG_ERROR = "error"


def _zone_label(zone):
    return zone.get("name_th") or zone.get("name") or str(zone.get("id", ""))


def _unique_tambons(zones):
    return sorted({n for zone in zones or [] for n in zone.get("tambons") or []})


def build_area_options(zones):
    """Options for the area <select>: all, then zones, then tambons."""
    options = [{"value": ALL_AREAS, "label": "ทุกพื้นที่", "group": None}]
    for zone in zones or []:
        zone_id = str(zone.get("id", "") or "")
        if not zone_id:
            continue
        options.append(
            {
                "value": f"{ZONE_PREFIX}{zone_id}",
                "label": _zone_label(zone),
                "group": "Zone",
            }
        )
    for name in _unique_tambons(zones):
        options.append(
            {"value": f"{TAMBON_PREFIX}{name}", "label": f"ต.{name}", "group": "ตำบล"}
        )
    return options


def zones_for_tambon(zones, name):
    """Zones tagged with this tambon name (several when it straddles zones)."""
    return [z for z in zones or [] if name in (z.get("tambons") or [])]


def zone_ids_for_value(zones, value):
    """Zone ids an option value stands for ([] for all areas / unknown)."""
    value = value or ""
    if value.startswith(ZONE_PREFIX):
        zone_id = value[len(ZONE_PREFIX) :]
        known = [str(z.get("id", "") or "") for z in zones or []]
        return [zone_id] if zone_id in known else []
    if value.startswith(TAMBON_PREFIX):
        name = value[len(TAMBON_PREFIX) :]
        return [str(z.get("id")) for z in zones_for_tambon(zones, name) if z.get("id")]
    return []


def merge_station_codes(zones):
    """Station codes across zones, deduplicated, first-seen order."""
    codes = []
    seen = set()
    for zone in zones or []:
        for station in zone.get("stations") or []:
            code = station.get("code") if station else None
            if not code:
                continue
            code = str(code)
            if code not in seen:
                seen.add(code)
                codes.append(code)
    return codes


def location_message(kind, zone=None, error=None):
    if kind == MSG_IN_ZONE:
        zone_name = _zone_label(zone) if zone else ""
        return f"คุณอยู่ใน {zone_name}"
    if kind == MSG_OUTSIDE:
        return (
            "ตำแหน่งของคุณอยู่นอกพื้นที่ Zone ในเขตหาดใหญ่ "
            "— เลือกพื้นที่จากรายการแทนได้"
        )
    if kind == MSG_DENIED:
        return (
            "ไม่สามารถใช้ตำแหน่งของคุณได้ กรุณาอนุญาตการเข้าถึงตำแหน่งในเบราว์เซอร์ "
            "หรือเลือกพื้นที่จากรายการแทน"
        )
    message = ""
    if error is not None:
        message = getattr(error, "message", None) or str(error)
    suffix = f" ({message})" if message else ""
    return f"ไม่สามารถระบุตำแหน่งได้{suffix} — เลือกพื้นที่จากรายการแทนได้"
