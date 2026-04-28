from urllib.parse import urlencode

import javascript as js
from browser import ajax, document, html, window, timer, aio
import datetime


class Predictions:
    def __init__(self, source, map_, api_url):
        self.source = source
        self.map = map_
        self.api_url = api_url
        self.predict_days = []
        self.start_predict_date = None
        self.target_timestamp = None

        self.prediction_selected = None
        self.prediction_params = None

        self.get_station_climate_url = f"{api_url}/v1/stations/climates/predictions"
        self.get_prediction_interpolation_url = (
            f"{api_url}/v1/stations/climates/predictions/interpolate"
        )
        self.get_empirical_forecast_url = (
            f"{api_url}/v1/stations/climates/empirical_forecast/interpolate"
        )
        self.get_interpolation_url = f"{api_url}/v1/interpolations/kriging/interpolate"

        self.climates = None

        self.interpolates = [
            "kriging_interpolation",
            "simple_interpolation",
            "idw_interpolation",
        ]

        self.kriging_classes = ["ordinary", "simple"]
        self.kriging_models = [
            "exp",
            "spherical",
        ]

        self.simple_models = [
            "nearest",
            "cubic",
        ]

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

    def reset_interpolation_params(self, selected_mode=None):
        for mode in self.interpolation_params.keys():
            if mode == selected_mode:
                continue
            for key in self.interpolation_params[mode].keys():
                self.interpolation_params[mode][key] = None

    def reset_other_interpolation_button(self, interpolate_mode):
        document_ids = self.interpolates.copy()
        if interpolate_mode in ["kriging", "simple", "idw"]:
            document_ids.remove(f"{interpolate_mode}_interpolation")
        if interpolate_mode == "kriging":
            document_ids += self.simple_models
        elif interpolate_mode == "simple":
            document_ids += self.kriging_classes + self.kriging_models
        else:
            document_ids += (
                self.simple_models + self.kriging_classes + self.kriging_models
            )
        for doc_id in document_ids:
            document[doc_id].checked = False

    def params_mode(self, mode="disable"):
        if mode == "enable":
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

    def add_prediction_climate(self, url=None, predict_date=None):
        if url is None:
            url = self.get_station_climate_url

        def climates_on_completed(req):
            response = js.JSON.parse(req.text)

            self.climates = response
            aio.run(
                self.map.update(
                    self.prediction_selected,
                    self.climates,
                    target_timestamp=predict_date,
                )
            )

            document["loading_map"].className = "ui inactive inverted dimmer"
            self.params_mode("enable")

        self.params_mode("disable")

        document["loading_map"].className = "ui active inverted dimmer"

        params = self.prediction_params
        ajax.get(
            url,
            data=urlencode(params),
            oncomplete=climates_on_completed,
            cache=True,
        )

    def on_prediction_clicked(self, ev):
        doc_id = ev.target.id
        self.prediction_selected = doc_id
        if ev.target.checked:
            document["select_future_date_panel"].style = "display: block"
            document["interpolation_control_panel"].style = "display: block"
        else:
            document["select_future_date_panel"].style = "display: none"
            document["interpolation_control_panel"].style = "display: none"

    async def on_prediction_date_changed(self, ev):
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
        if target_timestamp == self.target_timestamp:
            return

        self.map.remove_climates_layer("PM_2_5_prediction")
        self.params_mode("disable")
        document["loading_map"].className = "ui active inverted dimmer"

        await self.map.update(
            self.prediction_selected,
            self.climates,
            target_timestamp=target_timestamp,
        )
        self.target_timestamp = target_timestamp

        # กรณีมีการเปลี่ยนวันที่ ให้ update ค่าของ interpolation ด้วย
        has_active_interpolation = False
        for mode in self.interpolation_params.keys():
            # ดึงค่า interpolation ใหม่แก้วันที่เปลี่ยน
            self.interpolation_params[mode]["target_timestamp"] = target_timestamp
            if mode in self.map.shapes.keys():
                has_active_interpolation = True
                self.get_interpolation("PM_2_5_prediction", mode)

        # กรณีปกติเรียก loading ออกเอง (และ enable params)
        if not has_active_interpolation:
            document["loading_map"].className = "ui inactive inverted dimmer"
            self.params_mode("enable")

    ### Interpolations
    def remove_all_interpolation_layer(self):
        for key in list(self.interpolation_params.keys()):
            self.remove_interpolation_layer(key)
            # remove boundary layer if exist
            print(self.map.shapes)
            if "boundary" in self.map.shapes:
                print("remove 'boundary' layer")
                self.map.map.removeLayer(self.map.shapes["boundary"])
                del self.map.shapes["boundary"]

    def remove_interpolation_layer(self, key):
        if key in self.map.shapes.keys():
            print(f"remove '{key}' interpolate layer")
            self.map.map.removeLayer(self.map.shapes[key])

    def add_interpolation(
        self,
        url,
        source,
        formula="",
        key="",
        interpolate_class="",
        interpolate_model="",
        **kwargs,
    ):
        def interpolation_on_completed(req):
            result = js.JSON.parse(req.text)
            interpolation_data = result.get("interpolation", None)
            boundary = result.get("boundary", None)

            try:
                if interpolation_data:
                    self.map.set_shape_with_key(interpolation_data, key)
                    # if have boundary delete and re-add to make sure it's on top of interpolation layer
                    if boundary:
                        if "boundary" in self.map.shapes:
                            self.map.map.removeLayer(self.map.shapes["boundary"])
                            del self.map.shapes["boundary"]
                        self.map.set_shape_boundary(boundary)
                else:
                    print("No interpolation data received")

            except Exception as e:
                print("Error in adding interpolation layer:", e)
                self.reset_other_interpolation_button("All")
                self.reset_interpolation_params()
            finally:
                document["loading_map"].className = "ui inactive inverted dimmer"
                self.params_mode("enable")

        self.params_mode("disable")
        params = dict(
            source=source,
            formula=formula,
            interpolate_class=interpolate_class,
            interpolate_model=interpolate_model,
            **kwargs,
        )
        document["loading_map"].className = "ui active inverted dimmer"
        ajax.get(
            url,
            data=urlencode(params),
            oncomplete=interpolation_on_completed,
            cache=True,
        )

    def get_interpolation(self, doc_id, mode, started_datetime=None):
        print("Get interpolation with params:", doc_id, mode, started_datetime)
        extra_params = {}
        if doc_id == "PM_2_5_prediction":
            url = self.get_prediction_interpolation_url
            extra_params = {
                "predict_date": self.start_predict_date,
                "target_timestamp": self.target_timestamp,
            }
        elif doc_id == "empirical_PM_0_1_forecast":
            url = self.get_empirical_forecast_url
            extra_params = {"started_datetime": started_datetime}
        elif doc_id == "empirical_PM_0_1":
            url = self.get_interpolation_url
            extra_params = {"sensor_type": "PM_2_5", "formula": "PM_0_1_forecast"}
        elif doc_id == "empirical_PM_1":
            url = self.get_interpolation_url
            extra_params = {"sensor_type": "PM_2_5", "formula": "PM_1_forecast"}

        params = self.interpolation_params[mode]

        required_fields = {
            "kriging": ["interpolate_class", "interpolate_model"],
            "simple": ["interpolate_model"],
            "idw": [],
        }
        required = required_fields.get(mode, [])
        if mode != "idw" and not all(params.get(k) for k in required):
            return

        self.reset_other_interpolation_button(mode)

        for m in required_fields.keys():
            self.remove_interpolation_layer(m)
        self.reset_interpolation_params(mode)

        self.add_interpolation(
            url,
            source="air4thai",
            key=mode,
            interpolate_class=params.get("interpolate_class", ""),
            interpolate_model=params.get("interpolate_model", ""),
            formula=extra_params.pop("formula", params.get("formula", "")),
            **extra_params,
        )

    def on_interpolation_parameter_clicked(
        self, ev, sensor_type, mode, started_datetime=None
    ):
        self.remove_interpolation_layer(mode)
        doc_id = ev.target.id
        prefix = f"{mode}_"

        formulas = document.select(f'[name="{prefix}formula"]')
        params = self.interpolation_params[mode]

        mode_config = {
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

        config = mode_config.get(mode, {})
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

        if sensor_type == "PM_2_5_prediction":
            params["predict_date"] = self.start_predict_date
            params["target_timestamp"] = self.target_timestamp
        elif sensor_type == "empirical_PM_0_1_forecast":
            params["started_datetime"] = self.start_predict_date

        self.get_interpolation(
            sensor_type,
            mode,
            started_datetime=started_datetime,
        )
