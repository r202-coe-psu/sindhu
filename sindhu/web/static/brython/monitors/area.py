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


def _normalize_tambon_ref(item):
    """Tambon as {code, name_th, amphoe_th}; a legacy plain string is its own code."""
    if isinstance(item, str):
        return {"code": item, "name_th": item, "amphoe_th": None}
    if not item:
        return None
    code = item.get("code")
    name = item.get("name_th") or (str(code) if code else "")
    if not code and not name:
        return None
    return {
        "code": str(code if code else name),
        "name_th": name,
        "amphoe_th": item.get("amphoe_th") or None,
    }


def _zone_tambons(zone):
    return [t for t in map(_normalize_tambon_ref, zone.get("tambons") or []) if t]


def _unique_tambons(zones):
    by_code = {}
    for zone in zones or []:
        for t in _zone_tambons(zone):
            by_code.setdefault(t["code"], t)
    return sorted(
        by_code.values(), key=lambda t: (t["name_th"], t["amphoe_th"] or "", t["code"])
    )


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
    tambons = _unique_tambons(zones)
    name_counts = {}
    for t in tambons:
        if not t["amphoe_th"]:
            name_counts[t["name_th"]] = name_counts.get(t["name_th"], 0) + 1
    for t in tambons:
        label = f"ต.{t['name_th']}"
        if t["amphoe_th"]:
            label += f" (อ.{t['amphoe_th']})"
        elif name_counts.get(t["name_th"], 0) > 1:
            label += f" ({t['code']})"
        options.append(
            {"value": f"{TAMBON_PREFIX}{t['code']}", "label": label, "group": "ตำบล"}
        )
    return options


def zones_for_tambon(zones, code):
    """Zones that contain the tambon with this code."""
    code = str(code)
    return [z for z in zones or [] if any(t["code"] == code for t in _zone_tambons(z))]


def zone_ids_for_value(zones, value):
    """Zone ids an option value stands for ([] for all areas / unknown)."""
    value = value or ""
    if value.startswith(ZONE_PREFIX):
        zone_id = value[len(ZONE_PREFIX) :]
        known = [str(z.get("id", "") or "") for z in zones or []]
        return [zone_id] if zone_id in known else []
    if value.startswith(TAMBON_PREFIX):
        code = value[len(TAMBON_PREFIX) :]
        return [str(z.get("id")) for z in zones_for_tambon(zones, code) if z.get("id")]
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


def location_message(kind, zone=None, tambon=None, error=None):
    if kind == MSG_IN_ZONE:
        zone_name = _zone_label(zone) if zone else ""
        tambon_name = ""
        if tambon:
            tambon_name = tambon.get("name_th") or ""
        suffix = f" (ต.{tambon_name})" if tambon_name else ""
        return f"คุณอยู่ใน {zone_name}{suffix}"
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
