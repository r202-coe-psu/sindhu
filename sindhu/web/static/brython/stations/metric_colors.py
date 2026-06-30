from typing import Any, List, Tuple, Union

class MetricColor:
    def __init__(self, type_: str = "default"):
        self.type = type_
        self.color_ranks: List[Tuple[Union[float, int], Union[float, int], str, str, str]] = [
            (0, 15, "#00BFFF", "#FFFFFF", "ดีมาก"),
            (15, 25, "#01DF3A", "#FFFFFF", "ดี"),
            (25, 37.5, "#FFE319", "#374151", "ปานกลาง"),
            (37.5, 75, "#FF8000", "#FFFFFF", "เริ่มมีผลกระทบ"),
            (75, 1_000_000, "#FF0000", "#FFFFFF", "มีผลกระทบ"),
        ]

    def get_color(self, value: Union[float, int, None]) -> str:
        if value is None:
            return "#808080"
        for rank in self.color_ranks:
            min_value = rank[0]
            max_value = rank[1]
            color = rank[2]
            if min_value <= value <= max_value:
                return color
        return "#808080"

    def get_details(self, value: Union[float, int, None]) -> dict:
        if value is None:
            return {"color": "#808080", "text_color": "#FFFFFF", "label": "ไม่มีข้อมูล"}
        for rank in self.color_ranks:
            min_value = rank[0]
            max_value = rank[1]
            if min_value <= value <= max_value:
                return {
                    "color": rank[2],
                    "text_color": rank[3] if len(rank) > 3 else "#FFFFFF",
                    "label": rank[4] if len(rank) > 4 else "ปกติ",
                }
        return {"color": "#808080", "text_color": "#FFFFFF", "label": "ไม่มีข้อมูล"}


class WaterLevelColor(MetricColor):
    def __init__(self):
        super().__init__("water_level")

        self.color_ranks = [
            (0, 5, "#9ca3af", "#FFFFFF", "ต่ำมาก"),
            (5, 30, "#22c55e", "#FFFFFF", "ปกติ"),
            (30, 120, "#eab308", "#FFFFFF", "เฝ้าระวัง"),
            (120, 250, "#f97316", "#FFFFFF", "เตือนภัย"),
            (250, 1_000_000, "#ef4444", "#FFFFFF", "วิกฤต"),
        ]


class WaterLevelMSLColor(MetricColor):
    def __init__(self):
        super().__init__("waterlevel_msl")

        self.color_ranks = [
            (-1_000_000, 5, "#9ca3af", "#FFFFFF", "ต่ำมาก"),
            (5, 30, "#22c55e", "#FFFFFF", "ปกติ"),
            (30, 120, "#eab308", "#FFFFFF", "เฝ้าระวัง"),
            (120, 250, "#f97316", "#FFFFFF", "เตือนภัย"),
            (250, 1_000_000, "#ef4444", "#FFFFFF", "วิกฤต"),
        ]


class StoragePercentColor(MetricColor):
    def __init__(self):
        super().__init__("storage_percent")

        self.color_ranks = [
            (0, 30, "#9ca3af", "#FFFFFF", "น้ำน้อย"),
            (30, 50, "#22c55e", "#FFFFFF", "ปกติ"),
            (50, 80, "#eab308", "#FFFFFF", "เฝ้าระวัง"),
            (80, 100, "#f97316", "#FFFFFF", "เตือนภัย"),
            (100, 1_000_000, "#ef4444", "#FFFFFF", "วิกฤต (เกินความจุ)"),
        ]


class DiffWLBankColor(MetricColor):
    def __init__(self):
        super().__init__("diff_wl_bank")

        self.color_ranks = [
            (-1_000_000, -3, "#9ca3af", "#FFFFFF", "ปลอดภัย"),
            (-3, -1, "#22c55e", "#FFFFFF", "ปกติ"),
            (-1, 0, "#eab308", "#FFFFFF", "เฝ้าระวัง"),
            (0, 1, "#f97316", "#FFFFFF", "เตือนภัย"),
            (1, 1_000_000, "#ef4444", "#FFFFFF", "วิกฤต (ล้นตลิ่ง)"),
        ]


METRIC_COLORS: List[MetricColor] = [
    WaterLevelColor(),
    WaterLevelMSLColor(),
    StoragePercentColor(),
    DiffWLBankColor(),
]


def get_metric_color_rank(type_: str) -> List[Tuple[Union[float, int], Union[float, int], str]]:
    type_ = type_.lower()
    for metric_color in METRIC_COLORS:
        if type_ == metric_color.type:
            return [(r[0], r[1], r[2]) for r in metric_color.color_ranks]

    return []


def get_metric_color(type_: str, value: Union[float, int, None]) -> str:
    type_ = type_.lower()
    for metric_color in METRIC_COLORS:
        if type_ == metric_color.type:
            return metric_color.get_color(value)

    grey = "#808080"
    return grey


def get_metric_details(type_: str, value: Union[float, int, None]) -> dict:
    type_ = type_.lower()
    for metric_color in METRIC_COLORS:
        if type_ == metric_color.type:
            return metric_color.get_details(value)
    return {"color": "#808080", "text_color": "#FFFFFF", "label": "ไม่มีข้อมูล"}

