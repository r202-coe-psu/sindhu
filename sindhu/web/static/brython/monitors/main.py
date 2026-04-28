import datetime
import time
from urllib.parse import urlencode

import javascript as js

from browser import ajax, document, html, window, timer, aio
from maps import LnMainMap, MainMap, MainDashboardMap
from stations import Station
from .dashboard import DashboardMonitor
from . import (
    climates,
    hotspots,
    fire_reports,
    empirical_forecasts,
    predictions,
    dashboard_forecasts,
)

bangkok_timezone = datetime.timezone(datetime.timedelta(hours=7), name="Asia/Bangkok")


class MainMonitor:
    def __init__(
        self,
        lang_code,
        api_url,
        source,
        center=None,
        zoom=None,
        monitor_mode="climates",
    ):
        self.lang_code = lang_code
        self.acquisition_interval = 60 * 60

        self.running = False

        self.api_url = api_url
        self.source = source
        self.center = center
        self.zoom = zoom
        self.monitor_mode = monitor_mode

        self.started_datetime = ""
        self.ended_datetime = ""

        self.pm25_ranking = None
        self.get_system_setting_url = f"{api_url}/v1/system_settings"
        self.get_pm25_ranking_url = f"{api_url}/v1/stations/climates/ranking"
        self.get_stations_url = f"{api_url}/v1/stations"
        # ใช้สำหรับการดึงข้อมูลจาก api สำหรับตัว sensor type เพื่อนำข้อมูลมาแสดงเป็น marker
        self.get_station_latest_climate_sensor_type_url = (
            f"{api_url}/v1/stations/climates/sensor_type/latest"
        )
        self.get_station_climate_url = f"{api_url}/v1/stations/climates/"
        self.get_empirical_forecast_url = (
            f"{api_url}/v1/stations/climates/empirical_forecast"
        )
        self.get_station_latest_climate_url = f"{api_url}/v1/stations/climates/latest"
        self.get_latest_hotspot_url = f"{api_url}/v1/hotspots/latest"

        self.get_hotspot_animation_response_url = f"{api_url}/v1/hotspots/animation"
        self.get_interpolation_url = f"{api_url}/v1/interpolations/kriging/interpolate"
        self.get_fire_reports_url = f"{api_url}/v1/fire_reports"
        self.get_fire_report_file_url = f"{api_url}/v1/data/sample_doc_id"
        self.get_fire_report_aod_url = f"{api_url}/v1/climates/fire_report/aod"
        # self.get_climate_formulas_url = f"{api_url}/v1/climate_formulas"

        # ใช้สำหรับเก็บค่าตัวแปรที่ใช้สำหรับเช็ค การโหลดเสร็จสมบูรณ์
        self.list_resource = []

        # ใช้สำหรับเก็บ source เพื่อนำมาแสดงผล เมื่อกด ปุ่ม source
        self.sources = [
            "air4thai",
            "meteorological",
            "airport",
            "santhings",
        ]

        self.fire_sources = ["firms", "fire_reports"]

        self.source_mapping = {
            "air4thai": "air4thai",
            "meteorological": "meteorological",
            "airport": "port-api",
            "santhings": "santhings-api",
        }
        # ใช้สำหรับเก็บ sensor type เพื่อนำมาแสดงผล เมื่อกด ปุ่ม sensor type
        self.sensor_types = [
            "PM_0_1",
            "PM_1",
            "PM_2_5",
            "PM_10",
            "rain",
            "pressure",
            "temperature",
            "wind_direction",
            "humidity",
            "CO",
            "O3",
            "SO2",
            "NO2",
        ]

        self.hotspots = [
            "viir_hotspots",
            "noaa-20_hotspots",
            "noaa-21_hotspots",
            "suomi_hotspots",
            "modis_hotspots",
        ]

        self.interpolates = [
            "kriging_interpolation",
            "simple_interpolation",
            "idw_interpolation",
        ]

        self.time_periods = [
            "custom",
            "7_days",
            "5_days",
            "3_days",
            "24_hours",
        ]

        self.hotspots_time_period_info_panel = [
            "hotspots_time_period_info_panel",
            "time_preiod_header",
            "time_preiod_detail",
        ]

        self.hotspot_display_options = [
            "display_cumulative",
            "display_non_cumulative",
        ]
        self.hotspot_display_mode = []

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
        self.simple_models = [
            "nearest",
            "cubic",
        ]
        self.simple_sensors = {
            "simple_pm_2_5": "PM_2_5",
            "simple_temperature": "temperature",
            "simple_humidity": "humidity",
        }
        self.idw_sensors = {
            "idw_pm_2_5": "PM_2_5",
            "idw_temperature": "temperature",
            "idw_humidity": "humidity",
        }
        self.interpolate_mode = None

        self.fire_report_datas = {}
        self.fire_reports = [
            "FAHP",
            "dNBR",
            "AOD",
            "MLBA",
            "Emissions",
        ]
        self.fire_report_aod_filters = ["aod"]
        self.fire_report_name_checked = None

        self.interpolate_model = None
        self.interpolate_sensor_type = None

        self.formula_name = None

        self.sensor_type_buttons = ["stations_button", "parameters_button"]

        self.empirical_forecasts = [
            "empirical_PM_0_1_forecast",
            "empirical_PM_0_1",
            "empirical_PM_1",
        ]

        self.tab_dashboard = ["pm_0_1", "pm_1", "pm_2_5", "pm_10"]
        self.tab_selected = ["tab_pm25", "tab_temperature", "tab_humidity"]
        self.predictions = ["PM_2_5_prediction"]

        self.predict_days = []

        self.stations = dict()
        self.map = "pm25"

        self.climate_service = None
        self.hotspot_service = None
        self.empirical_forecast_service = None
        self.prediction_service = None
        self.dashboard = None
        self.dashboard_forecasts = None
        self.selected_sensor_type = "pm_2_5"
        self.selected_table_sensor_type = "tab_pm25"
        # self.selected_sensor_type = None

        self.user_coord = ["my_locate"]
        self.search_button = ["search_button"]
        self.selected_region = "south"
        self.region_dropdown_id = "region-dropdown"
        self.region = [
            "all",
            "bangkok_vicinity",
            "north",
            "northeast",
            "central_west",
            "east",
            "south",
        ]
        # Card Modal
        self.topic_keys = ["pm25", "pm01_pm1", "aqi_knowledge"]

        # button for selected date predict
        self.predict_date = ["pred_1", "pred_2", "pred_3", "pred_4", "pred_5"]

        self.toggle_marker = ["toggle_marker"]

    async def get_api_data(self, url, params):
        response = await aio.get(url, data=params, cache=True)
        stations = js.JSON.parse(response.data)

        return stations

    ### Get data zone
    def get_latest_climate_data_on_completed(self, req, document_id):
        # print(f"DEBUG: Status Code: {req.status}")  # เช็กว่า 200 OK หรือไม่
        # print(f"DEBUG: Response Text: {req.text}")  # ตัวปัญหาคือค่านี้

        climates = js.JSON.parse(req.text)
        aio.run(self.map.update(document_id, climates))

    def get_latest_climate_data(self, url, params, document_id):
        # document["loading_map"].className = "ui active inverted dimmer"
        if document_id not in self.list_resource:
            self.list_resource.append(document_id)

        ajax.get(
            url,
            data=urlencode(params),
            oncomplete=lambda req: self.get_latest_climate_data_on_completed(
                req, document_id
            ),
            cache=True,
        )

    def determine_url_and_params(self, document_id):
        params = {}

        if document_id in self.sensor_types:
            return self.get_station_latest_climate_sensor_type_url, {
                "sensor_type": document_id
            }

        for key, source in self.source_mapping.items():
            if key in document_id:
                params["source"] = source
                return self.get_station_latest_climate_url, params

        return None, params

    def get_latest_climates(self, document_id):
        url, params = self.determine_url_and_params(document_id)

        self.get_latest_climate_data(url, params, document_id)

    def on_reset_hotspot_params_clicked(self, ev=None):
        for param in self.hotspot_display_options + self.time_periods:
            if param in document:
                document[param].style.backgroundColor = ""

        document["hotspot_calendar_panel"].style.display = "none"
        document["started_datetime"].value = ""
        document["ended_datetime"].value = ""

        for mode in self.hotspot_display_mode:
            self.map.remove_hotspots_layer(mode)
            self.hotspot_service.hotspot_params[mode]["display_mode"] = None
            self.hotspot_service.hotspot_params[mode]["time_period"] = None

    def get_user_coord(self, ev):

        self.map.fly_to_user()

    ### Manage event on browser
    def on_filter_clicked(self, ev):
        timer.set_timeout(lambda: aio.run(self.on_filter(ev)), 50)

    async def on_filter(self, ev):
        document_ = ev.target
        doc_id = document_.id

        if doc_id in self.sources or doc_id in self.sensor_types:
            if document_.checked:
                if doc_id in self.sensor_types:
                    # remove all other sensor types
                    for sensor_type in self.sensor_types:
                        if sensor_type in document and sensor_type != doc_id:
                            self.map.remove_climates_layer(sensor_type)
                            self.map.remove_climate_legend(sensor_type)

                if doc_id not in self.map.sensor_markers_layer:
                    self.get_latest_climates(doc_id)
                    aio.run(self.map.update_climate_legend(doc_id))
                else:
                    self.map.set_all_sensor_marker(doc_id)
                    aio.run(self.map.update_climate_legend(doc_id))

            else:
                self.map.remove_climates_layer(doc_id)
                self.map.remove_climate_legend(doc_id)

        elif doc_id in self.hotspots:
            if document_.checked:
                mode = doc_id

                if doc_id not in self.hotspot_display_mode:
                    self.hotspot_display_mode.append(doc_id)

                for mode in self.hotspot_display_mode:
                    self.map.remove_hotspot_legend(mode)
                    param = self.hotspot_service.hotspot_params.get(mode, {})
                    display_mode = param.get("display_mode")
                    time_period = param.get("time_period")

                    other_mode = (
                        "viir_hotspots"
                        if mode == "modis_hotspots"
                        else "modis_hotspots"
                    )
                    if display_mode and time_period:

                        self.hotspot_service.hotspot_params[other_mode][
                            "display_mode"
                        ] = display_mode
                        self.hotspot_service.hotspot_params[other_mode][
                            "time_period"
                        ] = time_period

                        self.hotspot_service.get_hotspots_data(mode)

                    elif display_mode and not time_period:
                        self.hotspot_service.hotspot_params[other_mode][
                            "display_mode"
                        ] = display_mode

                        if mode not in self.hotspot_service.selected_modes:
                            self.hotspot_service.selected_modes.append(mode)

                        if "search_data" in document:
                            document["search_data"].unbind("click")
                            document["search_data"].bind(
                                "click", self.hotspot_service.on_search_clicked
                            )

                parameters = self.hotspot_display_options + self.time_periods

                if not getattr(self, "_hotspot_params_bound", False):
                    for param in parameters:
                        document[param].bind(
                            "click",
                            lambda ev: self.hotspot_service.on_hotspots_parameter_clicked(
                                ev,
                                list(self.hotspot_display_mode),
                            ),
                        )
                    self._hotspot_params_bound = True

            else:
                self.map.remove_hotspots_layer(doc_id)
                self.map.remove_hotspot_legend(doc_id)
                if doc_id in self.hotspot_display_mode:
                    self.hotspot_display_mode.remove(doc_id)

            document["hotspot_display_mode_panel"].style.display = (
                "block" if self.hotspot_display_mode else "none"
            )

        # elif doc_id in self.tab_dashboard:
        #     sensor_map = {"pm_0_1": "PM_0_1", "pm_1": "PM_1", "pm_2_5": "PM_2_5"}
        #     actual_doc_id = sensor_map[doc_id]
        #     if document_.checked:
        #         # remove all other sensor types
        #         for sensor_type in self.sensor_types:
        #             if sensor_type in document and sensor_type != actual_doc_id:
        #                 self.map.remove_climates_layer(sensor_type)
        #                 self.map.remove_climate_legend(sensor_type)

        #         if actual_doc_id not in self.map.sensor_markers_layer:
        #             self.get_latest_climates(actual_doc_id)
        #             aio.run(self.map.update_climate_legend(actual_doc_id))
        #         else:
        #             self.map.set_all_sensor_marker(actual_doc_id)
        #             aio.run(self.map.update_climate_legend(actual_doc_id))

        #     else:
        #         self.map.remove_climates_layer(actual_doc_id)
        #         self.map.remove_climate_legend(actual_doc_id)

        elif doc_id in self.interpolates:
            # print("Interpolate :", self.interpolates)
            if document_.checked:
                document[f"{doc_id}_choices"].style.display = "block"

                mode = doc_id.replace("_interpolation", "")
                # index page mode
                if self.monitor_mode == "climates":
                    if mode in self.map.shapes.keys():
                        self.climate_service.get_interpolation(mode)

                    self.interpolate_mode = mode
                    prefix = f"{mode}_"

                    formulas = document.select(f"[name='{prefix}formula']")
                    formula_ids = [f.id for f in formulas]

                    if mode == "kriging":
                        # print("DEBUG selectedMode: ", mode)
                        parameters = (
                            self.kriging_classes
                            + self.kriging_models
                            + list(self.kriging_sensors.keys())
                            + formula_ids
                        )
                    elif mode == "simple":
                        parameters = (
                            self.simple_models
                            + list(self.simple_sensors.keys())
                            + formula_ids
                        )
                    else:
                        parameters = list(self.idw_sensors.keys())

                    print(f"Bind click event for parameters: {parameters}")

                    for param in parameters:
                        document[param].bind(
                            "click",
                            lambda ev, m=mode: self.climate_service.on_interpolation_parameter_clicked(
                                ev, mode=m
                            ),
                        )

                # empirical forecast page mode
                elif self.monitor_mode == "empirical_forecasts":
                    if mode in self.map.shapes.keys():
                        self.prediction_service.get_interpolation(
                            doc_id=self.selected_sensor_type,
                            mode=mode,
                            started_datetime=self.empirical_forecast_service.started_datetime,
                        )

                    self.interpolate_mode = mode
                    prefix = f"{mode}_"

                    formulas = document.select(f"[name='{prefix}formula']")
                    formula_ids = [f.id for f in formulas]

                    if mode == "kriging":
                        parameters = (
                            self.kriging_classes + self.kriging_models + formula_ids
                        )
                    elif mode == "simple":
                        parameters = self.simple_models + formula_ids
                    elif mode == "idw":
                        parameters = formula_ids
                        # Call Immediate for idw to set default parameters
                        self.prediction_service.on_interpolation_parameter_clicked(
                            ev, mode=mode
                        )

                    for param in parameters:
                        document[param].bind(
                            "click",
                            lambda ev, m=mode: self.prediction_service.on_interpolation_parameter_clicked(
                                ev,
                                sensor_type=self.selected_sensor_type,
                                mode=m,
                                started_datetime=self.empirical_forecast_service.started_datetime,
                            ),
                        )
            else:
                document[f"{doc_id}_choices"].style.display = "none"
                self.climate_service.remove_all_interpolation_layer()

        elif doc_id in self.fire_reports:
            if self.map.fire_report_layers:
                self.map.remove_all_fire_report_layers()
                self.map.remove_all_fire_report_legends()

            if document_.checked:
                warning_el = document["fire_report_enso_phase_warning"]
                warning_el.style.display = "none"

                params = {"status": "active"}
                url = f"{self.get_fire_reports_url}"
                await self.fire_report_service.get_fire_reports_data(
                    url,
                    params,
                )

                self.fire_report_service.on_fire_report_category_selected(ev)

        elif doc_id in self.empirical_forecasts:
            if document_.checked:
                self.selected_sensor_type = doc_id
                if doc_id == "empirical_PM_0_1_forecast":
                    # This mean use ANN to predict PM 0.1 that run from pipeline
                    empirical_forecast_url = self.get_empirical_forecast_url
                else:
                    # This mean use Linear Regression to predict PM 0.1
                    empirical_forecast_url = self.get_station_climate_url
                doc_id = doc_id.replace("empirical_", "")
                for sensor_type in self.empirical_forecasts:
                    if sensor_type in document and sensor_type != doc_id:
                        sensor_type = sensor_type.replace("empirical_", "")

                        self.map.remove_climates_layer(sensor_type)
                        self.map.remove_climate_legend(sensor_type)

                if (
                    self.empirical_forecast_service.empirical_forecast_selected
                    and self.empirical_forecast_service.empirical_forecast_params
                ):
                    self.empirical_forecast_service.add_empirical_forecast_climates(
                        empirical_forecast_url
                    )
                    if not self.map.climate_legends.get(doc_id):
                        await self.map.update_climate_legend(doc_id)

                self.empirical_forecast_service.on_empirical_forecast_clicked(ev)

        elif doc_id in self.predictions:
            if document_.checked:
                document["interpolation_control_panel"].style = "display: block"
                self.selected_sensor_type = doc_id
                if doc_id not in self.map.sensor_markers_layer:
                    self.predict_days = []
                    predict_date = datetime.datetime.now() + datetime.timedelta(days=1)
                    predict_date = predict_date.replace(
                        hour=0, minute=0, second=0, microsecond=0
                    )
                    self.predict_days = [
                        f"predict_day_{predict_date + datetime.timedelta(days=i)}"
                        for i in range(5)
                    ]

                    # Bind click events after predict_days is populated
                    for day_id in self.predict_days:
                        if day_id in document:
                            document[day_id].bind(
                                "click",
                                lambda ev: aio.run(
                                    self.prediction_service.on_prediction_date_changed(
                                        ev
                                    )
                                ),
                            )
                    self.prediction_service.predict_days = self.predict_days

                    self.prediction_service.prediction_selected = doc_id
                    self.prediction_service.prediction_params = {
                        "source": self.sources[0],
                        "predict_date": predict_date,
                        "sensor_type": "PM_2_5",
                        "model": "BiLSTM",
                    }
                    self.prediction_service.start_predict_date = predict_date
                    self.prediction_service.target_timestamp = predict_date
                    document[self.predict_days[0]].classList.add("active")
                    self.prediction_service.add_prediction_climate(
                        predict_date=predict_date
                    )
                    await self.map.update_climate_legend(doc_id)
                else:
                    self.map.set_all_sensor_marker(doc_id)
                    await self.map.update_climate_legend(doc_id)
            else:
                self.map.remove_climates_layer(doc_id)
                self.map.remove_climate_legend(doc_id)
                # remove interpolate layer if exist
                self.prediction_service.remove_all_interpolation_layer()
                self.interpolate_mode = None
            self.prediction_service.on_prediction_clicked(ev)

        elif doc_id in self.tab_dashboard:
            print("Main Monitor Dashboard Filter Get: ", doc_id)

            self.dashboard.handle_tab_click_dashboard(ev)

            self.map.selected_sensor_type = doc_id
            # print("Doc_id", doc_id)

            if doc_id == "pm_0_1":
                target = "PM_0_1_forecast"
            #     doc_id = "empirical_PM_0_1_forecast"
            #     empirical_forecast_url = self.get_empirical_forecast_url
            else:
                target = doc_id.upper()

            # print(f"Requesting data for: {target}")
            # print("-->", doc_id, target)
            self.get_latest_climates(target)

            current_source = (
                self.map.current_source if self.map.current_source else "air4thai"
            )
            self.map.remove_climates_layer(current_source)

            if self.map.current_data:
                aio.run(
                    self.map.update(
                        current_source,
                        self.map.current_data,
                    )
                )
                # aio.run(self.dashboard.update())
        elif doc_id in self.tab_selected:
            self.dashboard.handle_tab_click_table(ev)
            self.dashboard.selected_table_sensor_type = doc_id

            current_source = (
                self.map.current_source if self.map.current_source else "air4thai"
            )
            # self.map.remove_climates_layer(current_source)

            aio.run(self.dashboard.update())

        elif doc_id == self.region_dropdown_id:
            self.dashboard.handle_region_change(ev)
            self.dashboard.selected_region = document_.value

            current_source = (
                self.map.current_source if self.map.current_source else "air4thai"
            )

            # aio.run(self.dashboard.update())

        # elif doc_id in self.region:
        #     self.dashboard.handle_region_change(ev)
        #     self.dashboard.selected_region = doc_id

        #     current_source = (
        #         self.map.current_source if self.map.current_source else "air4thai"
        #     )
        #     # self.map.remove_climates_layer(current_source)

        #     aio.run(self.dashboard.update())

        # elif doc_id in self.user_coord:
        #     self.dashboard.get_user_coord(ev)
        #     # print("Main Monitor My Coord Get: ", doc_id)

        #     self.map.fly_to_user()

        elif doc_id in self.user_coord:
            # แก้เป็นเรียกฟังก์ชันในคลาสตัวเอง
            self.get_user_coord(ev)

        # elif doc_id in self.search_button:
        #     # แก้เป็นเรียกฟังก์ชันในคลาสตัวเอง
        #     self.search_station(ev)

        elif doc_id in self.search_button:
            self.dashboard.search_station(ev)

            # Clear map
            current_source = (
                self.map.current_source if self.map.current_source else "air4thai"
            )
            self.map.remove_climates_layer(current_source)
            if self.map.current_data:
                aio.run(
                    self.map.update(
                        current_source,
                        self.map.current_data,
                    )
                )

        elif doc_id in self.topic_keys:
            # print("Topic_keys", doc_id)
            self.dashboard.show_modal(ev)

        # elif doc_id in self.predict_date:
        #     print(f"Forecast Date Clicked: {doc_id}")
        #     self.dashboard_forecasts.on_prediction_date_changed(ev)

        elif doc_id in self.toggle_marker:
            is_active = ev.target.checked
            self.dashboard.toggle_marker(is_active)

        else:
            self.climate_service.on_type_changed(doc_id)

    ### Setup
    async def setup(self):
        response = await aio.get(self.get_system_setting_url, cache=True)
        self.system_setting = js.JSON.parse(response.data)

        center = self.system_setting["center"]["coordinates"]
        zoom = self.system_setting["zoom"]
        min_zoom = self.system_setting["min_zoom"]
        if self.source in ["fire_reports"]:
            center = self.center
            zoom = self.zoom

        if self.monitor_mode == "new_dashboard":
            self.map = LnMainMap(
                [15.0, 101.0],
                5.4,
                min_zoom,
                self.lang_code,
                self.api_url,
                self.selected_sensor_type,
            )
            # New Dashboard
            self.dashboard = DashboardMonitor(
                self.api_url,
                self.map,
                self.selected_table_sensor_type,
                self.selected_region,
            )
            # Top 5 Highest, Lowest pm25
            await self.dashboard.display_pm25_ranking(self.selected_sensor_type)
            # Interpolate
            self.dashboard.get_interpolation()
            # Climate detail information
            await self.dashboard.update()
            print("DashboardMonitor setup completed")

        elif self.monitor_mode == "dashboard_forecasts":
            print("-----MainDashboardMap-----")
            self.map = MainDashboardMap(
                [center[1], center[0]],
                6,
                min_zoom,
                self.lang_code,
                self.api_url,
            )
            self.dashboard_forecasts = dashboard_forecasts.DashboardForecastMonitor(
                self.source, self.map, self.api_url
            )
            self.dashboard_forecasts.setup_events()

            await self.dashboard_forecasts.add_prediction_climate()

        else:
            self.map = MainMap([center[1], center[0]], zoom, min_zoom, self.lang_code)

        self.climate_service = climates.Climates(self.source, self.map, self.api_url)
        self.hotspot_service = hotspots.Hotspot(self.source, self.map, self.api_url)
        self.fire_report_service = fire_reports.FireReport(
            self.source, self.map, self.api_url
        )
        # self.empirical_forecast_service = empirical_forecasts.EmpiricalForecasts(
        #     self.source, self.map, self.api_url
        # )
        self.prediction_service = predictions.Predictions(
            self.source, self.map, self.api_url
        )

    ### Monitor
    async def monitor(self):
        await self.setup()

        while self.running:
            print(f"monitor: wake up {datetime.datetime.now()}")

            source = self.source
            print(f"Monitor mode: {self.monitor_mode}")

            if not self.monitor_mode == "dashboard_forecasts":
                if source not in self.fire_sources:
                    params = dict(source=source)
                    stations = await self.get_api_data(
                        self.get_station_latest_climate_url, params
                    )
                    await self.map.update(source, stations)

            print(f"monitor: sleep {self.acquisition_interval}s")
            # wait for next aquisition
            await aio.sleep(self.acquisition_interval)

    ### Start
    def start(self):
        print("Start")
        self.running = True

        sources = self.sources
        sensor_names = self.sensor_types
        hotspots = self.hotspots
        interpolations = self.interpolates
        sensor_type = self.sensor_type_buttons
        fire_reports = self.fire_reports
        empirical_forecasts = self.empirical_forecasts
        predictions = self.predictions
        tab_dashboard = self.tab_dashboard
        tab_selected = self.tab_selected
        user_coord = self.user_coord
        search_button = self.search_button
        # region = self.region
        topic_keys = self.topic_keys
        toggle_marker = self.toggle_marker
        for name in (
            sources
            + sensor_names
            + hotspots
            + interpolations
            + sensor_type
            + fire_reports
            + empirical_forecasts
            + predictions
            + tab_dashboard
            + tab_selected
            + user_coord
            + search_button
            + topic_keys
            + toggle_marker
        ):
            if name in document:
                document[name].bind("click", self.on_filter_clicked)

        if self.region_dropdown_id in document:
            document[self.region_dropdown_id].bind("change", self.on_filter_clicked)

        if "reset_hotspot_params" in document:
            document["reset_hotspot_params"].bind(
                "click", self.on_reset_hotspot_params_clicked
            )

        aio.run(self.monitor())
