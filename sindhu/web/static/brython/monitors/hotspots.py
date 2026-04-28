from urllib.parse import urlencode

import javascript as js
from browser import ajax, document, html, window, timer, aio

import datetime


class Hotspot:
    def __init__(self, source, map_, api_url):
        self.source = source
        self.map = map_
        self.api_url = api_url

        self.get_hotspots_url = f"{api_url}/v1/hotspots/latest"

        self.hotspots = [
            "viir_hotspots",
            "noaa-20_hotspots",
            "noaa-21_hotspots",
            "suomi_hotspots",
            "modis_hotspots",
        ]
        self.hotspot_display_options = [
            "display_cumulative",
            "display_non_cumulative",
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

        self.satellites = {
            "viir_hotspots": ["noaa-20", "noaa-21", "suomi"],
            "modis_hotspots": ["modis"],
        }

        self.hotspot_params = {
            "modis_hotspots": {
                "display_mode": None,
                "time_period": None,
            },
            "viir_hotspots": {
                "display_mode": None,
                "time_period": None,
            },
        }

        self.selected_modes = []

    def draw_fire(self, mode, hotspot, is_live_update=False):
        params = self.hotspot_params[mode]
        display_mode = params.get("display_mode", "")
        if display_mode in ["display_non_cumulative"]:
            self.map.remove_hotspots_layer(mode)

        aio.run(self.map.update(mode, hotspot, is_live_update))
        # aio.run(self.update_hotspot_informations(document_id, hotspot))

    def add_hotspots(self, url, mode):
        def hotspots_on_completed(req):
            response = js.JSON.parse(req.text)
            hotspots = response["hotspots"]

            document["loading_map"].className = "ui inactive inverted dimmer"

            if len(hotspots) == 1:
                self.draw_fire(mode, hotspots[0], True)
            else:
                for i, hotspot in enumerate(hotspots):
                    timer.set_timeout(
                        self.draw_fire, i * 1000, mode, hotspot
                    )  # หน่วงเวลาบน browers เพราะว่า time.sleep ไม่สามารถทำได้ เพราะเป็นการ block web

            document["loading_map"].className = "ui inactive inverted dimmer"

        document["loading_map"].className = "ui active inverted dimmer"

        params = dict()
        aio.run(self.map.update_hotspot_legend(mode))

        ajax.get(
            url,
            data=urlencode(params),
            oncomplete=hotspots_on_completed,
            cache=True,
        )

    def on_search_clicked(self, ev):
        self.map.remove_all_hotspots_layer()
        self.map.remove_all_hotspot_legends()

        started_datetime_str = document["started_datetime"].value
        ended_datetime_str = document["ended_datetime"].value

        if started_datetime_str and ended_datetime_str:
            started_datetime = datetime.datetime.strptime(
                started_datetime_str, "%Y-%m-%d"
            )
            ended_datetime = datetime.datetime.strptime(ended_datetime_str, "%Y-%m-%d")
        else:
            ended_datetime = datetime.datetime.now(datetime.timezone.utc)
            started_datetime = ended_datetime - datetime.timedelta(days=1)

        started_iso = started_datetime.isoformat().split("+")[0]
        ended_iso = ended_datetime.isoformat().split("+")[0]

        for mode in self.selected_modes:
            satellites = self.satellites.get(mode, [])

            satellites_query = "".join(
                f"&satellites={sat}" for sat in satellites if sat
            )

            hotspots_url = (
                f"{self.get_hotspots_url}?source=firms{satellites_query}"
                f"&started_datetime={started_iso}&ended_datetime={ended_iso}&"
            )

            self.add_hotspots(hotspots_url, mode)

    def get_hotspots_data(self, mode):
        params = self.hotspot_params[mode]

        ended_datetime = datetime.datetime.now(datetime.timezone.utc)
        started_datetime = ended_datetime - datetime.timedelta(days=1)

        required_fields = {
            "modis_hotspots": ["display_mode", "time_period"],
            "viir_hotspots": ["display_mode", "time_period"],
        }

        required = required_fields.get(mode, [])
        if not all(params.get(k) for k in required):
            return

        display_mode = params.get("display_mode")
        time_preiod = params.get("time_period")

        value, unit = time_preiod.split("_")
        duration = int(value)

        if unit == "hours":
            started_datetime = ended_datetime - datetime.timedelta(hours=duration)
        elif unit == "days":
            started_datetime = ended_datetime - datetime.timedelta(days=duration - 1)

        started_datetime = started_datetime.replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        ended_datetime = ended_datetime.replace(
            hour=23, minute=59, second=59, microsecond=0
        )

        document["time_preiod_header"].text = time_preiod.replace("_", "").upper()
        document["time_preiod_label"].text = (
            f"[{started_datetime.date()} {started_datetime.strftime('%H:%M:%S')}]"
        )
        document["time_preiod_detail"].innerHTML = (
            f"From <span class='ui label' id='time_preiod_label'>{document['time_preiod_label'].text}</span> to present"
        )

        satellites = self.satellites.get(mode)

        satellites_name = ""
        for satellite in satellites:
            if not satellite:
                continue

            satellites_name += f"&satellites={satellite}"

        started_datetime = started_datetime.isoformat().split("+")[0]
        ended_datetime = ended_datetime.isoformat().split("+")[0]

        hotspots_url = f"{self.get_hotspots_url}?source=firms{satellites_name}&started_datetime={started_datetime}&ended_datetime={ended_datetime}&"

        self.add_hotspots(hotspots_url, mode)

    def on_hotspots_parameter_clicked(self, ev, modes):
        doc_id = ev.target.id
        if doc_id not in document:
            return

        self.map.remove_all_hotspots_layer()
        self.map.remove_all_hotspot_legends()
        self.selected_modes = modes
        print(f"selected mode parameter --> {self.selected_modes}")

        for mode in modes:
            params = self.hotspot_params.get(mode, {})
            self.hotspot_name = mode

            if doc_id in self.hotspot_display_options:
                for _id in self.hotspot_display_options:
                    document[_id].style.backgroundColor = ""
                document[doc_id].style.backgroundColor = "#0056B7"

                params["display_mode"] = doc_id

            elif doc_id in self.time_periods:
                for _id in self.time_periods:
                    document[_id].style.backgroundColor = ""
                document[doc_id].style.backgroundColor = "#0056B7"

                if doc_id == "custom":
                    document["hotspot_calendar_panel"].style.display = "block"
                    document["hotspots_time_period_info_panel"].style.display = "none"

                    params["time_period"] = None

                    if "hotspot_search_data_button" in document:
                        document["hotspot_search_data_button"].unbind("click")
                        document["hotspot_search_data_button"].bind(
                            "click", self.on_search_clicked
                        )

                else:
                    document["hotspot_calendar_panel"].style.display = "none"
                    document["hotspots_time_period_info_panel"].style.display = "block"
                    params["time_period"] = doc_id

            print(f"[{mode}] params --> {params}")
            if doc_id != "custom":
                self.get_hotspots_data(mode)
