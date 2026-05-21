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


class PM01Color(MetricColor):
    def __init__(self):
        super().__init__("pm_0_1")

        # self.color_ranks = [
        #     (0, 10, "#00BFFF"),
        #     (10, 20, "#01DF3A"),
        #     (20, 30, "#FFE319"),
        #     (30, 60, "#FF8000"),
        #     (60, 1_000_000, "#FF0000"),
        # ]
        self.color_ranks = [
            (0, 2.25, "#00BFFF"),
            (2.26, 3.75, "#01DF3A"),
            (3.76, 5.63, "#FFE319"),
            (5.64, 11.25, "#FF8000"),
            (11.26, 1_000_000, "#FF0000"),
        ]


class EmpiricalForecastPM01Color(MetricColor):
    def __init__(self):
        super().__init__("pm_0_1_forecast")

        self.color_ranks = [
            (0, 2.25, "#00BFFF"),
            (2.26, 3.75, "#01DF3A"),
            (3.76, 5.63, "#FFE319"),
            (5.64, 11.25, "#FF8000"),
            (11.26, 1_000_000, "#FF0000"),
        ]


class PM1Color(MetricColor):
    def __init__(self):
        super().__init__("pm_1")

        # self.color_ranks = [
        #     (0, 10, "#00BFFF"),
        #     (10, 20, "#01DF3A"),
        #     (20, 30, "#FFE319"),
        #     (30, 60, "#FF8000"),
        #     (60, 1_000_000, "#FF0000"),
        # ]
        self.color_ranks = [
            (0, 12, "#00BFFF"),
            (12, 20, "#01DF3A"),
            (20, 30, "#FFE319"),
            (30, 60, "#FF8000"),
            (60, 1_000_000, "#FF0000"),
        ]


class PM25Color(MetricColor):
    def __init__(self):
        super().__init__("pm_2_5")


class PM25predictionColor(MetricColor):
    def __init__(self):
        super().__init__("pm_2_5_prediction")


class WindSpeedColor(MetricColor):
    def __init__(self):
        super().__init__("wind_speed")

        self.color_ranks = [
            (0, 1, "calm"),
            (1, 3, "very_light"),
            (3, 6, "light_breeze"),
            (6, 10, "gentle_breeze"),
            (10, 16, "moderate_breeze"),
            (16, 21, "fresh_breeze"),
            (21, 27, "strong_breeze"),
            (27, 33, "near_gale"),
            (33, 40, "gale"),
            (40, 47, "strong_gale"),
            (47, 55, "storm"),
            (55, 63, "violent_storm"),
            (63, 100000, "hurricane"),
        ]

    def get_color(self, value: Union[float, int, None]) -> str:
        if value is None:
            return ""
        for min_value, max_value, color in self.color_ranks:
            if min_value <= value <= max_value:
                return color
        return ""


class PM10Color(MetricColor):
    def __init__(self, type_="pm_10"):
        super().__init__(type_)

        self.color_ranks = [
            (0, 54, "#00BFFF"),
            (54.1, 154, "#01DF3A"),
            (154.1, 254, "#FFE319"),
            (254.1, 354, "#FF8000"),
            (354.1, 1_000_000, "#FF0000"),
        ]


class PM100Color(PM10Color):
    def __init__(self):
        super().__init__("pm_100")


class TemperatureColor(MetricColor):
    def __init__(self):
        super().__init__("temperature")

        self.color_ranks = [
            (0, 15, "#FE2EF7"),
            (15, 20, "#8904B1"),
            (20, 25, "#0040FF"),
            (25, 30, "#00BFFF"),
            (30, 35, "#FFE319"),
            (35, 40, "#FF8000"),
            (40, 1_000_000, "#FF0000"),
        ]


class HumidityColor(MetricColor):
    def __init__(self):
        super().__init__("humidity")

        self.color_ranks = [
            (0, 30, "#FE2EF7"),
            (30, 60, "#53B06E"),
            (60, 90, "#1CD2C7"),
            (90, 1_000_000, "#000080"),
        ]


class VOCColor(MetricColor):
    def __init__(self):
        super().__init__("voc")

        self.color_ranks = [
            (0, 66, "#00BFFF"),
            (66, 221, "#01DF3A"),
            (221, 661, "#FFE319"),
            (661, 2201, "#FF8000"),
            (2201, 1_000_000, "#FF0000"),
        ]


class COColor(MetricColor):
    def __init__(self):
        super().__init__("co")

        self.color_ranks = [
            (0, 0, "#00e400"),
            (0.0, 4.4, "#ffff00"),
            (4.4, 9.4, "#ff7e00"),
            (9.4, 12.4, "#ff0000"),
            (12.4, 15.4, "#8f3f97"),
            (15.4, 1_000_000, "#7e0023"),
        ]


class RainColor(MetricColor):
    def __init__(self):
        super().__init__("rain")

        self.color_ranks = [
            (0, 10, "#cce5ff"),
            (10, 30, "#66b2ff"),
            (30, 50, "#0073e6"),
            (50, 100, "#004080"),
            (100, 1_000_000, "#800080"),
        ]


class PressureColor(MetricColor):
    def __init__(self):
        super().__init__("pressure")

        self.color_ranks = [
            (0, 730, "#0000ff"),
            (730, 740, "#66b2ff"),
            (740, 750, "#ffffff"),
            (750, 760, "#ff9999"),
            (760, 1_000_000, "#ff0000"),
        ]


class O3Color(MetricColor):
    def __init__(self):
        super().__init__("o3")

        self.color_ranks = [
            (0, 50, "#00e400"),
            (50, 100, "#ffff00"),
            (100, 150, "#ff7e00"),
            (150, 1_000_000, "#ff0000"),
        ]


class SO2Color(MetricColor):
    def __init__(self):
        super().__init__("so2")

        self.color_ranks = [
            (0, 35, "#00e400"),
            (35, 75, "#ffff00"),
            (75, 185, "#ff7e00"),
            (185, 1_000_000, "#ff0000"),
        ]


class NO2Color(MetricColor):
    def __init__(self):
        super().__init__("no2")

        self.color_ranks = [
            (0, 53, "#00e400"),
            (53, 100, "#ffff00"),
            (100, 360, "#ff7e00"),
            (360, 649, "#ff0000"),
            (649, 1_000_000, "#8f3f97"),
        ]


class AODColor(MetricColor):
    def __init__(self):
        super().__init__("aod")

        self.color_ranks = [
            (0, 0, "#FFFFFF"),
            (0.0, 0.2, "#FFF5E1"),
            (0.2, 0.4, "#F4D88A"),
            (0.4, 0.6, "#E8A857"),
            (0.6, 0.8, "#BE5B2D"),
            (0.8, 1.0, "#5E2D16"),
        ]


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

METRIC_COLORS: List[MetricColor] = [
    PM01Color(),
    EmpiricalForecastPM01Color(),
    PM1Color(),
    PM25Color(),
    PM25predictionColor(),  # duplicate for "pm_2_5_prediction"
    PM10Color(),
    PM100Color(),
    TemperatureColor(),
    HumidityColor(),
    VOCColor(),
    COColor(),
    WindSpeedColor(),
    AODColor(),
    RainColor(),
    PressureColor(),
    COColor(),
    O3Color(),
    SO2Color(),
    NO2Color(),
    WaterLevelColor(),
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

