from urllib.parse import urlencode

import javascript as js
from browser import ajax, document, html, window, timer, aio


class Climates:
    def __init__(self, source, map_, api_url):
        self.source = source
        self.map = map_
        self.api_url = api_url

        self.sources = [
            "air4thai",
            "meteorological",
            "airport",
            "santhings",
        ]

        self.sensor_types = [
            "PM_0_1",
            "PM_1",
            "PM_2_5",
            "PM_10",
            "humidity",
            "wind_direction",
            "rain",
            "temperature",
            "pressure",
            "CO",
            "O3",
            "SO2",
            "NO2",
        ]

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
        self.interpolattion_sensors = {
            "pm_2_5": "PM_2_5",
            "temperature": "temperature",
            "humidity": "humidity",
        }

        self.interpolation_params = {
            "kriging": {
                "sensor": None,
                "formula": None,
                "interpolate_class": None,
                "interpolate_model": None,
            },
            "simple": {
                "sensor": None,
                "formula": None,
                "interpolate_model": None,
            },
            "idw": {
                "sensor": None,
            },
        }

        self.get_interpolation_url = f"{api_url}/v1/interpolations/kriging/interpolate"

    async def get_station_latest_climate_data(self, url, params):
        response = await aio.get(url, data=params, cache=True)
        stations = js.JSON.parse(response.data)
        return stations

    def on_type_changed(self, doc_id):
        # เมื่อกดปุ่ม sensor types
        if doc_id == "parameters_button":
            document["parameters_menu"].style.display = "block"
            document["stations_menu"].style.display = "none"
            document["stations_button"].className = "ui button"
            document["parameters_button"].className = "ui positive button"
            for source in self.sources:
                if source in document:
                    if document[source].checked:
                        self.map.remove_climates_layer(source)
                        self.map.remove_climate_legend(source)

            for sensor_type in self.sensor_types:
                if sensor_type in document:
                    if document[sensor_type].checked:
                        self.map.set_all_sensor_marker(sensor_type)
                        aio.run(self.map.update_climate_legend(sensor_type))

        # เมื่อกดปุ่ม source
        elif doc_id in "stations_button":
            document["parameters_menu"].style.display = "none"
            document["stations_menu"].style.display = "block"
            document["stations_button"].className = "ui positive button"
            document["parameters_button"].className = "ui button"
            for sensor_types in self.sensor_types:
                if sensor_types in document:
                    if document[sensor_types].checked:
                        self.map.remove_climates_layer(sensor_types)
                        self.map.remove_climate_legend(sensor_types)

            for source in self.sources:
                if source in document:
                    if document[source].checked:
                        self.map.set_all_sensor_marker(source)
                        aio.run(self.map.update_climate_legend(source))

    ### Interpolations
    def remove_all_interpolation_layer(self):
        for key in list(self.interpolation_params.keys()):
            self.remove_interpolation_layer(key)

    def remove_interpolation_layer(self, key):
        if key in self.map.shapes.keys():
            print(f"remove '{key}' interpolate layer")
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
    ):
        def interpolation_on_completed(req):
            print("Interpolation on completed", req.status)
            result = js.JSON.parse(req.text)
            interpolate_data = result.get("interpolation", None)
            boundary_data = result.get("boundary", None)

            if interpolate_data:
                self.map.set_shape_with_key(interpolate_data, key)
                if boundary_data:
                    self.map.set_shape_boundary(boundary_data)

            document["loading_map"].className = "ui inactive inverted dimmer"

        params = dict(
            source=source,
            sensor_type=sensor_type,
            formula=formula,
            interpolate_class=interpolate_class,
            interpolate_model=interpolate_model,
        )
        document["loading_map"].className = "ui active inverted dimmer"

        ajax.get(
            url,
            data=urlencode(params),
            oncomplete=interpolation_on_completed,
            cache=True,
        )

    def get_interpolation(self, mode):
        url = f"{self.get_interpolation_url}"
        params = self.interpolation_params[mode]

        required_fields = {
            "kriging": ["sensor", "interpolate_class", "interpolate_model"],
            "simple": ["sensor", "interpolate_model"],
            "idw": ["sensor"],
        }

        required = required_fields.get(mode, [])
        if not all(params.get(k) for k in required):
            return

        self.remove_interpolation_layer(mode)

        self.add_interpolation(
            url,
            source="air4thai",
            sensor_type=params["sensor"],
            formula=params.get("formula", ""),
            key=mode,
            interpolate_class=params.get("interpolate_class", ""),
            interpolate_model=params.get("interpolate_model", ""),
        )

    def on_interpolation_parameter_clicked(self, ev, mode):
        self.remove_interpolation_layer(mode)
        doc_id = ev.target.id
        prefix = f"{mode}_"

        formulas = document.select(f'[name="{prefix}formula"]')
        sensors = document.select(f'[name="{prefix}sensor"]')
        params = self.interpolation_params[mode]

        mode_config = {
            "kriging": {
                "classes": self.kriging_classes,
                "models": self.kriging_models,
                "sensors": self.kriging_sensors,
            },
            "simple": {
                "classes": [],
                "models": self.simple_models,
                "sensors": self.simple_sensors,
            },
            "idw": {
                "classes": [],
                "models": [],
                "sensors": self.idw_sensors,
            },
        }

        config = mode_config.get(mode, {})
        classes = config["classes"]
        models = config["models"]
        sensor_map = config["sensors"]
        sensor_types = list(sensor_map.keys())

        if doc_id not in document and not document[doc_id].checked:
            return

        if doc_id in sensor_types:
            if mode in ["kriging", "simple"]:
                if doc_id.endswith("temperature") or doc_id.endswith("humidity"):
                    document[f"{prefix}interpolate_formulas"].style.display = "none"
                    for el in formulas:
                        el.checked = False
                    params["formula"] = ""
                else:
                    if not params.get("formula"):
                        raw_toggle_id = f"{mode}_raw_data"
                        if raw_toggle_id in document:
                            document[raw_toggle_id].checked = True
                            params["formula"] = ""
                    document[f"{prefix}interpolate_formulas"].style.display = "block"

            params["sensor"] = sensor_map.get(doc_id)

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

        self.get_interpolation(mode)
