class HotspotColor:
    def __init__(self, type_="default"):
        self.type = type_
        self.color_ranks = []

    def get_color(self, value):
        for min_value, max_value, color in self.color_ranks:
            if min_value <= int(value) <= max_value:
                return color
        return "#808080"


class ModisColor(HotspotColor):
    def __init__(self):
        super().__init__("modis")

        self.color_ranks = [
            (0, 29, "#f1a7a7"),
            (30, 79, "#ea7b7b"),
            (80, 100, "#dd3131"),
        ]


class Noaa20Color(HotspotColor):
    def __init__(self):
        super().__init__("noaa-20")

        self.color_ranks = {"low": "#ffc299", "nominal": "#ff944d", "high": "#ff6600"}

    def get_color(self, value):
        return self.color_ranks[value]


class Noaa21Color(HotspotColor):
    def __init__(self):
        super().__init__("noaa-21")

        self.color_ranks = {"low": "#ffc299", "nominal": "#ff944d", "high": "#ff6600"}

    def get_color(self, value):
        return self.color_ranks[value]


class SuomiColor(HotspotColor):
    def __init__(self):
        super().__init__("suomi")

        self.color_ranks = {"low": "#ffc299", "nominal": "#ff944d", "high": "#ff6600"}

    def get_color(self, value):
        return self.color_ranks[value]


HOTSPOT_COLORS = [ModisColor(), Noaa20Color(), Noaa21Color(), SuomiColor()]


def get_hotspot_color(type_, value):
    type_ = type_.lower()
    for hotspot_color in HOTSPOT_COLORS:
        if type_ == hotspot_color.type:
            return hotspot_color.get_color(value)

    grey = "#808080"
    return grey
