from datetime import datetime, timezone, timedelta
import asyncio

from urllib.parse import urlencode
import javascript as js
from browser import aio, document, html, window, alert, ajax
import datetime

from stations import (
    sensor_colors,
    sensor_infos,
    hotspot_colors,
    hotspot_infos,
    fire_report_infos,
)


# Helper
def get_nested(data, *keys, default="-"):
    """
    ฟังก์ชันช่วยดึงข้อมูลแบบปลอดภัย
    วิธีใช้: get_nested(item, "pm_2_5", "latest", "value")
    """
    for key in keys:
        if isinstance(data, dict):
            data = data.get(key)
        else:
            return default
    return data if data is not None else default


def get_color(pm25_value):

    if pm25_value:
        if pm25_value == "-":
            color = "slate"
        elif pm25_value <= 15:
            color = "blue"
        elif 15 < pm25_value <= 25:
            color = "green"
        elif 25 < pm25_value <= 37.5:
            color = "yellow"
        elif 37.5 < pm25_value <= 75:
            color = "orange"
        elif pm25_value > 75:
            color = "red"
    else:
        color = "slate"

    return f"inline-block px-3 py-1 rounded-lg bg-{color}-100 text-{color}-700"


class DashboardMonitor:
    def __init__(
        self,
        api_url,
        map_controller,
        selected_table_sensor_type,
        selected_region,
    ):

        self.running = False
        self.api_url = api_url
        self.page_size = 10
        self.get_climates_predictions_stats = (
            f"{api_url}/v1/stations/climates/predictions/stats/"
        )
        self.get_climate_last_24_hours_url = (
            f"{api_url}/v1/stations/climates/last_24_hours"
        )
        self.get_station_latest_climate_sensor_type_url = (
            f"{api_url}/v1/stations/climates/sensor_type/latest"
        )
        self.get_station_empirical_forecast_url = (
            f"{api_url}/v1/stations/climates/empirical_forecast"
        )

        # Interpolation
        self.kriging_classes = ["ordinary", "simple"]
        self.kriging_models = [
            "exp",
            "spherical",
        ]
        self.kriging_sensors = {
            "kriging_pm_2_5": "PM_2_5",
            "kriging_temperature": "temperature",
            "kriging_humidity": "humidity",
        }

        self.interpolattion_sensors = {
            "pm_2_5": "PM_2_5",
            "temperature": "temperature",
            "humidity": "humidity",
        }

        self.interpolation_params = {
            "kriging": {
                "sensor": "PM_2_5",
                "formula": "",
                "interpolate_class": "simple",
                "interpolate_model": "exp",
            },
        }

        self.get_interpolation_url = f"{api_url}/v1/interpolations/kriging/interpolate"

        self.station_objects = {}
        self.monitor_selected = None
        self.map = map_controller
        self.selected_table_sensor_type = selected_table_sensor_type
        self.selected_region = selected_region
        # PM TOP 5 Ranking
        # self.get_pm25_ranking_url = f"{api_url}/v1/stations/climates/ranking"
        self.get_ranking_pm_url = f"{api_url}/v1/stations/climates/ranking_pm"
        self.PM25_LEVELS = [
            {"max": 15, "label": "คุณภาพดีมาก", "color": "blue"},
            {"max": 25, "label": "คุณภาพดี", "color": "green"},
            {"max": 37.5, "label": "คุณภาพปานกลาง", "color": "yellow"},
            {"max": 75, "label": "มีผลกระทบ", "color": "orange"},
            {"max": float("inf"), "label": "มีผลกระทบต่อสุขภาพ", "color": "red"},
        ]

        self.PM10_LEVELS = [
            {"max": 54, "label": "คุณภาพดีมาก", "color": "blue"},
            {"max": 154, "label": "คุณภาพดี", "color": "green"},
            {"max": 254, "label": "คุณภาพปานกลาง", "color": "yellow"},
            {"max": 354, "label": "มีผลกระทบ", "color": "orange"},
            {"max": float("inf"), "label": "มีผลกระทบต่อสุขภาพ", "color": "red"},
        ]

        self.PM1_LEVELS = [
            {"max": 12, "label": "คุณภาพดีมาก", "color": "blue"},
            {"max": 20, "label": "คุณภาพดี", "color": "green"},
            {"max": 30, "label": "คุณภาพปานกลาง", "color": "yellow"},
            {"max": 60, "label": "มีผลกระทบ", "color": "orange"},
            {"max": float("inf"), "label": "มีผลกระทบต่อสุขภาพ", "color": "red"},
        ]

        self.PM01_LEVELS = [
            {"max": 2.25, "label": "คุณภาพดีมาก", "color": "blue"},
            {"max": 3.75, "label": "คุณภาพดี", "color": "green"},
            {"max": 5.63, "label": "คุณภาพปานกลาง", "color": "yellow"},
            {"max": 11.25, "label": "มีผลกระทบ", "color": "orange"},
            {"max": float("inf"), "label": "มีผลกระทบต่อสุขภาพ", "color": "red"},
        ]

        self.SENSOR_MAP = {
            "tab_pm25": "PM_2_5",
        }

        self.selected = self.SENSOR_MAP.get(self.selected_table_sensor_type, "PM_2_5")

    # PM TOP 5 Ranking
    # Create card
    def create_ranking_card(self, item, index, sensor_type, is_highest=True):
        # print("-------Create Ranking Card-------")
        station_name = item.get("station_name_th", item.get("station_id", "Unknown"))
        province = get_nested(item, "province")
        pm_value = item.get("value")

        label = "ไม่มีข้อมูล"
        color = "slate"

        if pm_value is not None:
            val = float(pm_value)

            config = self.PM25_LEVELS
            if sensor_type == "pm_10":
                config = self.PM10_LEVELS
            elif sensor_type == "pm_0_1":
                config = self.PM01_LEVELS
            elif sensor_type == "pm_1":
                config = self.PM1_LEVELS

            # print("USE CONFIG: ", sensor_type, config)

            for level in config:
                if val <= level["max"]:
                    label = level["label"]
                    color = level["color"]
                    break

        li = html.LI(Class="list-row items-center")

        set_class = "w-12 h-12 bg-green-100 text-green-600 rounded-xl flex items-center justify-center font-bold"
        if is_highest:
            set_class = "w-12 h-12 bg-red-100 text-red-600 rounded-xl flex items-center justify-center font-bold"

        li <= html.DIV(f"{index}", Class=set_class)

        # Stations name
        # li <= html.DIV(
        #     f"{station_name}",
        #     Class="flex items-center justify-start font-bold text-lg font-normal",
        # )

        station_info = html.DIV(Class="flex flex-col justify-center ml-2")

        # Station name
        station_info <= html.DIV(
            f"{station_name} ({province})",
            Class="font-bold text-lg text-slate-800 leading-tight",
        )

        # Label
        station_info <= html.DIV(label, Class="text-slate-500 font-light text-sm")

        li <= station_info

        # PM2.5 Value and label
        right_box = html.DIV(Class="flex flex-col justify-end items-end")
        set_class = f"w-fit p-3 h-fit bg-{color}-100 text-{color}-600 rounded-2xl font-bold text-md"

        right_box <= html.DIV(f"{pm_value}", Class=set_class)
        right_box <= html.DIV("µg/m³", Class="text-slate-600 font-light")
        # right_box <= html.DIV(label, Class="text-slate-600 font-light")
        li <= right_box

        return li

    def show_empty_state(self, containers):
        for container in containers:
            container.innerHTML = f"<div class='divider text-slate-500'><i class='ph ph-folder text-2xl text-slate-500'></i>ไม่มีข้อมูลในขณะนี้</div>"

    # DISPLAY
    async def display_pm25_ranking(self, selected_sensor_type):

        if selected_sensor_type == "pm_0_1":
            sensor_type = "PM_0_1_forecast"
        else:
            sensor_type = selected_sensor_type.upper()

        try:
            response = await aio.get(
                url=self.get_ranking_pm_url,
                data={"sensor_type": sensor_type},
                cache=True,
            )

            data = js.JSON.parse(response.data)
            pm_highest = data.get("highest", [])
            pm_lowest = data.get("lowest", [])

            highest_div = document["highest_container"]
            lowest_div = document["lowest_container"]

            highest_div.innerHTML = ""
            lowest_div.innerHTML = ""

            if not pm_highest and not pm_lowest:
                self.show_empty_state([highest_div, lowest_div])
                return

            for i, item in enumerate(pm_highest, 1):
                if item:
                    highest_div <= self.create_ranking_card(
                        item, i, selected_sensor_type, is_highest=True
                    )

            for i, item in enumerate(pm_lowest, 1):
                if item:
                    lowest_div <= self.create_ranking_card(
                        item, i, selected_sensor_type, is_highest=False
                    )

        except Exception as e:
            print(f"Error in display_PM_Ranking: {e}")

    # Update Detail (Table)
    # table_sensor_type
    async def update(self):
        await self.update_table_info(page_number=1)

    ## Pagination
    def render_pagination(self, data):
        nav_container = document["pagination-container"]
        nav_container.clear()

        current_page = data.get("page", 1)
        total_pages = data.get("pages", 1)

        # ฟังก์ชันนี้จะถูกเรียกเมื่อคลิกเลขหน้า
        def on_page_click(p):
            def handler(ev):
                ev.preventDefault()
                aio.run(self.fetch_all_data(page_number=p))

            return handler

        pagination_list = html.UL(Class="flex list-none rounded my-4")
        # print("DEBUG PAGINATION:", current_page, total_pages)

        if current_page > 1:
            # First page
            first_link = html.A("<< หน้าแรกสุด", Class="px-3 py-2 cursor-pointer")
            first_link.bind("click", on_page_click(1))
            pagination_list <= html.LI(first_link)

            # Previous page
            prev_link = html.A("< ก่อนหน้า", Class="px-3 py-2 cursor-pointer")
            prev_link.bind("click", on_page_click(current_page - 1))
            pagination_list <= html.LI(prev_link)

        # วนลูปสร้างเลขหน้า
        for p in range(1, total_pages + 1):
            if p >= current_page - 2 and p <= current_page + 2:
                active_style = (
                    "bg-blue-500 border rounded-xl text-white"
                    if p == current_page
                    else "bg-white"
                )
                page_link = html.A(p, Class=f"px-4 py-2 cursor-pointer {active_style}")
                page_link.bind("click", on_page_click(p))
                pagination_list <= html.LI(page_link)

        if current_page < total_pages:
            # Next page
            next_link = html.A("ถัดไป >", Class="px-3 py-2 cursor-pointer")
            next_link.bind("click", on_page_click(current_page + 1))
            pagination_list <= html.LI(next_link)

            # Last page
            last_link = html.A("หน้าสุดท้าย >>", Class="px-3 py-2 cursor-pointer")
            last_link.bind("click", on_page_click(total_pages))
            pagination_list <= html.LI(last_link)

        nav_container <= pagination_list

    async def fetch_all_data(self, page_number=1, selected_type=None):
        if selected_type is None:
            selected_type = self.SENSOR_MAP.get(
                self.selected_table_sensor_type, "PM_2_5"
            )

        # print("Fetch all data from API", page_number)
        spinner = document["loading-spinner"]
        spinner.classList.remove("hidden")

        # document["tbody_pm25"].clear()
        document["pagination-container"].clear()

        today = datetime.datetime.now().replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        try:

            # region_key = getattr(self, "selected_region", "all")
            current_region = getattr(self, "selected_region", "all")

            # ถ้าเป็น "all" ให้เป็น None เพื่อที่ API จะได้ข้ามการกรองภูมิภาค
            api_region = "" if current_region == "all" else current_region

            params = {
                "source": "air4thai",
                "sensor_type": selected_type,
                "region": api_region,
                "timestamp": today.isoformat(),
                "model": "BiLSTM",
                "page": page_number,
                "page_size": self.page_size,
            }
            # Filter

            response = await aio.get(
                url=self.get_climates_predictions_stats,
                data=params,
            )

            res_json = js.JSON.parse(response.data)
            self.all_items = res_json.get("items", [])
            self.total_items = int(res_json.get("total", 0))
            self.total_pages = int(res_json.get("pages", 1))

            await self.update_table_info(page_number, force_render=True)

        except Exception as e:
            print(f"Fetch Error: {e}")
            spinner.innerHTML = "<p class='text-red-500 font-bold p-5 text-center'>เกิดข้อผิดพลาดในการดึงข้อมูล</p>"

    ## Show Info per page
    async def update_table_info(self, page_number, force_render=False):
        selected_type = self.SENSOR_MAP.get(self.selected_table_sensor_type, "PM_2_5")

        if (not hasattr(self, "all_items") or not self.all_items) and not force_render:
            await self.fetch_all_data(page_number, selected_type)
            return

        spinner = document["loading-spinner"]
        spinner.classList.remove("hidden")

        for head in document.select(".table-header"):
            head.classList.add("hidden")

        for body in document.select(".table-body"):
            body.classList.add("hidden")
            body.clear()

        if selected_type == "PM_2_5":
            header = document["thead_pm25"]
            current_tbody = document["tbody_pm25"]
        else:
            header = document["thead_climate"]
            label = document["label_thead_climate"]
            label_avg = document["label_avg_thead_climate"]

            if selected_type == "humidity":
                label.html = "ข้อมูลล่าสุด (%)"
                label_avg.html = "เฉลี่ย 24 ชม. (%)"
            elif selected_type == "temperature":
                label.html = "ข้อมูลล่าสุด (°C)"
                label_avg.html = "เฉลี่ย 24 ชม. (°C)"

            current_tbody = document["tbody_climate"]

        header.classList.remove("hidden")
        current_tbody.classList.remove("hidden")

        if not self.all_items:
            col_span = 10 if selected_type == "PM_2_5" else 4
            current_tbody.html = f"<tr><td colspan='{col_span}' class='text-center p-10 text-gray-400'>ไม่มีข้อมูลแสดงผล</td></tr>"
        else:
            for item in self.all_items:
                self.station_objects[item["id"]] = item
                current_tbody <= self.create_dynamic_table_row(item, selected_type)

        self.render_pagination({"page": page_number, "pages": self.total_pages})
        spinner.classList.add("hidden")

    def create_dynamic_table_row(self, item, selected_type):

        ## Get Data For TD
        name_th = item.get("name_th", "-")
        province = get_nested(item, "metadata", "province")
        # print("Province", province)

        if selected_type == "PM_2_5":
            latest_value = get_nested(item, "pm_2_5", "latest", "value")
            avg_value = get_nested(item, "pm_2_5", "average_24h", "value")

        # elif selected_type == "temperature":
        # latest_value = get_nested(item, "temperature", "latest", "value")
        # avg_value = get_nested(item, "temperature", "average_24h", "value")

        # else:
        # latest_value = get_nested(item, "humidity", "latest", "value")
        # avg_value = get_nested(item, "humidity", "average_24h", "value")

        if isinstance(avg_value, (int, float)):
            display_avg = f"{avg_value:.1f}"
        else:
            display_avg = "-"

        ## Create TableRow
        table_row = html.TR(
            Class="hover:bg-gray-50 transition border-b border-gray-100"
        )
        table_row <= html.TD(f"{name_th} ({province})", Class="px-4 py-4 text-gray-800")

        if not selected_type == "PM_2_5":
            table_row <= html.TD(
                html.SPAN(latest_value, Class=get_color(latest_value)),
                Class="px-4 py-4 text-center",
            )

        table_row <= html.TD(
            html.SPAN(display_avg, Class=get_color(avg_value)),
            Class="px-4 py-4 text-center",
        )

        # Forecast 5 Days
        if selected_type == "PM_2_5":
            forecast = item.get("forecast_5d", [])
            for i in range(5):
                value = forecast[i]["value"] if i < len(forecast) else "-"
                if value == None:
                    value = "-"
                else:
                    value = round(value, 1)
                table_row <= html.TD(
                    html.SPAN(value, Class=get_color(value)),
                    Class="px-4 py-4 text-center",
                )

        # Detail Button
        detail_btn = html.TD(
            html.SPAN("ดูรายละเอียด", Class="text-blue-600 font-medium hover:underline"),
            Class="px-4 py-4 text-center cursor-pointer",
        )

        detail_btn.bind("click", lambda ev: self.open_modal(ev, item, selected_type))
        table_row <= detail_btn
        return table_row

    ## Modal
    def open_modal(self, ev, item, selected_type):
        # Open Modal
        self.fill_modal(item, selected_type)

        modal = document["modal_container"]
        modal.classList.remove("hidden")
        modal.classList.add("flex")

        document.body.style.overflow = "hidden"

        document["close_modal"].bind("click", self.close_modal)

        modal.bind("click", self.on_backdrop_click)

    def close_modal(self, ev=None):
        modal = document["modal_container"]
        modal.classList.add("hidden")
        modal.classList.remove("flex")

        # Reset Main Display
        document.body.style.overflow = ""

    def on_backdrop_click(self, ev):
        if ev.target.id == "modal_container":
            self.close_modal()

    def format_th_datetime(self, iso_ts):
        dt = datetime.datetime.fromisoformat(iso_ts)

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        bangkok_tz = timezone(timedelta(hours=7))
        dt = dt.astimezone(bangkok_tz)

        year_th = dt.year + 543

        return f"{dt.day:02d}/{dt.month:02d}/{year_th} {dt.hour:02d}:{dt.minute:02d}:{dt.second:02d}"

    # async def load_modal_charts(self, item_id, selected_type):
    #     try:
    #         tasks = [self.update_chart(item_id, "latest", selected_type)]

    #         if selected_type == "PM_2_5":
    #             tasks.append(self.update_chart(item_id, "forecast", selected_type))

    #         await asyncio.gather(*tasks)
    #     except Exception as e:
    #         print(f"Parallel loading failed: {e}")

    async def load_all_charts(self, item, selected_type):
        await self.update_chart_data(item["id"], "latest", selected_type)

        if selected_type == "PM_2_5":
            # ใช้ aio.sleep แทน asyncio.sleep
            await aio.sleep(0.2)
            await self.update_chart_data(item["id"], "forecast", selected_type)

    def fill_modal(self, item, selected_type):
        # RESET
        # document["latest_section"].classList.add("hidden")
        # document["forecast_section"].classList.add("hidden")
        # task =
        # aio.run(self.update_chart(item["id"], "latest", selected_type))
        # if selected_type == "PM_2_5":
        # aio.run(self.load_modal_charts(item["id"], selected_type))
        # aio.run(self.update_chart_data(item["id"], "latest", selected_type))
        # if selected_type == "PM_2_5":
        #     aio.run(self.update_chart_data(item["id"], "forecast", selected_type))

        aio.run(self.load_all_charts(item, selected_type))

        meta = {
            "PM_2_5": ("ph-wind", "ฝุ่น PM₂.₅", "µg/m³"),
        }

        icon, label, unit = meta.get(selected_type, ("ph-info", "ข้อมูล", ""))

        ## Get data
        name_th = item.get("name_th", "-")
        latest_value = get_nested(item, "pm_2_5", "latest", "value")
        coordinates = get_nested(item, "coordinates", "coordinates")
        area_th = get_nested(item, "metadata", "area_th")
        created_date = get_nested(item, "calculated_at")

        # body = document["modal_body"]
        # body.clear()

        # Field Data
        document["modal_title"].text = f"{label}  {name_th}"
        document["modal_coord"].text = f"พิกัด: {coordinates[0]}, {coordinates[1]}"
        document["modal_icon_title"].class_name = f"ph {icon} text-2xl text-white"
        document["modal_icon"].class_name = f"ph {icon} text-2xl text-white"
        document["modal_label"].text = f"{label} ปัจจุบัน"
        document["modal_latest"].text = f"{latest_value} {unit}"
        document["modal_area"].text = f"พื้นที่: {area_th}"
        document["modal_update_date"].text = (
            f"อัปเดตล่าสุด: {self.format_th_datetime(created_date)}"
        )

    async def update_chart_data(self, station_id, type_chart, selected_type):
        print("Update Chart Data")
        try:
            if type_chart == "latest":
                response = await aio.get(
                    url=self.get_climate_last_24_hours_url,
                    data={
                        "source": "air4thai",
                        "station": station_id,
                        "sensor_type": selected_type,
                    },
                    cache=False,
                )
                res_json = js.JSON.parse(response.data)
                data = res_json.get("history", [])

            elif type_chart == "forecast":
                station = self.station_objects.get(station_id)
                data = station["forecast_5d"]
                # print("Forecast Data:", data)

            # await asyncio.sleep(0.5)
            self.render_chart_to_ui(data, type_chart, selected_type)

        except Exception as e:
            print(f"ERROR: update_chart_data: {e}")

    def render_chart_to_ui(self, data, type_chart, selected_type):
        # 1. กำหนด ID และแสดง Section
        if type_chart == "latest":
            section = document["latest_section"]
            chart_id = "climate_chart"
        else:
            section = document["forecast_section"]
            chart_id = "forecast_chart"

        section.classList.remove("hidden")

        if not hasattr(self, "modal_charts"):
            self.modal_charts = {}

        if type_chart not in self.modal_charts:
            print(f"Initializing {type_chart} chart...")
            self.init_chart_object(chart_id, type_chart, selected_type)

        series_data = self.prepare_chart_data(data, type_chart, selected_type)

        chart_instance = self.modal_charts.get(type_chart)

        if chart_instance:
            # กำหนดชื่อ Label ให้เหมาะสม
            label_name = (
                "PM₂.₅ (µg/m³)" if selected_type == "PM_2_5" else f"{selected_type}"
            )

            # อัปเดตทั้งกราฟ
            try:
                chart_instance.updateSeries(
                    [
                        {
                            "name": label_name,
                            "data": series_data,
                        }
                    ],
                    True,
                )
                print(
                    f"Successfully updated {type_chart} series with {len(series_data)} points"
                )
            except Exception as e:
                print(f"Error updating ApexCharts: {e}")

    def init_chart_object(self, chart_id, type_chart, selected_type):
        if chart_id not in document:
            print(f"Element {chart_id} not found in document")
            return

        el = document[chart_id]
        unit = "µg/m³"

        # เลือกชนิดกราฟ: Latest เป็น Bar, Forecast เป็น Line
        chart_type = "bar" if type_chart == "latest" else "line"

        # ป้องกันกราฟซ้อน (Destroy ของเก่าถ้ามี)
        if type_chart in self.modal_charts:
            try:
                self.modal_charts[type_chart].destroy()
            except:
                pass

        options = {
            "chart": {
                "type": chart_type,
                "height": 280,
                "toolbar": {"show": False},
                "animations": {"enabled": True, "easing": "easeinout", "speed": 800},
            },
            "tooltip": {
                "shared": False,  # ป้องกันการรวม Series ซ้ำซ้อนในกรอบเดียว
                "intersect": True if chart_type == "bar" else False,
            },
            "stroke": {"curve": "smooth", "width": 3 if chart_type == "line" else 0},
            "dataLabels": {"enabled": False},
            "series": [],  # เริ่มต้นด้วยว่างเปล่า
            "xaxis": {"type": "category", "labels": {"style": {"fontSize": "12px"}}},
            "yaxis": {
                "title": {"text": unit},
            },
            "colors": ["#3b82f6"],  # สีน้ำเงินหลัก
        }

        # สร้าง Instance ใหม่
        new_chart = window.ApexCharts.new(el, options)
        new_chart.render()

        # เก็บเข้า Dictionary
        self.modal_charts[type_chart] = new_chart

    def prepare_chart_data(self, data, type_chart, selected_type):

        series_data = []

        # Latest
        if type_chart == "latest":
            bangkok_timezone = timezone(timedelta(hours=7), name="Asia/Bangkok")
            data_map = {}

            for item in data:
                dt = datetime.datetime.fromisoformat(item["timestamp"])

                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)

                dt = dt.astimezone(bangkok_timezone)

                key = dt.strftime("%Y-%m-%d %H")
                data_map[key] = item["value"]

            now = datetime.datetime.now(bangkok_timezone)

            for i in range(23, -1, -1):
                hour_dt = now - timedelta(hours=i)

                key = hour_dt.strftime("%Y-%m-%d %H")
                label = hour_dt.strftime("%H:00")

                value = data_map.get(key, 0)

                series_data.append(
                    {
                        "x": label,
                        "y": value,
                        "fillColor": (
                            sensor_colors.get_sensor_color(selected_type, value)
                            if value > 0
                            else "#E5E7EB"
                        ),
                    }
                )

        # Forecast
        elif type_chart == "forecast":
            if data is None:
                return series_data

            bangkok_timezone = timezone(timedelta(hours=7), name="Asia/Bangkok")

            for item in data:

                if item is None or item.get("value") is None:
                    continue

                try:
                    dt = datetime.datetime.fromisoformat(item["timestamp"])
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    dt = dt.astimezone(bangkok_timezone)

                    label = dt.strftime("%d %b")
                    value = round(item["value"], 1)

                    series_data.append(
                        {
                            "x": label,
                            "y": value,
                        }
                    )
                except Exception as e:
                    print(f"Error parsing item: {e}")
                    continue

        return series_data

    def init_chart(self, chart_id, type_chart, selected_type):
        units = {"PM_2_5": "µg/m³"}
        unit = units.get(selected_type, "")

        chart_type = "bar"
        if selected_type in ["temperature", "humidity"]:
            chart_type = "area"
        if type_chart == "forecast":
            chart_type = "line"

        el = window.document.querySelector(f"#{chart_id}")
        if not el:
            return

        # จัดการลบกราฟเก่าถ้ามีอยู่ (Prevent memory leak/overlap)
        chart_attr = f"new_chart_{type_chart}"
        if hasattr(self, chart_attr):
            getattr(self, chart_attr).destroy()

        self.new_chart = window.ApexCharts.new(
            el,
            {
                "chart": {
                    "type": chart_type,
                    "height": 300,
                    "toolbar": {"show": False},
                },
                "dataLabels": {"enabled": False},
                "series": [{"name": f"{selected_type} ({unit})", "data": []}],
                "xaxis": {"type": "category"},
                "yaxis": {"title": {"text": unit}},
                "stroke": {
                    "curve": "smooth" if chart_type in ["area", "line"] else "straight"
                },
            },
        )
        self.new_chart.render()
        setattr(self, chart_attr, self.new_chart)  # เก็บแยกกันระหว่าง latest กับ forecast

    def render_chart(self, data, type_chart, selected_type):

        series_data = self.prepare_chart_data(data, type_chart, selected_type)

        if selected_type == "PM_2_5":
            self.new_chart.updateSeries(
                [{"name": "PM2.5 (µg/m³)", "data": series_data}], True
            )
        elif selected_type == "temperature":
            self.new_chart.updateSeries(
                [{"name": "Temperature (°C)", "data": series_data}], True
            )
        else:
            self.new_chart.updateSeries(
                [{"name": "Humidity (%)", "data": series_data}], True
            )

    # Handle Button
    def handle_tab_click_dashboard(self, ev):
        TAB_DASHBOARD = {
            "pm_0_1": "pm_0_1",
            "pm_1": "pm_1",
            "pm_2_5": "pm_2_5",
            "pm_10": "pm_10",
        }

        doc_id = ev.target.id
        if doc_id not in TAB_DASHBOARD:
            return

        for tid in TAB_DASHBOARD.keys():
            tab = document[tid]
            if tid == doc_id:
                tab.classList.add("tab-active")
            else:
                tab.classList.remove("tab-active")

        sensor_type = TAB_DASHBOARD.get(doc_id)

        self.map.selected_sensor_type = sensor_type

        # Reset Formula
        # self.interpolation_params["kriging"]["formula"] = ""

        if sensor_type == "pm_0_1":
            self.interpolation_params["kriging"]["sensor"] = "PM_0_1_forecast"
            # self.interpolation_params["kriging"]["formula"] = ""

        elif sensor_type == "pm_1":
            self.interpolation_params["kriging"]["sensor"] = "PM_2_5"
            self.interpolation_params["kriging"]["formula"] = "PM_1_forecast"

        elif sensor_type == "pm_2_5":
            self.interpolation_params["kriging"]["sensor"] = "PM_2_5"

        elif sensor_type == "pm_10":
            self.interpolation_params["kriging"]["sensor"] = "PM_10"

        self.get_interpolation()

        aio.run(self.display_pm25_ranking(sensor_type))

    def handle_tab_click_table(self, ev):
        TAB_SENSOR_TYPE = (
            "tab_pm25",
            "tab_temperature",
            "tab_humidity",
        )

        doc_id = ev.target.id
        if doc_id not in TAB_SENSOR_TYPE:
            return

        for tid in TAB_SENSOR_TYPE:
            tab = document[tid]
            tab.classList.toggle("tab-active", tid == doc_id)

        self.map.tab_selected = doc_id

    def handle_region_change(self, ev):
        REGION_TABS = [
            "all",
            "bangkok_vicinity",
            "north",
            "northeast",
            "central_west",
            "east",
            "south",
        ]

        doc_id = ev.target.id
        selected_value = ev.target.value

        print("Element ID", doc_id)
        print("Select value:", selected_value)

        if selected_value not in REGION_TABS:
            print(f"Not Found Region: {selected_value}")
            return

        for rid in REGION_TABS:
            if rid in document:
                tab = document[rid]
                if rid == selected_value:
                    tab.classList.add("tab-active")
                else:
                    tab.classList.remove("tab-active")

        self.selected_region = selected_value
        self.all_items = []
        aio.run(self.fetch_all_data(page_number=1))

    def toggle_marker(self, is_active):
        if not self.map.current_source or not self.map.current_data:
            print("No Data For Display")
            return

        if is_active:
            aio.run(
                self.map.update_climate_marker(
                    self.map.current_source, self.map.current_data
                )
            )
        else:
            self.map.remove_climates_layer(self.map.current_source)

    def get_user_coord(self, ev):
        doc_id = ev.target.id

    def search_station(self, ev):
        doc_id = ev.target.id
        # query = document["search_input"].value.strip().capitalize()
        query = document["search_input"].value

        self.map.search_input = query

    def show_modal(self, ev):
        ev.preventDefault()

        doc_id = ev.target.id
        modal_id = f"modal_{doc_id}"

        if modal_id in document:
            document[modal_id].classList.remove("hidden")

            document.body.classList.add("overflow-hidden")

            self.bind_close_events(doc_id)

    def close_modal_card(self, doc_id):
        modal_id = f"modal_{doc_id}"
        if modal_id in document:
            document[modal_id].classList.add("hidden")
            document.body.classList.remove("overflow-hidden")

    def bind_close_events(self, doc_id):

        if f"close_btn_{doc_id}" in document:
            document[f"close_btn_{doc_id}"].bind(
                "click", lambda ev: self.close_modal_card(doc_id)
            )

        if f"close_action_{doc_id}" in document:
            document[f"close_action_{doc_id}"].bind(
                "click", lambda ev: self.close_modal_card(doc_id)
            )

    # Toggle loading Map
    def toggle_loading(self, show=True):
        """Helper function เพื่อจัดการ Loading ให้เป็นระเบียบ"""
        loader = document["loading_map"]
        if show:
            loader.classList.remove("hidden")
        else:
            loader.classList.add("hidden")

    # Interpolate
    def remove_all_interpolation_layer(self):
        for key in list(self.interpolation_params.keys()):
            self.remove_interpolation_layer(key)

    def remove_interpolation_layer(self, key):
        if key in self.map.shapes.keys():
            print(f"remove '{key}' interpolate layer New dashboard")
            self.map.map.removeLayer(self.map.shapes[key])

    def add_interpolation(
        self,
        url,
        source,
        sensor_type="",
        formula="",
        key="",
        interpolate_class="",
        interpolate_model="",
        extra_params=None,
    ):
        # print("-- Add Interpolation --")

        def interpolation_on_completed(req):
            self.toggle_loading(show=False)

            if req.status != 200 or not req.text:
                print(f"Error: Status {req.status} or Empty Response")
                # document["loading_map"].className = "hidden"
                return

            try:
                result = js.JSON.parse(req.text)
                interpolation_data = result.get("interpolation", None)
                boundary = result.get("boundary", None)
                if interpolation_data:
                    self.map.set_shape_with_key(interpolation_data, key)
                    if boundary:
                        self.map.set_shape_boundary(boundary)

            except Exception as e:
                print(f"JSON Parse Error: {e}")

            # document["loading_map"].className = "hidden"

        params = dict(
            source=source,
            sensor_type=sensor_type,
            formula=formula,
            interpolate_class=interpolate_class,
            interpolate_model=interpolate_model,
        )
        # document["loading_map"].className = "loading loading-spinner loading-sm"
        # document["loading_map"].className = "ui active inverted dimmer"
        if extra_params:
            params.update(extra_params)

        # print(f"Interpolation Request: {url}?{urlencode(params)}")

        self.toggle_loading(show=True)
        ajax.get(
            url,
            data=urlencode(params),
            oncomplete=interpolation_on_completed,
            cache=True,
        )

    def get_interpolation(self):

        mode = "kriging"

        required_fields = ["sensor", "interpolate_class", "interpolate_model"]

        params = self.interpolation_params.get(mode)
        if not params:
            print("No params found")
            return

        # required = required_fields.get(mode, [])
        # if not params or not all(params.get(k) for k in required_fields):
        #     print(f"Missing params for Kriging: {params}")
        #     return

        if not all(params.get(k) for k in required_fields):
            print(f"Missing params for Kriging: {params}")
            return

        self.remove_all_interpolation_layer()
        # self.remove_interpolation_layer(mode)

        sensor_type = self.map.selected_sensor_type

        extra_api_params = {}

        if sensor_type == "pm_0_1":
            #    print("Use PM2.5 interpolation for PM0.1")
            url = f"{self.api_url}/v1/stations/climates/empirical_forecast/interpolate"
            now_utc = datetime.datetime.now(timezone.utc)
            started_datetime = now_utc.replace(minute=0, second=0, microsecond=0)

            extra_api_params["started_datetime"] = started_datetime.strftime(
                "%Y-%m-%dT%H:%M:%S"
            )
        else:
            url = self.get_interpolation_url
        # print("before remove")

        self.add_interpolation(
            url,
            source="air4thai",
            sensor_type=params["sensor"],
            formula=params.get("formula", ""),
            key=mode,
            interpolate_class=params["interpolate_class"],
            interpolate_model=params["interpolate_model"],
            extra_params=extra_api_params,
        )
