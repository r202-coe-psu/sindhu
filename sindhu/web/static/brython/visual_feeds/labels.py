"""Thai display labels for the CCTV panel."""

THAI_DAYS_SHORT = ["จ.", "อ.", "พ.", "พฤ.", "ศ.", "ส.", "อา."]
THAI_MONTHS_SHORT = [
    "",
    "ม.ค.",
    "ก.พ.",
    "มี.ค.",
    "เม.ย.",
    "พ.ค.",
    "มิ.ย.",
    "ก.ค.",
    "ส.ค.",
    "ก.ย.",
    "ต.ค.",
    "พ.ย.",
    "ธ.ค.",
]

# Keys are the catalog's coverage_group values.
COVERAGE_LABELS = {
    "hatyai_city": "เมืองหาดใหญ่",
    "kho_hong": "คอหงส์",
    "patong": "พะตง",
    "khuan_lang": "ควนลัง",
    "pawong": "พะวง",
    "r1_drainage": "ประตูระบายน้ำ",
    "hatyai_upstream": "ต้นน้ำหาดใหญ่",
    "dwr_songkhla": "จ.สงขลา",
}


def short_date_label(day, today):
    """``20 พ.ย.``; days outside the current year add the Thai year (``68``)."""
    label = f"{day.day} {THAI_MONTHS_SHORT[day.month]}"
    if day.year != today.year:
        label += f" {(day.year + 543) % 100:02d}"
    return label


def coverage_label(group):
    group = str(group or "").strip()
    if not group:
        return "—"
    return COVERAGE_LABELS.get(group, group)
