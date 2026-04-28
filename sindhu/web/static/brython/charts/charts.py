from browser import ajax, document, window, timer, html, template
import javascript
import datetime
import calendar
from stations import sensor_colors, sensor_infos


class Chart:
    def __init__(
        self,
        sensor,
        chart_time="daily",
        render_tag_id="",
        default_options="",
        lang_code="th",
    ):
        self.apexcharts = window.ApexCharts

        self.lang_code = lang_code
        self.sensor = sensor
        self.default_options = default_options
        self.render_tag_id = render_tag_id
        self.chart_time = chart_time

        self.chart = self.apexcharts.new(document[self.render_tag_id], default_options)

    def set_color_level(self, obj, *args):
        return sensor_colors.get_sensor_color(self.sensor.type, obj.value)

    async def render(self):
        self.chart.render()


class CircleChart(Chart):
    def __init__(
        self, sensor, chart_time="daily", lang_code="th", render_tag_id="circle-chart"
    ):
        self.sensor = sensor

        text_avg = dict(
            hourly={"th": "ค่าเฉลี่ยราย ชม.", "en": "Hourly average"},
            daily={"th": "ค่าเฉลี่ยรายวัน", "en": "Daily average"},
            minute={"th": "ค่าเฉลี่ยรายนาที", "en": "Minute average"},
        )

        default_options = {
            "chart": {"height": 280, "type": "radialBar"},
            "series": [0],
            "colors": ["#4B4B4B"],
            "plotOptions": {
                "radialBar": {
                    "startAngle": -110,
                    "endAngle": 110,
                    "track": {
                        "background": "#CCC",
                        "startAngle": -110,
                        "endAngle": 110,
                    },
                    "dataLabels": {
                        "name": {"show": True},
                        "value": {
                            "fontSize": "30px",
                            "show": True,
                            "formatter": self.value_format,
                        },
                    },
                }
            },
            "fill": {"colors": [self.set_color_level]},
            "stroke": {"lineCap": "butt"},
            "labels": [text_avg[chart_time][lang_code]],
            "grid": {"padding": {"bottom": -15}},
        }

        render_tag_id = render_tag_id
        super().__init__(sensor, chart_time, render_tag_id, default_options, lang_code)

    def value_format(self, value, *args):
        return "{:.1f}".format(float(value))

    async def update(self):
        if self.sensor.data[self.chart_time]:
            self.chart.updateSeries([self.sensor.data[self.chart_time][-1][1]], True)


class BarChart(Chart):
    def __init__(
        self, sensor, chart_time="daily", lang_code="th", render_tag_id="bar-chart"
    ):
        self.sensor = sensor
        chart_type = "bar"

        every = document["every"].value

        if every == "1m":
            xaxis_labels_format = "MM/yyyy"
        else:
            xaxis_labels_format = "dd/MM/yyyy"

        if every == "1w":
            xaxis = {
                "type": "categories",
            }

        else:
            xaxis = {
                "type": "datetime",
                "labels": {
                    "format": xaxis_labels_format,
                    "datetimeUTC": False,
                    "showDuplicates": False,
                },
            }

        yaxis = {
            "decimalsInFloat": 2,
            "labels": {"formatter": lambda value, *args: round(value, 2)},
            "min": 0,
        }
        x_tooltip = {"show": True, "format": "dd/MM/yyyy HH:mm"}
        if every == "1m":
            x_tooltip = {"show": True, "formatter": self.change_x_tooltip_mouth_format}

        y_tooltip = {"show": True, "formatter": self.change_y_tooltip_format}

        if chart_time == "hourly":
            xaxis_labels_format = "HH:mm"
            yaxis = {
                "decimalsInFloat": 2,
                "labels": {"formatter": lambda value, *args: round(value, 2)},
            }

            x_tooltip = {"show": True, "formatter": self.change_x_tooltip_format}
            fill = {"colors": [self.set_color_level], "opacity": 0.7}

        fill = {"colors": [self.set_color_level], "opacity": 0.7}

        default_options = {
            "dataLabels": {"distributed": True},
            "chart": {
                "height": 200,
                "width": "100%",
                "type": chart_type,
                "animations": {"initialAnimation": {"enabled": True}},
            },
            "dataLabels": {"enabled": False},
            "tooltip": {"x": x_tooltip, "y": y_tooltip},
            "series": [
                {
                    "name": sensor_infos.HTML_SENSOR_NAMES.get(sensor.type.lower(), ""),
                    "data": [],
                }
            ],
            "stroke": {"curve": "straight", "colors": "#FFFFFF"},
            "xaxis": xaxis,
            "yaxis": yaxis,
            "fill": fill,
        }

        render_tag_id = render_tag_id
        super().__init__(sensor, chart_time, render_tag_id, default_options, lang_code)

    async def update(self):
        every = document["every"].value
        datas = self.sensor.data[self.chart_time]
        climate_datas = []
        for data in datas:
            if every == "1w":
                datetime_str, week = data[-1].split()
                started_date = datetime.datetime.strptime(datetime_str, "%Y/%m/%d")
                started_date = self.get_started_datetime_of_week(started_date)
                started_date = f"{started_date.strftime('%Y-%m-%d')} W{week}"
                climate_datas.append({"x": started_date, "y": data[1]})
            else:
                climate_datas.append({"x": data[0], "y": data[1]})
        # self.chart.updateSeries([{"data": self.sensor.data[self.chart_time]}], True)
        self.chart.updateSeries([{"data": climate_datas}], True)

    def change_y_tooltip_format(self, *args):
        unit = ""
        if "pm" in self.sensor.type:
            unit = "μg/m3"
        elif "temperature" == self.sensor.type:
            unit = "°C"
        elif "humidity" == self.sensor.type:
            unit = "%"

        return "{:.2f} {}".format(float(args[0]), unit)

    def change_x_tooltip_mouth_format(self, *args):
        started_date = datetime.datetime.fromtimestamp(args[0] // 1000)
        last_day = calendar.monthrange(started_date.year, started_date.month)
        ended_date = started_date.replace(
            day=last_day[1], hour=23, minute=59, second=59
        )
        return (
            f'{started_date.strftime("%d/%m/%Y")} - {ended_date.strftime("%d/%m/%Y")}'
        )

    # สร้างฟังก์ชั่นเพื่อเอาค่าวันแรกของ สัปดาห์ โดยนับเริ่มวันอาทิตย์
    def get_started_datetime_of_week(self, started_datetime):
        if started_datetime.weekday() == 6:
            started_datetime = started_datetime
        else:
            started_datetime = started_datetime - datetime.timedelta(
                days=started_datetime.weekday() + 1
            )
        return started_datetime


class LineChartCalculateFomula(Chart):
    def __init__(
        self,
        sensor,
        sensor_type,
        chart_time="daily",
        lang_code="th",
        render_tag_id=f"line-chart",
    ):
        self.sensor = sensor
        self.chart_time = chart_time

        fill = {
            "type": "gradient",
            "gradient": {
                "shade": "light",
                "type": "vertical",
                "shadeIntensity": 0.25,
                "inverseColors": False,
                "opacityFrom": 0.7,
                "opacityTo": 0.3,
                "stops": [0, 90, 100],
            },
        }
        x_tooltip = {"show": True, "format": "dd/MM/yyyy HH:mm"}

        default_options = {
            "chart": {
                "height": 300,
                "width": "100%",
                "type": "area",
                "zoom": {"enabled": True},
                "toolbar": {
                    "show": True,
                    "tools": {
                        "zoom": True,
                        "zoomin": True,
                        "zoomout": True,
                        "pan": True,
                        "reset": True,
                    },
                },
                "animations": {"initialAnimation": {"enabled": True}},
            },
            "tooltip": {"x": x_tooltip},
            "markers": {
                "size": 0,
            },
            "dataLabels": {"enabled": False},
            "series": [
                {"name": sensor_infos.HTML_SENSOR_NAMES[sensor_type], "data": []}
            ],
            "stroke": {
                "curve": "smooth",
                "colors": ["#008FFB"],
                "width": 2,
            },
            "xaxis": {
                "type": "datetime",
                "labels": {
                    "datetimeUTC": False,
                    "showDuplicates": False,
                    "format": "dd/MM/yyyy",
                },
            },
            "yaxis": {
                "decimalsInFloat": 2,
                "labels": {"formatter": lambda value, *args: round(value, 2)},
            },
            "fill": fill,
        }

        render_tag_id = render_tag_id
        super().__init__(sensor, chart_time, render_tag_id, default_options, lang_code)

    async def update(self):
        formatted_data = [
            {"x": data["timestamp"], "y": data["calculate_value"]}
            for data in self.sensor["climates"]
        ]
        self.chart.updateSeries([{"data": formatted_data}], True)

    def change_y_tooltip_format(self, *args):
        unit = ""
        if "pm" in self.sensor.type:
            unit = "μg/m3"
        elif "temperature" == self.sensor.type:
            unit = "°C"
        elif "humidity" == self.sensor.type:
            unit = "%"

        return "{:.2f} {}".format(float(args[0]), unit)


class LineChart(Chart):
    def __init__(
        self, sensor, chart_time="daily", lang_code="th", render_tag_id=f"line-chart"
    ):
        self.sensor = sensor

        # daily
        xaxis_labels_format = "dd/MM/yyyy"
        yaxis = {
            "decimalsInFloat": 2,
            "labels": {"formatter": lambda value, *args: round(value, 2)},
            "min": 0,
        }

        chart_type = "line"
        x_tooltip = {"show": True, "format": "dd/MM/yyyy HH:mm"}
        fill = {"colors": [self.set_color_level], "opacity": 0.7}

        if chart_time == "hourly":
            xaxis_labels_format = "HH:mm"
            yaxis = {
                "decimalsInFloat": 2,
                "labels": {"formatter": lambda value, *args: round(value, 2)},
            }

            x_tooltip = {"show": True, "formatter": self.change_x_tooltip_format}
            fill = {"colors": [self.set_color_level], "opacity": 0.7}

        y_tooltip = {"show": True, "formatter": self.change_y_tooltip_format}

        default_options = {
            "chart": {
                "height": 200,
                "width": "100%",
                "type": chart_type,
                "animations": {"initialAnimation": {"enabled": True}},
            },
            "dataLabels": {"enabled": False},
            "tooltip": {"x": x_tooltip, "y": y_tooltip},
            "series": [
                {"name": sensor_infos.HTML_SENSOR_NAMES[sensor.type], "data": []}
            ],
            "stroke": {"curve": "straight", "colors": "#FFFFFF"},
            "xaxis": {
                "type": "datetime",
                "labels": {
                    "format": xaxis_labels_format,
                    "datetimeUTC": False,
                    "showDuplicates": False,
                },
            },
            "yaxis": yaxis,
            "fill": fill,
        }

        render_tag_id = render_tag_id
        super().__init__(sensor, chart_time, render_tag_id, default_options, lang_code)

    async def update(self):
        self.chart.updateSeries(
            [{"data": self.sensor.data[self.chart_time][:-1]}], True
        )

    def change_x_tooltip_format(self, *args):
        timestamp = datetime.datetime.fromtimestamp(args[0] // 1000)
        endtime = timestamp + datetime.timedelta(minutes=59)
        return "{:%d/%m/%Y %H:%M} - {:%H:%M}".format(timestamp, endtime)

    def change_y_tooltip_format(self, *args):
        unit = ""
        if "pm" in self.sensor.type:
            unit = "μg/m3"
        elif "temperature" == self.sensor.type:
            unit = "°C"
        elif "humidity" == self.sensor.type:
            unit = "%"

        return "{:.2f} {}".format(float(args[0]), unit)


class AreaChart(Chart):
    def __init__(
        self, sensor, chart_time="daily", lang_code="th", render_tag_id="area-chart"
    ):
        self.sensor = sensor
        self.chart_time = chart_time

        # daily
        xaxis_labels_format = "dd/MM/yyyy HH:mm"
        yaxis = {
            "decimalsInFloat": 2,
            "labels": {"formatter": lambda value, *args: round(value, 2)},
            "min": 0,
        }

        chart_type = "area"
        x_tooltip = {"show": True, "format": "dd/MM/yyyy HH:mm"}
        fill = {
            "type": "gradient",
            "gradient": {
                "type": "vertical",
                "shadeIntensity": 1,
                "opacityFrom": 1,
                "opacityTo": 1,
                "colorStops": self.set_color_level_gradient(),
            },
        }

        if "pm" in self.sensor.type:
            yaxis = {
                "tickAmount": 5,
                "min": 0,
                "decimalsInFloat": 2,
                "labels": {"formatter": lambda value, *args: round(value, 2)},
            }

        y_tooltip = {"show": True, "formatter": self.change_y_tooltip_format}
        default_options = {
            "chart": {
                "height": 200,
                "width": "100%",
                "type": chart_type,
                "animations": {"initialAnimation": {"enabled": True}},
            },
            "dataLabels": {"enabled": False},
            "tooltip": {"x": x_tooltip, "y": y_tooltip},
            "series": [
                {"name": sensor_infos.HTML_SENSOR_NAMES[sensor.type], "data": []}
            ],
            "stroke": {"curve": "straight", "colors": "#FFFFFF"},
            "xaxis": {
                "type": "datetime",
                "labels": {
                    "format": xaxis_labels_format,
                    "datetimeUTC": False,
                    "showDuplicates": False,
                },
            },
            "yaxis": yaxis,
            "fill": fill,
        }

        render_tag_id = render_tag_id
        super().__init__(sensor, chart_time, render_tag_id, default_options, lang_code)

    async def update(self):
        self.chart.updateSeries(
            [{"data": self.sensor.data[self.chart_time][:-1]}], True
        )

    def change_x_tooltip_format(self, *args):
        timestamp = datetime.datetime.fromtimestamp(args[0] // 1000)
        endtime = timestamp + datetime.timedelta(minutes=59)
        return "{:%d/%m/%Y %H:%M} - {:%H:%M}".format(timestamp, endtime)

    def change_y_tooltip_format(self, *args):
        unit = sensor_infos.HTML_SENSOR_UNITS.get(self.sensor.type.lower(), "")
        return "{:.2f} {}".format(float(args[0]), unit)

    def set_color_level_gradient(self):
        color_stops = []

        vals = []
        for val in self.sensor.data[self.chart_time]:
            vals.append(val[1])
        max_val = max(vals)

        for min_value, max_value, color in sensor_colors.get_sensor_color_rank(
            self.sensor.type
        ):
            if max_value <= max_val:
                color_stops.append(
                    {"offset": min_value, "color": color, "opacity": 0.7}
                )
                color_stops.append(
                    {"offset": max_value, "color": color, "opacity": 0.7}
                )

        color_stops.reverse()

        return color_stops


class StationChartRenderer:
    def __init__(self, sensors, lang_code):
        self.lang_code = lang_code
        self.sensors = sensors
        self.charts = []
        self.lang_code = lang_code

        self.set_up()

    def set_up(self):
        container = document["chart-container"]
        chart_container = document["{ sensor_type }-chart-container"]
        chart_container.style["display"] = "block"
        container.clear()

        DISPLAY_ORDERS = sensor_infos.HTML_SENSOR_NAMES.keys()

        for key in self.sensors.keys():
            if key.lower() in DISPLAY_ORDERS:
                continue

            # DISPLAY_ORDERS.append(key)

        for type_ in DISPLAY_ORDERS:
            if type_.lower() not in self.sensors:
                continue

            sensor = self.sensors.get(type_)

            chart = chart_container.cloneNode(True)
            chart.id = f"{ type_ }-chart-container"
            chart.select_one("#sensor_type-chart").id = f"{ type_ }-chart"

            element = chart.select_one("#sensor_type-head")
            element.id = f"{ type_ }-head"
            element.html = element.html.replace(
                "{ sensor_name }",
                sensor_infos.HTML_SENSOR_NAMES.get(sensor.type.lower(), ""),
            ).replace(
                "{ unit }",
                sensor_infos.HTML_SENSOR_UNITS.get(sensor.type.lower(), sensor.unit),
            )

            element = chart.select_one("#sensor_type-loader")
            element.id = f"{ type_ }-loader"

            container <= chart

    async def update(self):
        for chart in self.charts:
            await chart.update()

    async def render(self):
        for type_, sensor in self.sensors.items():
            disable_loader_id = f"{sensor.type}-loader"
            if disable_loader_id not in document:
                continue

            document[disable_loader_id].attrs["class"] = "ui disabled loader"

            # chart_label_id = f"{sensor.type}-label_now-{chart_time}"
            # if chart_label_id not in document:
            #     continue

            # if chart_time == "daily" and chart_label_id in document:
            #     chart_label_element = document[chart_label_id]
            #     chart_label_element.style["display"] = "block"

            # chart = CircleChart(sensor, chart_time, self.lang_code)
            # self.charts.append(chart)
            # await chart.render()

            # if chart_time == "minute":
            #     chart = AreaChart(sensor, chart_time, self.lang_code)
            # else:
            chart = BarChart(sensor, "daily", self.lang_code, f"{ type_ }-chart")

            self.charts.append(chart)
            await chart.render()


class CalculateFomulaChartRenderer:
    def __init__(self, sensors, lang_code, sensor_type):
        self.lang_code = lang_code
        self.sensors = sensors
        self.sensor_type = sensor_type
        self.charts = []
        self.lang_code = lang_code

        self.set_up()

    def set_up(self):
        container = document["chart-container"]
        chart_container = document["{ sensor_type }-chart-container"]
        chart_container.style["display"] = "block"
        container.clear()

        unit = "test"

        chart = chart_container.cloneNode(True)
        chart.id = f"{ self.sensor_type }-chart-container"
        chart.select_one("#sensor_type-chart").id = f"{ self.sensor_type }-chart"

        element = chart.select_one("#sensor_type-head")
        element.id = f"{ self.sensor_type }-head"
        element.html = element.html.replace(
            "{ sensor_name }",
            sensor_infos.HTML_SENSOR_NAMES.get(self.sensor_type.lower(), ""),
        ).replace(
            "{ unit }",
            sensor_infos.HTML_SENSOR_UNITS.get(self.sensor_type.lower(), unit),
        )

        element = chart.select_one("#sensor_type-loader")
        element.id = f"{ self.sensor_type }-loader"

        container <= chart

    async def update(self):
        for chart in self.charts:
            await chart.update()

    async def render(self):
        sensor_type = self.sensor_type
        disable_loader_id = f"{sensor_type}-loader"

        if disable_loader_id in document:
            document[disable_loader_id].attrs["class"] = "ui disabled loader"

        chart = LineChartCalculateFomula(
            self.sensors, sensor_type, "daily", self.lang_code, f"{ sensor_type }-chart"
        )

        self.charts.append(chart)
        await chart.render()
