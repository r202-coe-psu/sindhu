from typing import Any, List, Tuple, Union

class MetricColor:
    def __init__(self, type_: str = "default"):
        self.type = type_
        self.color_ranks: List[Tuple[Union[float, int], Union[float, int], str]] = [
            (0, 15, "#00BFFF"),
            (15, 25, "#01DF3A"),
            (25, 37.5, "#FFE319"),
            (37.5, 75, "#FF8000"),
            (75, 1_000_000, "#FF0000"),
        ]

    def get_color(self, value: Union[float, int, None]) -> str:
        if value is None:
            return "#808080"
        for min_value, max_value, color in self.color_ranks:
            if min_value <= value <= max_value:
                return color
        return "#808080"

class WaterLevelColor(MetricColor):
    def __init__(self):
        super().__init__("water_level")

        self.color_ranks = [
            (0, 5, "#FFFFFF"),
            (5, 30, "#B3E5FC"),
            (30, 120, "#4FC3F7"),
            (120, 250, "#0288D1"),
            (250, 1_000_000, "#01579B"),
        ]


class WaterLevelMSLColor(MetricColor):
    def __init__(self):
        super().__init__("waterlevel_msl")

        self.color_ranks = [
            (-1_000_000, 5, "#FFFFFF"),
            (5, 30, "#B3E5FC"),
            (30, 120, "#4FC3F7"),
            (120, 250, "#0288D1"),
            (250, 1_000_000, "#01579B"),
        ]

class StoragePercentColor(MetricColor):
    def __init__(self):
        super().__init__("storage_percent")

        self.color_ranks = [
            (0, 30, "#FFFFFF"),
            (30, 50, "#B3E5FC"),
            (50, 80, "#4FC3F7"),
            (80, 100, "#0288D1"),
            (100, 1_000_000, "#01579B"),
        ]

class DiffWLBankColor(MetricColor):
    def __init__(self):
        super().__init__("diff_wl_bank")

        self.color_ranks = [
            (-1_000_000, -3, "#00BFFF"),
            (-3, -1, "#01DF3A"),
            (-1, 0, "#FFE319"),
            (0, 1, "#FF8000"),
            (1, 1_000_000, "#FF0000"),
        ]

METRIC_COLORS: List[MetricColor] = [
    WaterLevelColor(),
    WaterLevelMSLColor(),
    StoragePercentColor(),
    DiffWLBankColor(),
]
# don't have "rain, pressure, co, o3, so3, no2"


def get_metric_color_rank(type_: str) -> List[Tuple[Union[float, int], Union[float, int], str]]:
    type_ = type_.lower()
    for metric_color in METRIC_COLORS:
        if type_ == metric_color.type:
            return metric_color.color_ranks

    return []


def get_metric_color(type_: str, value: Union[float, int, None]) -> str:
    type_ = type_.lower()
    for metric_color in METRIC_COLORS:
        if type_ == metric_color.type:
            return metric_color.get_color(value)

    grey = "#808080"
    return grey

