from browser import document, aio, ajax
import javascript as js
import datetime
from urllib.parse import urlencode

from monitors.base import BaseMonitor


class EmpiricalForecastsMonitor(BaseMonitor):
    def __init__(
        self,
        lang_code,
        api_url,
        source,
        center=None,
        zoom=None,
    ):
        super().__init__(
            lang_code=lang_code,
            api_url=api_url,
            source=source,
            center=center,
            zoom=zoom,
        )
        self.monitor_name = "empirical_forecast"

        self.forecasts = [
            "empirical_PM_0_1_forecast",
            "empirical_PM_0_1",
            "empirical_PM_1",
            "PM_2_5_prediction_BiLSTM",
            "PM_2_5_prediction_LSTM",
        ]

        # set up api endpoints for empirical forecast and future forecast
        self.apis["stations"]["climates"].update(
            {
                "/": f"{api_url}/v1/stations/climates/",
                "empirical_forecast": {
                    "/": f"{api_url}/v1/stations/climates/empirical_forecast",
                    "interpolate": f"{api_url}/v1/stations/climates/empirical_forecast/interpolate",
                },
                "predictions": {
                    "/": f"{api_url}/v1/stations/climates/predictions",
                    "interpolate": f"{api_url}/v1/stations/climates/predictions/interpolate",
                },
            }
        )
        self.apis.setdefault("interpolations", {}).update(
            {
                "kriging": {
                    "interpolate": f"{api_url}/v1/interpolations/kriging/interpolate"
                }
            }
        )

        self.selected_forecast = None
        self.climates = None
        self.params = dict()

        # for empirical forecast
        self.started_datetime = None

        # for future forecast
        self.forecast_days = self.setup_forecast_range()

        # interpolates
        self.interpolation_params = {
            "kriging": {
                "interpolate_class": None,
                "interpolate_model": None,
                "predict_date": None,
                "target_timestamp": None,
            },
            "simple": {
                "interpolate_model": None,
                "predict_date": None,
                "target_timestamp": None,
            },
            "idw": {
                "predict_date": None,
                "target_timestamp": None,
            },
        }
        self.interpolates_mode_config = {
            "kriging": {
                "classes": self.kriging_classes,
                "models": self.kriging_models,
            },
            "simple": {
                "classes": [],
                "models": self.simple_models,
            },
            "idw": {
                "classes": [],
                "models": [],
            },
        }
        self.required_interpolation_params = {
            "kriging": ["interpolate_class", "interpolate_model"],
            "simple": ["interpolate_model"],
            "idw": [],
        }

    def start(self):
        self.running = True

        # bind self.interpolates from base
        bindings = self.forecasts + self.interpolates

        for name in bindings:
            if name in document:
                document[name].bind("click", self.on_filter_clicked)

        aio.run(self.monitor())

    async def monitor(self):
        await self.setup()  # use setup from base monitor

        while self.running:
            print(f"monitor: wake up {datetime.datetime.now()}")
            print(f"monitor: {self.monitor_name} monitor")
            print(f"monitor: sleep {self.acquisition_interval}s")

            # wait for next aquisition
            await aio.sleep(self.acquisition_interval)

    async def on_filter(self, ev):
        document_ = ev.target
        doc_id = document_.id

        if doc_id in self.forecasts:
            if doc_id in [
                "empirical_PM_0_1_forecast",
                "empirical_PM_0_1",
                "empirical_PM_1",
            ]:
                self.on_empirical_forecast_clicked(ev, doc_id)

            elif doc_id in ["PM_2_5_prediction_BiLSTM", "PM_2_5_prediction_LSTM"]:
                self.on_future_forecast_clicked(ev, doc_id)
        elif doc_id in self.interpolates:
            # use function from base monitor
            self.on_interpolates_clicked(
                ev, selected_sensor_type=self.selected_forecast
            )

    def render_empirical_forecast(self, doc_id, url):
        # remove interpolation layer if exist
        document["select_future_date_panel"].style = "display: none"
        self.remove_all_interpolation_layer()
        self.reset_interpolation_param_buttons()
        self.remove_others_forecast_layers(doc_id)

        self.add_empirical_forecast_climates(
            url=url,
        )
        if not self.map.climate_legends.get(doc_id):
            aio.run(self.map.update_climate_legend(doc_id))

    def remove_others_forecast_layers(self, doc_id):
        # Remove other forecast layers if exist
        for forecast in self.forecasts:
            if forecast in document and forecast != doc_id:
                self.map.remove_climates_layer(forecast)
                self.map.remove_climate_legend(forecast)

    def setup_forecast_range(self):
        forecast_days = datetime.datetime.now() + datetime.timedelta(days=1)
        forecast_days = forecast_days.replace(hour=0, minute=0, second=0, microsecond=0)
        return [
            f"predict_day_{forecast_days + datetime.timedelta(days=i)}"
            for i in range(5)
        ]

    def set_date_selectable(self, mode: bool):
        if mode:
            for column_div in document["prediction_date_buttons"].children:
                # Get the button inside the column div (Button is actually <a>)
                button = column_div.children[0]  # First child is the <a> button
                button.attrs["pointer-events"] = "auto"
                button.classList.remove("disabled")
        else:
            for column_div in document["prediction_date_buttons"].children:
                # Get the button inside the column div (Button is actually <a>)
                button = column_div.children[0]  # First child is the <a> button
                button.attrs["pointer-events"] = "none"
                button.classList.add("disabled")

    def add_empirical_forecast_climates(self, url):
        def climates_on_completed(req):
            try:
                response = js.JSON.parse(req.text)

            except js.JSONParseError:
                print("Error parsing JSON response")
                return

            warning_text = document["empirical_forecast_climates_warning"]
            warning_text.style.display = "none"
            if "errors" in response:
                self.set_map_loading(False)

                warning_text.textContent = f"ไม่มีข้อมูลสำหรับวันที่ {self.started_datetime}."
                warning_text.style.display = "block"
                return

            aio.run(self.map.update(self.selected_forecast, response))
            self.set_map_loading(False)
            self.show_interpolation_control_panel(True)

        # Start loading
        self.set_map_loading(True)

        ajax.get(
            url,
            data=urlencode(self.params),
            oncomplete=climates_on_completed,
            cache=True,
        )

    def on_search_clicked(self, ev):
        if self.selected_forecast:
            self.map.remove_climates_layer(self.selected_forecast)

        started_datetime_str = document["started_datetime"].value

        started_datetime = None
        ended_datetime = None

        if started_datetime_str:
            date_obj = datetime.datetime.strptime(
                started_datetime_str, "%B %d, %Y %I:%M %p"
            ).replace(minute=0, second=0)
        else:
            # default to last hour
            date_obj = (
                datetime.datetime.now(datetime.timezone.utc)
                - datetime.timedelta(hours=1)
            ).date()
        # convert to from +7 to UTC
        date_obj = date_obj - datetime.timedelta(hours=7)

        started_datetime = date_obj
        ended_datetime = date_obj + datetime.timedelta(hours=1)

        started_datetime = started_datetime.isoformat()
        ended_datetime = ended_datetime.isoformat()

        self.started_datetime = started_datetime
        self.params = dict(
            source=self.source,
            started_datetime=started_datetime,
            ended_datetime=ended_datetime,
        )

        # Check whether its ANN or Linear Regression
        if self.selected_forecast == "empirical_PM_0_1_forecast":
            url = self.apis["stations"]["climates"]["empirical_forecast"]["/"]
        else:
            url = self.apis["stations"]["climates"]["/"]

        self.add_empirical_forecast_climates(url)

    def on_empirical_forecast_clicked(self, ev, doc_id):
        self.set_date_selectable(False)
        if "empirical_forecast_search_data_button" in document:
            document["empirical_forecast_search_data_button"].unbind("click")
            document["empirical_forecast_search_data_button"].bind(
                "click", self.on_search_clicked
            )

        if ev.target.checked:
            print(f"Empirical forecast {doc_id} checked")
            self.selected_forecast = doc_id
            document["calendar_panel"].style = "display: block"
            # Select which api
            if doc_id == "empirical_PM_0_1_forecast":
                url = self.apis["stations"]["climates"]["empirical_forecast"]["/"]
            else:
                url = self.apis["stations"]["climates"]["/"]

            # This trigger when user switch from ANN <-> Linear Regression
            # So Its faster to just update the layer without fetch new data
            if self.selected_forecast and self.params:
                self.render_empirical_forecast(doc_id, url)
        else:
            self.selected_forecast = None
            self.params = dict()
            self.remove_climates_interpolation_layers(doc_id)
            document["calendar_panel"].style = "display: none"

    def on_future_forecast_clicked(self, ev, doc_id):
        # hide calendar panel if open
        document["calendar_panel"].style = "display: none"
        # Remove other forecast layers if exist
        self.remove_others_forecast_layers(doc_id)

        for forecast in self.forecasts:
            if forecast in document and forecast != doc_id:
                self.map.remove_climates_layer(forecast)
                self.map.remove_climate_legend(forecast)

        if ev.target.checked:
            self.selected_forecast = doc_id
            # Bind click events after forecast_days is populated
            for day_id in self.forecast_days:
                if day_id in document:
                    document[day_id].bind(
                        "click",
                        lambda ev: self.on_forecast_date_changed(ev),
                    )

            # Default to the first day in the forecast range
            date_string = self.forecast_days[0].replace("predict_day_", "")

            # Convert string to datetime object
            predict_date = datetime.datetime.strptime(date_string, "%Y-%m-%d %H:%M:%S")

            if doc_id == "PM_2_5_prediction_BiLSTM":
                model_type = "BiLSTM"
            elif doc_id == "PM_2_5_prediction_LSTM":
                model_type = "LSTM"

            self.params = {
                "source": self.source,
                "predict_date": predict_date,
                "model_type": model_type,
                "sensor_type": "PM_2_5",
            }

            self.started_datetime = predict_date
            self.target_timestamp = predict_date

            # Set first day button active by default
            document[self.forecast_days[0]].classList.add("active")

            # Fetch forecast for the first day by default
            self.fetch_future_forecast(predict_date=predict_date)

            document["select_future_date_panel"].style = "display: block"
            document["interpolation_control_panel"].style = "display: block"
        else:
            document["select_future_date_panel"].style = "display: none"
            document["interpolation_control_panel"].style = "display: none"

            self.remove_climates_interpolation_layers(doc_id)

    def on_forecast_date_changed(self, ev):
        # Remove 'active' class from all buttons (need to access the <a> inside each column div)
        for column_div in document["prediction_date_buttons"].children:
            # Get the button inside the column div
            button = column_div.children[0]  # First child is the <a> button
            button.classList.remove("active")

        # Add 'active' class to clicked button
        ev.target.classList.add("active")

        date_string = ev.target.id.replace("predict_day_", "")

        # Convert string to datetime object
        target_timestamp = datetime.datetime.strptime(date_string, "%Y-%m-%d %H:%M:%S")

        # If target timestamp is the same as current, do nothing
        if target_timestamp == self.target_timestamp:
            return

        print(f"self.map.shapes: {self.map.shapes}")
        print(
            f"Selected forecast: {self.selected_forecast}, target_timestamp: {target_timestamp}"
        )
        self.remove_all_interpolation_layer()
        self.set_date_selectable(False)
        self.set_map_loading(True)

        aio.run(
            self.map.update(
                "PM_2_5_prediction",
                self.climates,
                target_timestamp=target_timestamp,
            )
        )

        self.target_timestamp = target_timestamp

        # กรณีมีการเปลี่ยนวันที่ ให้ update ค่าของ interpolation ด้วย
        for mode in self.interpolation_params.keys():
            # ดึงค่า interpolation ใหม่แก้วันที่เปลี่ยน
            if mode in self.map.shapes.keys():
                url = self.apis["stations"]["climates"]["predictions"]["interpolate"]
                extra_params = {
                    "predict_date": self.started_datetime,
                    "target_timestamp": self.target_timestamp,
                }
                if self.selected_forecast == "PM_2_5_prediction_BiLSTM":
                    extra_params["model_type"] = "BiLSTM"
                elif self.selected_forecast == "PM_2_5_prediction_LSTM":
                    extra_params["model_type"] = "LSTM"
                self.set_interpolation(
                    url=url,
                    sensor_type="PM_2_5_prediction",
                    mode=mode,
                    extra_params=extra_params,
                )

    def fetch_future_forecast(self, predict_date):
        url = self.apis["stations"]["climates"]["predictions"]["/"]

        def climates_on_completed(req):
            response = js.JSON.parse(req.text)

            self.climates = response
            aio.run(
                self.map.update(
                    "PM_2_5_prediction",
                    self.climates,
                    target_timestamp=predict_date,
                )
            )

            self.set_map_loading(False)
            self.set_date_selectable(True)
            return True

        self.set_date_selectable(False)
        self.set_map_loading(True)

        ajax.get(
            url,
            data=urlencode(self.params),
            oncomplete=climates_on_completed,
            cache=True,
        )

    def on_interpolation_parameter_clicked(self, ev, sensor_type, mode):
        self.remove_interpolation_layer(mode)
        doc_id = ev.target.id
        prefix = f"{mode}_"

        # formulas = document.select(f'[name="{prefix}formula"]')
        params = self.interpolation_params[mode]

        config = self.interpolates_build_config.get(mode, {})
        classes = config["classes"]
        models = config["models"]

        if doc_id not in document and not document[doc_id].checked:
            return
        elif doc_id in classes:
            params["interpolate_class"] = doc_id

        elif doc_id in models:
            params["interpolate_model"] = doc_id
        else:
            formula = doc_id.replace(prefix, "")
            if formula == "raw_data":
                params["formula"] = ""
            else:
                params["formula"] = formula

        # added extra param
        extra_params = {}
        if sensor_type in ["PM_2_5_prediction_BiLSTM", "PM_2_5_prediction_LSTM"]:
            url = self.apis["stations"]["climates"]["predictions"]["interpolate"]
            extra_params["predict_date"] = self.started_datetime
            extra_params["target_timestamp"] = self.target_timestamp
            if sensor_type == "PM_2_5_prediction_BiLSTM":
                extra_params["model_type"] = "BiLSTM"
            elif sensor_type == "PM_2_5_prediction_LSTM":
                extra_params["model_type"] = "LSTM"

        elif sensor_type == "empirical_PM_0_1_forecast":
            url = self.apis["stations"]["climates"]["empirical_forecast"]["interpolate"]
            extra_params["started_datetime"] = self.started_datetime
        elif sensor_type in ["empirical_PM_0_1", "empirical_PM_1"]:
            url = self.apis["interpolations"]["kriging"]["interpolate"]
            extra_params["started_datetime"] = self.started_datetime

        # check required parameters based on interpolates_build_config
        required = self.required_interpolation_params.get(mode, [])
        if not all(params.get(k) for k in required):
            return

        self.set_interpolation(
            url=url,
            sensor_type=sensor_type,
            mode=mode,
            extra_params=extra_params,
        )
