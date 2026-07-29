HTML_METRIC_NAMES = dict(
    pm_2_5="PM<sub>2.5</sub>",
    pm_2_5_prediction="PM<sub>2.5</sub> (Prediction)",
    pm_0_1="PM<sub>0.1</sub> (linear regression)",
    pm_0_1_forecast="PM<sub>0.1</sub> (ANN)",
    pm_1="PM<sub>1</sub> (linear regression)",
    pm_10="PM<sub>10</sub>",
    pm_100="PM<sub>100</sub>",
    wind_speed="Wind Speed",
    wind_direction="Wind Direction",
    temperature="Temperture",
    humidity="Humidity",
    voc="VOC",
    co="CO",
    co2="CO<sub>2</sub>",
    so2="SO<sub>2</sub>",
    o3="O<sub>3</sub>",
    no2="NO<sub>2</sub>",
    rain="Rain",
    pressure="Pressure",
    dew_point="Dew Point",
    visible="Visible",
    water_level="Water Level",
    waterlevel="ระดับน้ำ",
    waterlevel_msl="Water Level (MSL)",
    storage_percent="Storage Percent",
    diff_wl_bank="ระดับน้ำเทียบตลิ่ง",
)

HTML_METRIC_UNITS = dict(
    pm_0_1="μg/m<sup>3</sup>",
    pm_0_1_forecast="μg/m<sup>3</sup>",
    pm_2_5="μg/m<sup>3</sup>",
    pm_2_5_prediction="μg/m<sup>3</sup>",
    pm_100="μg/m<sup>3</sup>",
    pm_10="μg/m<sup>3</sup>",
    pm_1_0="μg/m<sup>3</sup>",
    pm_1="μg/m<sup>3</sup>",
    wind_speed="knots",
    humidity="%",
    wind_direction="&deg;",
    temperature="&deg;C",
    dew_point="&deg;C",
    visible="km",
    pressure="mmHg",
    rain="mm",
    voc="ppb",
    co="ppm",
    co2="ppm",
    so2="ppb",
    o3="ppb",
    no2="ppb",
    water_level="m",
    waterlevel="ม.",
    waterlevel_msl="m(MSL)",
    storage_percent="%",
    diff_wl_bank="ม.",
)

HTML_CLIMATE_LEGENDS = dict(
    air4thai=[
        {"DES": "ดีมาก 0-15mg/m<sup>3</sup>", "fill": "#00BFFF"},
        {"DES": "ดี 15-25mg/m<sup>3</sup>", "fill": "#01DF3A"},
        {"DES": "ปานกลาง 25-37.5mg/m<sup>3</sup>", "fill": "#FFE319"},
        {"DES": "เริ่มมีผลกระทบต่อสุขภาพ 37.5-75mg/m<sup>3</sup>", "fill": "#FF8000"},
        {"DES": "มีผลกระทบต่อสุขภาพ >75mg/m<sup>3</sup>", "fill": "#FF0000"},
    ],
    santhings=[
        {"DES": "ดีมาก 0-15mg/m<sup>3</sup>", "fill": "#00BFFF"},
        {"DES": "ดี 15-25mg/m<sup>3</sup>", "fill": "#01DF3A"},
        {"DES": "ปานกลาง 25-37.5mg/m<sup>3</sup>", "fill": "#FFE319"},
        {"DES": "เริ่มมีผลกระทบต่อสุขภาพ 37.5-75mg/m<sup>3</sup>", "fill": "#FF8000"},
        {"DES": "มีผลกระทบต่อสุขภาพ >75mg/m<sup>3</sup>", "fill": "#FF0000"},
    ],
    airport=[
        {"DES": "calm", "fill": "#026701"},
        {"DES": "very light", "fill": "#099900"},
        {"DES": "gentle breeze", "fill": "#CEFF68"},
        {"DES": "moderate breeze", "fill": "#FEFF99"},
        {"DES": "fresh breeze", "fill": "#FFFF67"},
        {"DES": "strong breeze", "fill": "#FFFF01"},
        {"DES": "near gale", "fill": "#FFCB00"},
        {"DES": "gale", "fill": "#FF9900"},
        {"DES": "strong gale", "fill": "#FF3300"},
        {"DES": "storm", "fill": "#CD0001"},
        {"DES": "violent storm", "fill": "#A50022"},
        {"DES": "hurricane", "fill": "#670032"},
    ],
    PM_0_1=[
        {"DES": "ดีมาก 0-2.25µg/m<sup>3</sup>", "fill": "#00BFFF"},
        {"DES": "ดี 2.26-3.75µg/m<sup>3</sup>", "fill": "#01DF3A"},
        {"DES": "ปานกลาง 3.76-5.63µg/m<sup>3</sup>", "fill": "#FFE319"},
        {
            "DES": "เริ่มมีผลกระทบต่อสุขภาพ 5.64-11.25µg/m<sup>3</sup>",
            "fill": "#FF8000",
        },
        {"DES": "มีผลกระทบต่อสุขภาพ >11.26µg/m<sup>3</sup>", "fill": "#FF0000"},
    ],
    PM_0_1_forecast=[
        {"DES": "ดีมาก 0-2.25µg/m<sup>3</sup>", "fill": "#00BFFF"},
        {"DES": "ดี 2.26-3.75µg/m<sup>3</sup>", "fill": "#01DF3A"},
        {"DES": "สีเหลือง 3.76-5.63µg/m<sup>3</sup>", "fill": "#FFE319"},
        {
            "DES": "สีส้ม 5.64-11.25µg/m<sup>3</sup>",
            "fill": "#FF8000",
        },
        {"DES": "สีแดง >11.26µg/m<sup>3</sup>", "fill": "#FF0000"},
    ],
    PM_1=[
        {"DES": "ดีมาก 0-2.25µg/m<sup>3</sup>", "fill": "#00BFFF"},
        {"DES": "ดี 2.26-3.75µg/m<sup>3</sup>", "fill": "#01DF3A"},
        {"DES": "สีเหลือง 3.76-5.63µg/m<sup>3</sup>", "fill": "#FFE319"},
        {
            "DES": "สีส้ม 5.64-11.25µg/m<sup>3</sup>",
            "fill": "#FF8000",
        },
        {"DES": "สีแดง >11.26µg/m<sup>3</sup>", "fill": "#FF0000"},
    ],
    PM_2_5=[
        {"DES": "ดีมาก 0-15mg/m<sup>3</sup>", "fill": "#00BFFF"},
        {"DES": "ดี 15-25mg/m<sup>3</sup>", "fill": "#01DF3A"},
        {"DES": "ปานกลาง 25-37.5mg/m<sup>3</sup>", "fill": "#FFE319"},
        {"DES": "เริ่มมีผลกระทบต่อสุขภาพ 37.5-75mg/m<sup>3</sup>", "fill": "#FF8000"},
        {"DES": "มีผลกระทบต่อสุขภาพ >75mg/m<sup>3</sup>", "fill": "#FF0000"},
    ],
    PM_2_5_prediction=[
        {"DES": "ดีมาก 0-15mg/m<sup>3</sup>", "fill": "#00BFFF"},
        {"DES": "ดี 15-25mg/m<sup>3</sup>", "fill": "#01DF3A"},
        {"DES": "ปานกลาง 25-37.5mg/m<sup>3</sup>", "fill": "#FFE319"},
        {"DES": "เริ่มมีผลกระทบต่อสุขภาพ 37.5-75mg/m<sup>3</sup>", "fill": "#FF8000"},
        {"DES": "มีผลกระทบต่อสุขภาพ >75mg/m<sup>3</sup>", "fill": "#FF0000"},
    ],
    wind_direction=[
        {"DES": "calm", "fill": "#026701"},
        {"DES": "very light", "fill": "#099900"},
        {"DES": "gentle breeze", "fill": "#CEFF68"},
        {"DES": "moderate breeze", "fill": "#FEFF99"},
        {"DES": "fresh breeze", "fill": "#FFFF67"},
        {"DES": "strong breeze", "fill": "#FFFF01"},
        {"DES": "near gale", "fill": "#FFCB00"},
        {"DES": "gale", "fill": "#FF9900"},
        {"DES": "strong gale", "fill": "#FF3300"},
        {"DES": "storm", "fill": "#CD0001"},
        {"DES": "violent storm", "fill": "#A50022"},
        {"DES": "hurricane", "fill": "#670032"},
    ],
    PM_10=[
        {"DES": "ดีมาก 0-50mg/m<sup>3</sup>", "fill": "#00BFFF"},
        {"DES": "ดี 50-80mg/m<sup>3</sup>", "fill": "#01DF3A"},
        {"DES": "ปานกลาง 80-120mg/m<sup>3</sup>", "fill": "#FFE319"},
        {"DES": "เริ่มมีผลกระทบต่อสุขภาพ 120-180mg/m<sup>3</sup>", "fill": "#FF8000"},
        {"DES": "มีผลกระทบต่อสุขภาพ >180mg/m<sup>3</sup>", "fill": "#FF0000"},
    ],
    temperature=[
        {"DES": "0-15<sup>°</sup>C", "fill": "#FE2EF7"},
        {"DES": "15-20<sup>°</sup>C", "fill": "#8904B1"},
        {"DES": "20-25<sup>°</sup>C", "fill": "#0040FF"},
        {"DES": "25-30<sup>°</sup>C", "fill": "#00BFFF"},
        {"DES": "30-35<sup>°</sup>C", "fill": "#FFE319"},
        {"DES": "35-40<sup>°</sup>C", "fill": "#FF8000"},
        {"DES": ">40<sup>°</sup>C", "fill": "#FF0000"},
    ],
    humidity=[
        {"DES": "0-30 %RH", "fill": "#FE2EF7"},
        {"DES": "30-60 %RH", "fill": "#53B06E"},
        {"DES": "60-90 %RH", "fill": "#1CD2C7"},
        {"DES": ">90 %RH", "fill": "#000080"},
    ],
    rain=[
        {"DES": "0-10 mm (Light Rain)", "level": "Light", "fill": "#cce5ff"},
        {"DES": "10-30 mm (Moderate Rain)", "level": "Moderate", "fill": "#66b2ff"},
        {"DES": "30-50 mm (Heavy Rain)", "level": "Heavy", "fill": "#0073e6"},
        {
            "DES": "50-100 mm (Very Heavy Rain)",
            "level": "Very Heavy",
            "fill": "#004080",
        },
        {"DES": ">100 mm (Extreme Rain)", "level": "Extreme", "fill": "#800080"},
    ],
    pressure=[
        {"DES": "<730 mmHg (Very Low)", "level": "Very Low", "fill": "#0000ff"},
        {"DES": "730-740 mmHg (Low)", "level": "Low", "fill": "#66b2ff"},
        {"DES": "740-750 mmHg (Normal)", "level": "Normal", "fill": "#ffffff"},
        {"DES": "750-760 mmHg (High)", "level": "High", "fill": "#ff9999"},
        {"DES": ">760 mmHg (Very High)", "level": "Very High", "fill": "#ff0000"},
    ],
    CO=[
        {"DES": "0-4.4 ppm (Good)", "level": "Good", "fill": "#00e400"},
        {"DES": "4.5-9.4 ppm (Moderate)", "level": "Moderate", "fill": "#ffff00"},
        {
            "DES": "9.5-12.4 ppm (Unhealthy for Sensitive Groups)",
            "level": "USG",
            "fill": "#ff7e00",
        },
        {"DES": "12.5-15.4 ppm (Unhealthy)", "level": "Unhealthy", "fill": "#ff0000"},
        {
            "DES": ">15.5 ppm (Very Unhealthy)",
            "level": "Very Unhealthy",
            "fill": "#7e0023",
        },
    ],
    O3=[
        {"DES": "0-50 ppb (Good)", "level": "Good", "fill": "#00e400"},
        {"DES": "51-100 ppb (Moderate)", "level": "Moderate", "fill": "#ffff00"},
        {
            "DES": "101-150 ppb (Unhealthy for Sensitive Groups)",
            "level": "USG",
            "fill": "#ff7e00",
        },
        {"DES": ">150 ppb (Unhealthy)", "level": "Unhealthy", "fill": "#ff0000"},
    ],
    SO2=[
        {"DES": "0-35 ppb (Good)", "level": "Good", "fill": "#00e400"},
        {"DES": "36-75 ppb (Moderate)", "level": "Moderate", "fill": "#ffff00"},
        {
            "DES": "76-185 ppb (Unhealthy for Sensitive Groups)",
            "level": "USG",
            "fill": "#ff7e00",
        },
        {"DES": ">185 ppb (Unhealthy)", "level": "Unhealthy", "fill": "#ff0000"},
    ],
    NO2=[
        {"DES": "0-53 ppb (Good)", "level": "Good", "fill": "#00e400"},
        {"DES": "54-100 ppb (Moderate)", "level": "Moderate", "fill": "#ffff00"},
        {
            "DES": "101-360 ppb (Unhealthy for Sensitive Groups)",
            "level": "USG",
            "fill": "#ff7e00",
        },
        {"DES": "361-649 ppb (Unhealthy)", "level": "Unhealthy", "fill": "#ff0000"},
        {
            "DES": ">650 ppb (Very Unhealthy)",
            "level": "Very Unhealthy",
            "fill": "#8f3f97",
        },
    ],
    AOD=[
        {"DES": "ดีมาก 0-15mg/m<sup>3</sup>", "fill": "#00BFFF"},
        {"DES": "ดี 15-25mg/m<sup>3</sup>", "fill": "#01DF3A"},
        {"DES": "ปานกลาง 25-37.5mg/m<sup>3</sup>", "fill": "#FFE319"},
        {"DES": "เริ่มมีผลกระทบต่อสุขภาพ 37.5-75mg/m<sup>3</sup>", "fill": "#FF8000"},
        {"DES": "มีผลกระทบต่อสุขภาพ >75mg/m<sup>3</sup>", "fill": "#FF0000"},
    ],
    water_level=[
        {"DES": "ต่ำมาก (0-5 ม.)", "fill": "#9ca3af"},
        {"DES": "ปกติ (5-30 ม.)", "fill": "#22c55e"},
        {"DES": "เฝ้าระวัง (30-120 ม.)", "fill": "#eab308"},
        {"DES": "เตือนภัย (120-250 ม.)", "fill": "#f97316"},
        {"DES": "วิกฤต (>250 ม.)", "fill": "#ef4444"},
    ],
    waterlevel_msl=[
        {"DES": "ต่ำมาก (<5 ม.)", "fill": "#9ca3af"},
        {"DES": "ปกติ (5-30 ม.)", "fill": "#22c55e"},
        {"DES": "เฝ้าระวัง (30-120 ม.)", "fill": "#eab308"},
        {"DES": "เตือนภัย (120-250 ม.)", "fill": "#f97316"},
        {"DES": "วิกฤต (>250 ม.)", "fill": "#ef4444"},
    ],
    storage_percent=[
        {"DES": "น้ำน้อย (< 30%)", "fill": "#9ca3af"},
        {"DES": "ปกติ (30-50%)", "fill": "#22c55e"},
        {"DES": "เฝ้าระวัง (50-80%)", "fill": "#eab308"},
        {"DES": "เตือนภัย (80-100%)", "fill": "#f97316"},
        {"DES": "วิกฤต (เกินความจุ) (> 100%)", "fill": "#ef4444"},
    ],
    diff_wl_bank=[
        {"DES": "ปลอดภัย (<-3ม.)", "fill": "#9ca3af"},
        {"DES": "ปกติ (-3 ถึง -1ม.)", "fill": "#22c55e"},
        {"DES": "เฝ้าระวัง (-1 ถึง 0ม.)", "fill": "#eab308"},
        {"DES": "เตือนภัย (0 ถึง 1ม.)", "fill": "#f97316"},
        {"DES": "วิกฤต (ล้นตลิ่ง) (> 1ม.)", "fill": "#ef4444"},
    ],
)


HTML_CLIMATE_LEGEND_TITLES = dict(
    air4thai="PCD ความเข้มข้นของ PM<sub>2.5</sub> (หมายเหตุ สีอ้างอิงจากกรมมลพิษ)",
    santhings="Airthai ความเข้มข้นของ PM<sub>2.5</sub> (หมายเหตุ สีอ้างอิงจากกรมมลพิษ)",
    airport="Airport Wind Speed & Direction",
    PM_0_1="ความเข้มข้นของ PM<sub>0.1</sub> (หมายเหตุ 15% ของ PM2.5 แสดงถึงความสูงต่ำไม่เกี่ยวกับสุขภาพ (อยู่ระหว่างการวิจัย))",
    PM_0_1_forecast="ความเข้มข้นของ PM<sub>0.1</sub> (ANN) (หมายเหตุ 15% ของ PM2.5 แสดงถึงความสูงต่ำไม่เกี่ยวกับสุขภาพ (อยู่ระหว่างการวิจัย))",
    PM_1="ความเข้มข้นของ PM<sub>1</sub> (หมายเหตุ 80% ของ PM2.5 แสดงถึงความสูงต่ำไม่เกี่ยวกับสุขภาพ (อยู่ระหว่างการวิจัย))",
    PM_2_5="ความเข้มข้นของ PM<sub>2.5</sub> (หมายเหตุ สีอ้างอิงจากกรมมลพิษ)",
    PM_2_5_prediction="ความเข้มข้นของ PM<sub>2.5</sub> (การพยากรณ์ล่วงหน้า) (หมายเหตุ สีอ้างอิงจากกรมมลพิษ)",
    wind_direction="Wind Speed",
    PM_10="ความเข้มข้นของ PM<sub>10</sub> (หมายเหตุ สีอ้างอิงจากกรมมลพิษ)",
    temperature="Temperature",
    humidity="Humidity",
    AOD="ความเข้มข้นของ PM<sub>2.5</sub> (หมายเหตุ สีอ้างอิงจากกรมมลพิษ)",
    rain="Rainfall (mm)",
    pressure="Pressure (mmHg)",
    CO="CO Concentration (ppm)",
    O3="Ozone Concentration (ppb)",
    SO2="SO<sub>2</sub> Concentration (ppb)",
    NO2="NO<sub>2</sub> Concentration (ppb)",
    water_level="Water Level",
    waterlevel_msl="Water Level (MSL)",
    storage_percent="Storage Percent",
    diff_wl_bank="Diff WL Bank",
)

INTERPOLATION_METRIC_TYPES_WITH_LEGEND = dict(
    PM_2_5={
        "get_colors_config": lambda upper_bound: [
            (0, "#00BFFF"),
            (15, "#01DF3A"),
            (25, "#FFE319"),
            (37.5, "#FF8000"),
            (75, "#FF0000"),
            (upper_bound, "#FF0000"),
        ]
    }
)

# Data-source credits shown on marker tooltips, keyed by the lowercase
# `source` field returned by the stations API.
HTML_SOURCE_CREDITS = dict(
    thaiwater={
        "name": "สถาบันสารสนเทศทรัพยากรน้ำ (องค์การมหาชน)",
        "short": "สสน.",
    },
    rid={
        "name": "กรมชลประทาน",
        "short": "ชป.",
    },
    dwr={
        "name": "กรมทรัพยากรน้ำ",
        "short": "ทน.",
    },
    # The DWR ETL used to write this instead of plain "dwr"; kept so stations
    # ingested before the rename still get credited
    dwr_telemetry={
        "name": "กรมทรัพยากรน้ำ (โทรมาตร)",
        "short": "ทน.",
    },
)


def get_source_credit(source):
    """Return the credit info for a data source, or None when unknown."""
    if not source:
        return None
    return HTML_SOURCE_CREDITS.get(str(source).lower())


# Safety-level wording for the map legend and the station cards.
# Each list is positional: entry N describes rank N of the matching
# `metric_colors` color_ranks, so colors can never drift from the markers.
METRIC_LEVEL_TITLES = dict(
    storage_percent="ระดับปริมาณน้ำในอ่างเก็บน้ำ",
    water_level="ระดับน้ำ",
    waterlevel="ระดับน้ำ",
    waterlevel_msl="ระดับน้ำ (ม.รทก.)",
    diff_wl_bank="ระดับน้ำเทียบตลิ่ง",
)

# The metric a station is judged by, best first. The ETL writes `diff_wl_bank`
# and `waterlevel` for every source, so those carry the map; `storage_percent`
# only shows up for reservoir stations.
PRIMARY_METRIC_PREFERENCE = ["diff_wl_bank", "storage_percent", "waterlevel"]

METRIC_LEVEL_LABELS = dict(
    storage_percent=[
        {"label": "น้ำน้อยวิกฤต", "range": "< 30%", "text": "#374151"},
        {"label": "น้ำน้อย", "range": "30 - 50%", "text": "#0369a1"},
        {"label": "น้ำปกติ", "range": "50 - 80%", "text": "#0c4a6e"},
        {"label": "น้ำมาก", "range": "80 - 100%", "text": "#FFFFFF"},
        {"label": "เฝ้าระวังน้ำล้น", "range": "> 100%", "text": "#FFFFFF"},
    ],
    water_level=[
        {"label": "น้ำน้อยวิกฤต", "range": "< 5 ม.", "text": "#374151"},
        {"label": "น้ำน้อย", "range": "5 - 30 ม.", "text": "#0369a1"},
        {"label": "น้ำปกติ", "range": "30 - 120 ม.", "text": "#0c4a6e"},
        {"label": "น้ำมาก", "range": "120 - 250 ม.", "text": "#FFFFFF"},
        {"label": "เฝ้าระวัง", "range": "> 250 ม.", "text": "#FFFFFF"},
    ],
    waterlevel=[
        {"label": "น้ำน้อยวิกฤต", "range": "< 5 ม.", "text": "#374151"},
        {"label": "น้ำน้อย", "range": "5 - 30 ม.", "text": "#0369a1"},
        {"label": "น้ำปกติ", "range": "30 - 120 ม.", "text": "#0c4a6e"},
        {"label": "น้ำมาก", "range": "120 - 250 ม.", "text": "#FFFFFF"},
        {"label": "เฝ้าระวัง", "range": "> 250 ม.", "text": "#FFFFFF"},
    ],
    waterlevel_msl=[
        {"label": "น้ำน้อยวิกฤต", "range": "< 5 ม.รทก.", "text": "#374151"},
        {"label": "น้ำน้อย", "range": "5 - 30 ม.รทก.", "text": "#0369a1"},
        {"label": "น้ำปกติ", "range": "30 - 120 ม.รทก.", "text": "#0c4a6e"},
        {"label": "น้ำมาก", "range": "120 - 250 ม.รทก.", "text": "#FFFFFF"},
        {"label": "เฝ้าระวัง", "range": "> 250 ม.รทก.", "text": "#FFFFFF"},
    ],
    diff_wl_bank=[
        {"label": "ปลอดภัย", "range": "ต่ำกว่าตลิ่งเกิน 3 ม.", "text": "#0c4a6e"},
        {"label": "ปกติ", "range": "ต่ำกว่าตลิ่ง 1 - 3 ม.", "text": "#14532d"},
        {"label": "เฝ้าระวัง", "range": "ต่ำกว่าตลิ่งไม่เกิน 1 ม.", "text": "#713f12"},
        {"label": "ล้นตลิ่ง", "range": "สูงกว่าตลิ่งไม่เกิน 1 ม.", "text": "#FFFFFF"},
        {"label": "น้ำท่วม", "range": "สูงกว่าตลิ่งเกิน 1 ม.", "text": "#FFFFFF"},
    ],
)


def get_metric_levels(type_):
    """Merge `metric_colors` ranks with the Thai safety wording above.

    Returns a list of dicts with min/max/color/label/range/text so the
    legend, the station cards and the markers all read one definition.
    """
    from stations.metric_colors import get_metric_color_rank

    if not type_:
        return []

    type_ = str(type_).lower()
    ranks = get_metric_color_rank(type_)
    labels = METRIC_LEVEL_LABELS.get(type_, [])

    levels = []
    for index, rank in enumerate(ranks):
        min_value, max_value, color = rank
        info = labels[index] if index < len(labels) else {}
        levels.append(
            {
                "min": min_value,
                "max": max_value,
                "color": color,
                "label": info.get("label", ""),
                "range": info.get("range", ""),
                "text": info.get("text", "#374151"),
            }
        )
    return levels


def get_metric_level(type_, value):
    """Return the level a value falls into, or None when out of scale."""
    if value is None:
        return None

    for level in get_metric_levels(type_):
        if level["min"] <= value <= level["max"]:
            return level
    return None


def get_metric_level_title(type_):
    """Human readable title for the legend box."""
    if not type_:
        return ""
    type_ = str(type_).lower()
    return METRIC_LEVEL_TITLES.get(type_, HTML_METRIC_NAMES.get(type_, type_))


def pick_primary_metric(metrics):
    """Pick the metric a station is judged by, given a {type: value} mapping.

    Returns (type, value), or (None, None) when the station has nothing the
    colour scales know about.
    """
    if not metrics:
        return None, None

    for type_ in PRIMARY_METRIC_PREFERENCE:
        value = metrics.get(type_)
        if value is not None:
            return type_, value
    return None, None


def get_metric_fill_percent(type_, value):
    """Map a value onto 0-100 so the donut/tank/bubble markers can fill up.

    `storage_percent` is already a percentage. Everything else is placed by
    the colour band it falls in, so the marker still reads as "how severe"
    even when the metric has no natural 0-100 range.
    """
    if value is None:
        return 0

    type_ = str(type_).lower()
    if type_ == "storage_percent":
        return max(0, min(value, 100))

    levels = get_metric_levels(type_)
    if not levels:
        return 0

    for index, level in enumerate(levels):
        if level["min"] <= value <= level["max"]:
            # Centre of the band, so neighbouring bands stay visually apart
            return round((index + 0.5) / len(levels) * 100)
    return 0


# The single definition of what a risk level looks like on screen.
# `WaterMonitor.calculate_risk` decides the level; everything that draws it —
# the map markers, the station cards, the zone polygons and the legend — reads
# its colours from here, so the four can never disagree.
RISK_LEVEL_TITLE = "ระดับความปลอดภัย"

RISK_LEVELS = [
    {
        "risk": 3,
        "label": "อพยพ",
        "range": "ถึงระดับอพยพ",
        "color": "#9333ea",
        "border": "#7e22ce",
        "text": "#FFFFFF",
        "fill_opacity": 0.5,
    },
    {
        "risk": 2,
        "label": "วิกฤต",
        "range": "ถึงระดับวิกฤต",
        "color": "#ef4444",
        "border": "#dc2626",
        "text": "#FFFFFF",
        "fill_opacity": 0.4,
    },
    {
        "risk": 1,
        "label": "เฝ้าระวัง",
        "range": "ถึงระดับเฝ้าระวัง",
        "color": "#f97316",
        "border": "#ea580c",
        "text": "#FFFFFF",
        "fill_opacity": 0.3,
    },
    {
        "risk": 0,
        "label": "ปกติ",
        "range": "ต่ำกว่าระดับเฝ้าระวัง",
        "color": "#22c55e",
        "border": "#16a34a",
        "text": "#FFFFFF",
        "fill_opacity": 0.15,
    },
    {
        "risk": -1,
        "label": "ไม่ทราบสถานะ",
        "range": "ไม่มีข้อมูลใน 24 ชม.",
        "color": "#9ca3af",
        "border": "#6b7280",
        "text": "#FFFFFF",
        "fill_opacity": 0.1,
    },
]


def get_risk_level(risk):
    """Look up a risk level, falling back to the unknown one."""
    for level in RISK_LEVELS:
        if level["risk"] == risk:
            return level
    return RISK_LEVELS[-1]
