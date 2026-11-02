"""Compare a station's water level with its bank level.

Kept free of browser imports so the same code runs under Brython and in unit
tests. Everything shown to the public about "water vs bank" comes from here.
"""

import math

STATUS_BELOW = "below"
STATUS_NEAR = "near"
STATUS_OVERFLOW = "overflow"
STATUS_UNKNOWN = "unknown"

# Water up to this far under the bank counts as "near the bank"
NEAR_BANK_BAND_M = 1.0

# A gap this large means a wrong datum or a typo, not a real river
MAX_PLAUSIBLE_DIFF_M = 50.0

# Upstream gauges report these constants when the sensor has no reading
SENSOR_NO_DATA_VALUES = (-9.99, -999.0)

# `bank_level` is in metres above MSL, so only MSL readings can be compared.
# The ETL stores everything under `waterlevel`, and the datum depends on the
# source: DWR subtracts zflowMsl, so its value is a stage above the gauge zero.
# Comparing that with an MSL bank would falsely read as "far below the bank".
MSL_WATER_LEVEL_SOURCES = ("thaiwater", "rid")

# Raw readings the public view must not show; it shows the bank gap instead
RAW_WATER_LEVEL_METRICS = (
    "waterlevel",
    "waterlevel_msl",
    "water_level",
    "waterlevel_m",
    "wl07h",
)

_LABELS = {
    STATUS_BELOW: "ต่ำกว่าตลิ่ง",
    STATUS_NEAR: "ใกล้ระดับตลิ่ง",
    STATUS_OVERFLOW: "ล้นตลิ่ง",
    STATUS_UNKNOWN: "ไม่มีข้อมูล",
}

# (text colour, background tint)
_COLORS = {
    STATUS_BELOW: ("#15803d", "#dcfce7"),
    STATUS_NEAR: ("#a16207", "#fef9c3"),
    STATUS_OVERFLOW: ("#b91c1c", "#fee2e2"),
    STATUS_UNKNOWN: ("#475569", "#f1f5f9"),
}


def to_number(value):
    """Return `value` as a finite float, or None if it is not one."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _to_reading(value):
    number = to_number(value)
    if number is None:
        return None
    for no_data in SENSOR_NO_DATA_VALUES:
        if abs(number - no_data) < 0.001:
            return None
    return number


def has_unreliable_reading(water_level, diff, references=()):
    """Tell whether the readings are too broken to rate a station on.

    `references` are levels on the same datum as `water_level`, such as its
    warning thresholds or bank. A dead sensor must read as unknown: its constant
    sits far below every threshold, which would otherwise look like "safe".
    """
    number = to_number(water_level)
    if number is not None:
        if _to_reading(number) is None:
            return True
        for reference in references:
            level = to_number(reference)
            if level is not None and abs(number - level) > MAX_PLAUSIBLE_DIFF_M:
                return True

    gap = to_number(diff)
    return gap is not None and abs(gap) > MAX_PLAUSIBLE_DIFF_M


def _result(status, detail, diff=None, side=None):
    label = _LABELS[status]
    color, tint = _COLORS[status]
    return {
        "status": status,
        "label": label,
        "diff": diff,
        "side": side,
        "detail": detail,
        "summary": detail if detail.startswith(label) else f"{label} · {detail}",
        "color": color,
        "tint": tint,
    }


def compare_to_bank(water_level, bank_level):
    """Return the gap to the bank and its status for an MSL water level.

    Negative levels are valid: coastal gauges can sit below mean sea level.
    """
    bank = to_number(bank_level)
    if bank is None:
        return _result(STATUS_UNKNOWN, "ไม่มีข้อมูลระดับตลิ่ง")

    water = _to_reading(water_level)
    if water is None:
        return _result(STATUS_UNKNOWN, "ไม่มีข้อมูลระดับน้ำ")

    # Round before banding, so the status always agrees with the number shown
    diff = round(water - bank, 2)
    if abs(diff) > MAX_PLAUSIBLE_DIFF_M:
        return _result(STATUS_UNKNOWN, "ข้อมูลระดับน้ำผิดปกติ")

    if diff > 0:
        return _result(
            STATUS_OVERFLOW, f"สูงกว่าตลิ่ง {diff:.2f} ม.", diff, "สูงกว่าตลิ่ง"
        )
    if diff == 0:
        return _result(STATUS_NEAR, "เสมอระดับตลิ่ง", 0.0, "เสมอระดับตลิ่ง")

    status = STATUS_NEAR if diff >= -NEAR_BANK_BAND_M else STATUS_BELOW
    return _result(status, f"ต่ำกว่าตลิ่ง {abs(diff):.2f} ม.", diff, "ต่ำกว่าตลิ่ง")


def station_water_level(station):
    """Return the station's latest reading in metres above MSL, if it has one."""
    values = {}
    for metric in station.get("metrics") or []:
        if metric and isinstance(metric, dict) and metric.get("metric_type"):
            values[metric["metric_type"].lower()] = metric.get("value")

    if values.get("waterlevel_msl") is not None:
        return values["waterlevel_msl"]

    source = (station.get("source") or "").lower()
    if source in MSL_WATER_LEVEL_SOURCES:
        return values.get("waterlevel")
    return None


def compare_station(station):
    return compare_to_bank(station_water_level(station), station.get("bank_level"))
