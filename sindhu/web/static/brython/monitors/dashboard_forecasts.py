from browser import aio, document, window, alert, ajax
from datetime import datetime, timezone, timedelta
import javascript as js
from urllib.parse import urlencode

from monitors.base import BaseMonitor
from stations import sensor_colors


class DashboardForecastMonitor(BaseMonitor):
    def __init__(self, lang_code, api_url, source, center=None, zoom=None):
        super().__init__(
            lang_code=lang_code,
            api_url=api_url,
            source=source,
            center=center,
            zoom=zoom,
        )

        self.monitor_name = "dashboard_forecasts"
        self.selected_forecast = "PM_2_5_prediction"

        self.climates = None
        self.forecast_days = self.setup_forecast_range()

        # แก้ไขการสร้าง Datetime Object
        first_day_str = self.forecast_days[0].replace("predict_date_", "")
        self.base_predict_date = datetime.strptime(first_day_str, "%Y-%m-%d")

        self.started_datetime = self.base_predict_date
        self.target_timestamp = self.base_predict_date

        # parameters for API calls
        self.params = {
            "source": self.source,
            "predict_date": self.base_predict_date.isoformat(),
            "sensor_type": "PM_2_5",
            "model": "BiLSTM",
        }

        self.interpolation_params["kriging"].update(
            {
                "sensor": "PM_2_5_prediction",
                "formula": "",
                "interpolate_class": "simple",
                "interpolate_model": "exp",
            }
        )

        # Update API endpoints for forecasts
        self.apis["stations"]["climates"].update(
            {
                "predictions": {
                    "root": f"{api_url}/v1/stations/climates/predictions/",
                    "interpolate": f"{api_url}/v1/stations/climates/predictions/interpolate/",
                }
            }
        )

    # ========== 1. Setup and Initialization ==========
    async def setup(self):
        """Override setup to use MainDashboardMap instead of MainMap."""
        response = await aio.get(self.apis["system_settings"], cache=True)
        self.system_setting = js.JSON.parse(response.data)

        center = self.system_setting["center"]["coordinates"]
        zoom = self.system_setting["zoom"]
        min_zoom = self.system_setting["min_zoom"]

        from maps.main_dashboard import MainDashboardMap

        self.map = MainDashboardMap(
            [15.0, 101.0], 5.4, min_zoom, self.lang_code, self.api_url
        )

        self.map.set_on_station_click_listener(self.handle_station_click)
        self.init_chart()

    def set_map_loading(self, loading):
        """Override Loading ของคลาสแม่ เพื่อรองรับ Tailwind CSS"""
        loader = document["loading_map"]
        if loading:
            loader.classList.remove("hidden")
        else:
            loader.classList.add("hidden")

    def setup_forecast_range(self):
        forecast_days = datetime.now() + timedelta(days=1)
        forecast_days = forecast_days.replace(hour=0, minute=0, second=0, microsecond=0)
        return [
            f"predict_date_{(forecast_days + timedelta(days=i)).strftime('%Y-%m-%d')}"
            for i in range(5)
        ]

    def start(self):
        self.running = True
        self.setup_events()
        aio.run(self.monitor())

    # Main Life Cycle
    async def monitor(self):
        await self.setup()

        print("Initializing first day forecast")
        document[self.forecast_days[0]].classList.add(
            "btn-active", "bg-blue-100", "text-blue-700"
        )
        self.fetch_futureforecast(predict_date=self.base_predict_date)

        while self.running:
            print(f"monitor: wake up {datetime.now()}")
            print(f"monitor: sleep {self.acquisition_interval}s")
            await aio.sleep(self.acquisition_interval)

    # ========== 2. Data Fetching and Map Rendering ==========
    def fetch_futureforecast(self, predict_date):
        url = self.apis["stations"]["climates"]["predictions"]["root"]
        self.set_map_loading(True)

        def climates_on_completed(req):
            self.climates = js.JSON.parse(req.text)
            self.render_map_for_date(predict_date)
            # ไม่ต้องใส่ self.set_map_loading(False) ให้ base.py ปิดให้ตอนทำ interpolate เสร็จ

        ajax.get(
            url,
            data=urlencode(self.params),
            oncomplete=climates_on_completed,
            cache=True,
        )

    def render_map_for_date(self, target_timestamp):
        if not self.climates:
            self.set_map_loading(False)  # ดักไว้เผื่อไม่มีข้อมูล จะได้ไม่ค้าง
            return

        # Markers
        aio.run(
            self.map.update(
                self.selected_forecast,
                self.climates,
                target_timestamp=target_timestamp,
            )
        )

        # Interpolation Map
        url = self.apis["stations"]["climates"]["predictions"]["interpolate"]
        extra_params = {
            "predict_date": self.started_datetime.isoformat(),
            "target_timestamp": target_timestamp.isoformat(),  # ใช้ค่าจาก parameter
        }

        # ฟังก์ชันนี้จะทำหน้าที่โหลดแผนที่สี และปิด Loading ให้อัตโนมัติเมื่อเสร็จ
        self.set_interpolation(
            url=url,
            sensor_type="PM_2_5_prediction",
            mode="kriging",
            extra_params=extra_params,
        )

    # ========== 3. UI Events ==========
    def setup_events(self):
        # ผูกปุ่มเปลี่ยนวัน
        for day_id in self.forecast_days:
            if day_id in document:
                document[day_id].bind("click", self.on_forecast_date_changed)

        # ผูกปุ่มสวิตช์เปิดปิดจุดตรวจวัด
        if "toggle_marker" in document:
            document["toggle_marker"].bind("click", self.on_toggle_marker_clicked)

    def on_toggle_marker_clicked(self, ev):
        is_active = ev.target.checked
        self.map.toggle_layers(is_active)

    def on_forecast_date_changed(self, ev):
        clicked_id = ev.target.id
        date_string = clicked_id.replace("predict_date_", "")
        target_timestamp = datetime.strptime(date_string, "%Y-%m-%d")

        if target_timestamp == self.target_timestamp:
            return

        for day_id in self.forecast_days:
            if day_id in document:
                document[day_id].classList.remove(
                    "btn-active", "bg-blue-100", "text-blue-700"
                )
        ev.target.classList.add("btn-active", "bg-blue-100", "text-blue-700")

        self.target_timestamp = target_timestamp

        self.set_map_loading(True)
        self.remove_all_interpolation_layer()

        # สั่งวาดแผนที่ และปล่อยให้ฟังก์ชันข้างในปิด Loading เองเมื่อจบงาน
        self.render_map_for_date(target_timestamp)

    # ========== 4. Chart Logic ==========
    def init_chart(self):
        chart_el = document.querySelector("#pm25-chart")
        if not chart_el:
            return

        options = {
            "chart": {"type": "bar", "height": 300, "toolbar": {"show": False}},
            "dataLabels": {"enable": False},
            "series": [{"name": "PM2.5", "data": []}],
            "xaxis": {"categories": []},
            "yaxis": {"title": {"text": "PM₂.₅ (µg/m³)"}},
            "plotOptions": {"bar": {"borderRadius": 4}},
        }

        self.pm_chart = window.ApexCharts.new(
            chart_el, window.JSON.parse(window.JSON.stringify(options))
        )
        self.pm_chart.render()

    async def handle_station_click(self, station_id, station_data):
        if "panel_empty_state" in document:
            document["panel_empty_state"].classList.add("hidden")
        if "panel_content_state" in document:
            document["panel_content_state"].classList.remove("hidden")

        if station_data:
            document["panel_name_th"].text = station_data.get("name_th", "-")
            document["province"].text = station_data.get("metadata", {}).get(
                "province", "-"
            )

        await self.update_chart(station_id)

    async def update_chart(self, station_id):
        if not self.climates:
            return

        stations = self.climates.get("stations", [])
        target_station = next((s for s in stations if s.get("id") == station_id), None)

        if target_station:
            climates = target_station.get("climates", [])
            series_data, categories = self.prepare_chart_data(climates)

            if self.pm_chart:
                self.pm_chart.updateSeries(
                    [{"name": "PM₂.₅ Prediction", "data": series_data}]
                )
                self.pm_chart.updateOptions({"xaxis": {"categories": categories}})

    def prepare_chart_data(self, data):
        bangkok_tz = timezone(timedelta(hours=7))

        series_data = []
        categories = []

        predictions = [
            item for item in data if item.get("sensor_type") == "pm_2_5_prediction"
        ]

        predictions.sort(key=lambda x: x.get("timestamp", ""))

        for item in predictions:
            val = item.get("value", 0)
            timestamp_str = item.get("timestamp", "")

            if val is None:
                val = 0

            try:
                dt = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
                dt = dt.astimezone(bangkok_tz)
                date_label = dt.strftime("%d %b")
            except Exception as e:
                print(f"Date parsing error: {e}")
                date_label = timestamp_str

            color = sensor_colors.get_sensor_color("PM_2_5", val)

            categories.append(date_label)
            series_data.append(
                {
                    "x": date_label,
                    "y": float(val),
                    "fillColor": color,
                }
            )

        js_series = window.JSON.parse(window.JSON.stringify(series_data))
        return js_series, categories

    # ========== Override Base UI Functions ==========
    def reset_other_interpolation_button(self, interpolate_mode):
        pass

    def reset_interpolation_param_buttons(self, mode=None):
        pass

    def set_date_selectable(self, mode):
        pass
