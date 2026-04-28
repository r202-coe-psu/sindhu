from browser import aio, timer, document, ajax
import javascript as js
import datetime
from urllib.parse import urlencode

from maps.main import MainMap


class BaseMonitor:
    def __init__(
        self,
        lang_code,
        api_url,
        source,
        center=None,
        zoom=None,
    ):
        self.lang_code = lang_code
        self.acquisition_interval = 60 * 60

        self.running = False

        self.api_url = api_url
        self.source = source
        self.center = center
        self.zoom = zoom

        self.monitor_name = "base"

        # hardcoded URL
        self.params = None
        self.apis = {
            "stations": {
                "climates": {"latest": f"{api_url}/v1/stations/climates/latest"}
            },
            "system_settings": f"{api_url}/v1/system_settings",
        }

        self.sources = [
            "air4thai",
            "meteorological",
            "airport",
            "santhings",
        ]

        self.source_mapping = {
            "air4thai": "air4thai",
            "meteorological": "meteorological",
            "airport": "port-api",
            "santhings": "santhings-api",
        }

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

        # interpolation
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
        self.kriging_sensors = {}
        self.simple_sensors = {}
        self.idw_sensors = {}

        self.interpolate_mode = None

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
        self.required_interpolation_params = {
            "kriging": ["interpolate_class", "interpolate_model", "sensor"],
            "simple": ["interpolate_model", "sensor"],
            "idw": ["sensor"],
        }

        self.interpolates_build_config = {
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

    """
    ===========================================================================
    Main functions
    ===========================================================================
    """

    def start(self):
        """Start function defined in child class"""
        pass

    async def monitor(self):
        await self.setup()

        while self.running:
            print(f"monitor: wake up {datetime.datetime.now()}")
            print(f"monitor: {self.monitor_name} monitor")
            print(f"monitor: sleep {self.acquisition_interval}s")

            params = dict(source=self.source)
            stations = await self.fetch_stations(
                self.apis["stations"]["climates"]["latest"], params
            )
            await self.map.update(self.source, stations)

            # wait for next aquisition
            await aio.sleep(self.acquisition_interval)

    async def setup(self):
        response = await aio.get(self.apis["system_settings"], cache=True)
        self.system_setting = js.JSON.parse(response.data)

        center = self.system_setting["center"]["coordinates"]
        zoom = self.system_setting["zoom"]
        min_zoom = self.system_setting["min_zoom"]

        self.map = MainMap([center[1], center[0]], zoom, min_zoom, self.lang_code)

    def on_filter_clicked(self, ev):
        timer.set_timeout(lambda: aio.run(self.on_filter(ev)), 50)

    async def on_filter(self, ev):
        """Filter function defined in child class"""
        return

    """
    ===========================================================================
    Helper functions
    ===========================================================================
    """

    async def fetch_stations(self, url, params):
        response = await aio.get(url, data=params, cache=True)
        stations = js.JSON.parse(response.data)

        return stations

    def set_map_loading(self, loading):
        if loading:
            document["loading_map"].className = "ui active inverted dimmer"
        else:
            document["loading_map"].className = "ui inactive inverted dimmer"

    def show_interpolation_control_panel(self, show):
        if show:
            document["interpolation_control_panel"].style.display = "block"
        else:
            document["interpolation_control_panel"].style.display = "none"

    def show_sub_interpolate_choice(self, doc_id, show):
        if show:
            document[f"{doc_id}_choices"].style.display = "block"
        else:
            document[f"{doc_id}_choices"].style.display = "none"

    def remove_climates_interpolation_layers(self, doc_id):
        self.map.remove_climates_layer(doc_id)
        self.map.remove_climate_legend(doc_id)

        # remove interpolate layer if exist
        self.remove_all_interpolation_layer()
        self.interpolate_mode = None

    def remove_all_interpolation_layer(self):
        for key in self.map.shapes.keys():
            self.remove_interpolation_layer(key)

    def remove_interpolation_layer(self, key):
        if key in self.map.shapes.keys():
            self.map.map.removeLayer(self.map.shapes[key])
        if "boundary" in self.map.shapes:
            self.map.map.removeLayer(self.map.shapes["boundary"])
            del self.map.shapes["boundary"]

    def reset_interpolation_params(self, selected_mode=None):
        """Reset interpolation parameters, if selected_mode is provided, only reset other mode's parameters"""
        for mode in self.interpolation_params.keys():
            if mode == selected_mode:
                continue
            for key in self.interpolation_params[mode].keys():
                self.interpolation_params[mode][key] = None
            # uncheck parameters in UI

    def reset_other_interpolation_button(self, interpolate_mode):
        """Reset back to unchecked position"""
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

    def reset_interpolation_param_buttons(self, mode=None):
        if not mode:
            modes = self.interpolation_params.keys()
        else:
            modes = [mode]
        for mode in modes:
            mode_build_config = self.interpolates_build_config.get(mode, {})
            for param_doc_id in mode_build_config.get("classes", []):
                if param_doc_id in document:
                    print(f"Reset {param_doc_id} to unchecked")
                    document[param_doc_id].checked = False
            for param_doc_id in mode_build_config.get("models", []):
                if param_doc_id in document:
                    print(f"Reset {param_doc_id} to unchecked")
                    document[param_doc_id].checked = False

    def on_interpolates_clicked(self, ev, selected_sensor_type=None):
        document_ = ev.target
        doc_id = document_.id
        mode = doc_id.replace("_interpolation", "")

        if document_.checked:
            self.show_sub_interpolate_choice(doc_id, True)

            # index page mode
            mode = doc_id.replace("_interpolation", "")

            # set mode (kriging, simple, idw)
            self.interpolate_mode = mode
            prefix = f"{mode}_"

            # Get formulas for the selected mode
            formulas = document.select(f"[name='{prefix}formula']")
            formula_ids = [f.id for f in formulas]

            # build parameters from self.interpolates_build_config
            parameters = []
            mode_build_config = self.interpolates_build_config.get(mode, {})
            for config in mode_build_config.keys():
                parameters += mode_build_config[config]
            parameters += formula_ids

            # Bind click event for parameters
            for param in parameters:
                document[param].bind(
                    "click",
                    lambda ev, m=mode: self.on_interpolation_parameter_clicked(
                        ev,
                        sensor_type=selected_sensor_type,
                        mode=m,
                    ),
                )
        else:
            print(f"{doc_id} unchecked")
            print(f"Mode: {mode}")
            self.show_sub_interpolate_choice(doc_id, False)
            # remove interpolate layer if exist
            self.remove_interpolation_layer(mode)
            # remove parameters for the mode
            self.reset_interpolation_params()
            # uncheck and reset parameters
            self.reset_interpolation_param_buttons(mode)

    def set_interpolation(self, url, sensor_type, mode, extra_params={}):
        params = self.interpolation_params[mode]

        # check required parameters based on interpolates_build_config
        required = self.required_interpolation_params.get(mode, [])
        if not all(params.get(k) for k in required):
            return

        self.reset_other_interpolation_button(mode)
        self.remove_all_interpolation_layer()

        # remove others interpolation params, prevent collision of api
        self.reset_interpolation_params(mode)

        self.fetch_interpolates(
            url,
            source=self.source,
            mode=mode,
            interpolate_class=params.get("interpolate_class", ""),
            interpolate_model=params.get("interpolate_model", ""),
            formula=params.pop("formula", params.get("formula", "")),
            extra_params=extra_params,
        )

    def on_interpolation_parameter_clicked(self, ev, sensor_type, mode):
        """
        Set up interpolates parameters based on clicked parameter and fetch new interpolation layer
        """
        self.remove_interpolation_layer(mode)
        doc_id = ev.target.id
        prefix = f"{mode}_"

        formulas = document.select(f'[name="{prefix}formula"]')

        # Reference Variables for interpolation parameters
        params = self.interpolation_params[mode]

        config = self.interpolates_build_config.get(mode, {})
        classes = config["classes"]
        models = config["models"]

        # ensure the clicked parameter is valid for the current mode
        if doc_id not in document:
            return
        if not document[doc_id].checked:
            return

        if doc_id in classes:
            # update parameters based on clicked parameter
            params["interpolate_class"] = doc_id

        if doc_id in models:
            # update parameters based on clicked parameter
            params["interpolate_model"] = doc_id

        if doc_id in formulas:
            # formula case
            formula = doc_id.replace(prefix, "")
            if formula == "raw_data":
                params["formula"] = ""
            else:
                params["formula"] = formula

        self.set_interpolation(sensor_type, mode)

    def fetch_interpolates(
        self,
        url,
        source,
        formula="",
        mode="",
        interpolate_class="",
        interpolate_model="",
        extra_params={},
    ):
        def on_interpolation_completed(req):
            result = js.JSON.parse(req.text)
            interpolates_data = result.get("interpolation", None)
            boundary = result.get("boundary", None)

            try:
                if interpolates_data:
                    self.map.set_shape_with_key(interpolates_data, mode)
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
                self.set_map_loading(False)
                self.set_date_selectable(True)

        params = dict(
            source=source,
            formula=formula,
            interpolate_class=interpolate_class,
            interpolate_model=interpolate_model,
            **extra_params,
        )

        self.set_map_loading(True)
        self.set_date_selectable(False)

        ajax.get(
            url,
            data=urlencode(params),
            oncomplete=on_interpolation_completed,
            cache=True,
        )
