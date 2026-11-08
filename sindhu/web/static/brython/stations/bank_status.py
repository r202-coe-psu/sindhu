"""Compare a station's water level with its bank level.

Kept free of browser imports so the same code runs under Brython and in unit
tests. Everything shown to the public about "water vs bank" comes from here.
"""

import math

STATUS_BELOW = "below"
STATUS_NEAR = "near"
STATUS_OVERFLOW = "overflow"
STATUS_UNKNOWN = "unknown"

DEFAULT_NEAR_BAND_M = 1.0

RISK_UNKNOWN = -1
RISK_NORMAL = 0
RISK_WATCH = 1
RISK_CRITICAL = 2

GAP_FROM_ADMIN = "admin"
GAP_FROM_ETL_DIFF = "etl_diff"
GAP_FROM_ETL_BANK = "etl_bank"

# A gap this large means a wrong datum or a typo, not a real river
MAX_PLAUSIBLE_DIFF_M = 50.0

# Upstream gauges report these constants when the sensor has no reading
SENSOR_NO_DATA_VALUES = (-9.99, -999.0)

BANK_LEVEL_MIN_M = -20.0
BANK_LEVEL_MAX_M = 3000.0

MSL_WATER_LEVEL_SOURCES = ("thaiwater", "rid")
DWR_SOURCES = ("dwr", "dwr_telemetry")
CRITICAL_LEVEL_SOURCES = ("thaiwater", "rid")
THAIWATER_GENERATED_WARNING_RATIO = 0.8

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

_RISKS = {
    STATUS_BELOW: RISK_NORMAL,
    STATUS_NEAR: RISK_WATCH,
    STATUS_OVERFLOW: RISK_CRITICAL,
    STATUS_UNKNOWN: RISK_UNKNOWN,
}

# (text colour, background tint)
_COLORS = {
    RISK_NORMAL: ("#15803d", "#dcfce7"),
    RISK_WATCH: ("#c2410c", "#ffedd5"),
    RISK_CRITICAL: ("#b91c1c", "#fee2e2"),
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


def _to_level(value):
    level = _to_reading(value)
    if level is None or level == 0:
        return None
    if not BANK_LEVEL_MIN_M <= level <= BANK_LEVEL_MAX_M:
        return None
    return level


def admin_bank_level(value):
    return _to_level(value)


def _metadata(station):
    metadata = station.get("metadata")
    return metadata if isinstance(metadata, dict) else {}


def _source(station):
    return (station.get("source") or "").lower()


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
    msl = _to_reading(values.get("waterlevel_msl"))
    if msl is not None:
        return msl

    source = _source(station)
    if source in MSL_WATER_LEVEL_SOURCES:
        return _to_reading(raw_water_level(station))
    if source in DWR_SOURCES:
        stage = _to_reading(values.get("waterlevel"))
        gauge_zero = _to_reading(_metadata(station).get("zflowMsl"))
        if stage is not None and gauge_zero is not None:
            return round(stage + gauge_zero, 4)
    return None


def etl_bank_level(station):
    metadata = _metadata(station)
    source = _source(station)
    if source in CRITICAL_LEVEL_SOURCES:
        return _to_level(metadata.get("water_level_critical"))
    if source in DWR_SOURCES:
        banks = [_to_level(metadata.get(key)) for key in ("lbMsl", "rbMsl")]
        banks = [bank for bank in banks if bank is not None]
        return min(banks) if banks else None
    return None


def etl_bank_gap(station):
    values = _metric_values(station)
    diff = _to_reading(values.get("diff_wl_bank"))
    if diff is None:
        return None
    raw_water = to_number(raw_water_level(station))
    if raw_water is not None and _to_reading(raw_water) is None:
        return None
    if _source(station) == "rid":
        critical = _to_reading(_metadata(station).get("water_level_critical"))
        water = _to_reading(values.get("waterlevel"))
        built_on_zero_bank = critical == 0
        if built_on_zero_bank or (water is not None and abs(diff - water) < 0.005):
            return None
    return diff


def near_bank_band(station):
    metadata = _metadata(station)
    critical = _to_level(metadata.get("water_level_critical"))
    warning = _to_level(metadata.get("water_level_warning"))
    if critical is None or warning is None or warning >= critical:
        return DEFAULT_NEAR_BAND_M
    if _source(station) == "thaiwater":
        generated = critical * THAIWATER_GENERATED_WARNING_RATIO
        if abs(warning - generated) < 1e-6:
            return DEFAULT_NEAR_BAND_M
    return round(critical - warning, 2)


def _result(status, detail, diff=None, side=None, show_label=True):
    label = _LABELS[status]
    risk = _RISKS[status]
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
        "gap_source": None,
        "near_band": None,
    }


def status_for_gap(diff, near_band=DEFAULT_NEAR_BAND_M):
    diff = round(diff, 2)
    if diff > 0:
        result = _result(
            STATUS_OVERFLOW, f"สูงกว่าตลิ่ง {diff:.2f} ม.", diff, "สูงกว่าตลิ่ง"
        )
    elif diff == 0:
        result = _result(STATUS_NEAR, "เสมอระดับตลิ่ง", 0.0, "เสมอระดับตลิ่ง")
    elif diff >= -near_band:
        result = _result(
            STATUS_NEAR, f"ต่ำกว่าตลิ่ง {abs(diff):.2f} ม.", diff, "ต่ำกว่าตลิ่ง"
        )
    else:
        result = _result(
            STATUS_BELOW,
            f"ต่ำกว่าตลิ่ง {abs(diff):.2f} ม.",
            diff,
            "ต่ำกว่าตลิ่ง",
            show_label=False,
        )
    result["near_band"] = near_band
    return result


def compare_to_bank(water_level, bank_level, near_band=DEFAULT_NEAR_BAND_M):
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
    return status_for_gap(diff, near_band)


def _plausible(diff):
    return diff is not None and abs(diff) <= MAX_PLAUSIBLE_DIFF_M


def station_gap(station):
    water = station_water_level(station)

    admin_bank = admin_bank_level(station.get("bank_level"))
    if admin_bank is not None and water is not None:
        diff = round(water - admin_bank, 2)
        if _plausible(diff):
            return diff, GAP_FROM_ADMIN

    diff = etl_bank_gap(station)
    if _plausible(diff):
        return round(diff, 2), GAP_FROM_ETL_DIFF

    etl_bank = etl_bank_level(station)
    if etl_bank is not None and water is not None:
        diff = round(water - etl_bank, 2)
        if _plausible(diff):
            return diff, GAP_FROM_ETL_BANK

    return None, None


def compare_station(station):
    diff, gap_source = station_gap(station)
    if diff is None:
        has_bank = (
            admin_bank_level(station.get("bank_level")) is not None
            or etl_bank_level(station) is not None
        )
        if not has_bank:
            return _result(STATUS_UNKNOWN, "ไม่มีข้อมูลระดับตลิ่ง", show_label=False)
        if station_water_level(station) is None:
            return _result(STATUS_UNKNOWN, "ไม่มีข้อมูลระดับน้ำ", show_label=False)
        return _result(STATUS_UNKNOWN, "ข้อมูลระดับน้ำผิดปกติ")

    result = status_for_gap(diff, near_bank_band(station))
    result["gap_source"] = gap_source
    return result


def station_risk(station):
    return compare_station(station)["risk"]
