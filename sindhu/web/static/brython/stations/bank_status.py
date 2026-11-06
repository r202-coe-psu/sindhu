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

EVACUATE_OVER_BANK_M = 0.5

RISK_UNKNOWN = -1
RISK_NORMAL = 0
RISK_WATCH = 1
RISK_CRITICAL = 2
RISK_EVACUATE = 3

BANK_FROM_ADMIN = "admin"
BANK_FROM_ETL = "etl"

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
    "waterlevel_msl",
    "waterlevel",
    "water_level",
    "waterlevel_m",
)

_LABELS = {
    STATUS_BELOW: "ต่ำกว่าตลิ่ง",
    STATUS_NEAR: "ใกล้ระดับตลิ่ง",
    STATUS_OVERFLOW: "ล้นตลิ่ง",
    STATUS_UNKNOWN: "ไม่มีข้อมูล",
}

# (text colour, background tint)
_COLORS = {
    RISK_NORMAL: ("#15803d", "#dcfce7"),
    RISK_WATCH: ("#c2410c", "#ffedd5"),
    RISK_CRITICAL: ("#b91c1c", "#fee2e2"),
    RISK_EVACUATE: ("#7e22ce", "#f3e8ff"),
    RISK_UNKNOWN: ("#475569", "#f1f5f9"),
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


def risk_for_gap(diff):
    if diff is None:
        return RISK_UNKNOWN
    if diff > EVACUATE_OVER_BANK_M:
        return RISK_EVACUATE
    if diff > 0:
        return RISK_CRITICAL
    if diff >= -NEAR_BANK_BAND_M:
        return RISK_WATCH
    return RISK_NORMAL


def _result(status, detail, diff=None, side=None, show_label=True):
    label = _LABELS[status]
    risk = RISK_UNKNOWN if status == STATUS_UNKNOWN else risk_for_gap(diff)
    color, tint = _COLORS[risk]
    return {
        "status": status,
        "label": label,
        "diff": diff,
        "side": side,
        "detail": detail,
        "summary": f"{label} · {detail}" if show_label else detail,
        "risk": risk,
        "color": color,
        "tint": tint,
        "bank_source": None,
    }


def compare_to_bank(water_level, bank_level):
    """Return the gap to the bank and its status for an MSL water level.

    Negative levels are valid: coastal gauges can sit below mean sea level.
    """
    bank = to_number(bank_level)
    if bank is None:
        return _result(STATUS_UNKNOWN, "ไม่มีข้อมูลระดับตลิ่ง", show_label=False)

    water = _to_reading(water_level)
    if water is None:
        return _result(STATUS_UNKNOWN, "ไม่มีข้อมูลระดับน้ำ", show_label=False)

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

    if diff >= -NEAR_BANK_BAND_M:
        return _result(
            STATUS_NEAR, f"ต่ำกว่าตลิ่ง {abs(diff):.2f} ม.", diff, "ต่ำกว่าตลิ่ง"
        )
    return _result(
        STATUS_BELOW,
        f"ต่ำกว่าตลิ่ง {abs(diff):.2f} ม.",
        diff,
        "ต่ำกว่าตลิ่ง",
        show_label=False,
    )


def _metric_values(station):
    values = {}
    for metric in station.get("metrics") or []:
        if metric and isinstance(metric, dict) and metric.get("metric_type"):
            values[metric["metric_type"].lower()] = metric.get("value")
    return values


def raw_water_level(station):
    values = _metric_values(station)
    for metric_type in RAW_WATER_LEVEL_METRICS:
        if values.get(metric_type) is not None:
            return values[metric_type]
    return None


def station_water_level(station):
    """Return the station's latest reading in metres above MSL, if it has one."""
    values = _metric_values(station)
    if values.get("waterlevel_msl") is not None:
        return values["waterlevel_msl"]

    source = (station.get("source") or "").lower()
    if source not in MSL_WATER_LEVEL_SOURCES:
        return None
    return raw_water_level(station)


def station_bank_level(station):
    bank = to_number(station.get("bank_level"))
    if bank is not None:
        return bank, BANK_FROM_ADMIN

    source = (station.get("source") or "").lower()
    if source in MSL_WATER_LEVEL_SOURCES:
        metadata = station.get("metadata") or {}
        if isinstance(metadata, dict):
            crest = _to_reading(metadata.get("water_level_critical"))
            if crest is not None:
                return crest, BANK_FROM_ETL
    return None, None


def compare_station(station):
    bank, bank_source = station_bank_level(station)
    result = compare_to_bank(station_water_level(station), bank)
    result["bank_source"] = bank_source
    return result


def station_risk(station):
    return compare_station(station)["risk"]
