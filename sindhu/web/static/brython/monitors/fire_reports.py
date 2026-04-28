from urllib.parse import urlencode

import javascript as js
from browser import ajax, document, html, window, timer, aio
import datetime


class FireReport:
    def __init__(self, source, map_, api_url):
        self.source = source
        self.map = map_
        self.api_url = api_url

        self.report_name = None
        self.reports = None
        self.last_selected_year = None

        self.fire_reports = ["FAHP", "dNBR", "AOD", "MLBA", "Emissions"]
        self.enso_based_reports = ["MLBA", "Emissions"]

        self.report_data = {}
        self.report_params = {name: {} for name in self.fire_reports}

        self.report_file_url = f"{api_url}/v1/data/sample_doc_id/"
        self.fire_report_interpolate = f"{api_url}/v1/climates/interpolate/aod/"

    async def get_fire_reports_data(self, url, params):
        # aio Future ใช้เพื่อรอจนกว่า ajax ทำงานเสร็จ เพื่อโหลดข้อมูล fire report เรียบร้อย
        future = aio.Future()

        def on_completed(req):
            summary_data = js.JSON.parse(req.text)
            fire_reports = summary_data.get("fire_reports", [])
            if fire_reports:
                self.report_data = summary_data
            future.set_result(True)  # is completed

        ajax.get(url, data=urlencode(params), oncomplete=on_completed, cache=True)

        await future

    def get_fire_report_file(self, url):
        self.map.remove_all_fire_report_layers()
        self.map.remove_all_fire_report_legends()

        sample_doc_id = self.report_params.get(self.report_name, {})

        if sample_doc_id.get("sample_doc_id"):
            document["loading_map"].className = "ui active inverted dimmer"

            ajax.get(
                url,
                data=urlencode({"sample_doc_id": sample_doc_id.get("sample_doc_id")}),
                oncomplete=self.get_fire_report_file_on_completed,
                cache=True,
            )
        else:
            return

        self.report_params[self.report_name] = {}

    def get_fire_report_file_on_completed(self, req):
        fire_report = js.JSON.parse(req.text)
        document["loading_map"].className = "ui inactive inverted dimmer"
        aio.run(self.map.update(self.report_name, fire_report))

    def remove_all_interpolation_layer(self):
        for key in list(self.map.shapes.keys()):
            self.remove_interpolation_layer(key)

    def remove_interpolation_layer(self, key):
        if key in self.map.shapes.keys():
            print(f"remove '{key}' interpolate layer")
            self.map.map.removeLayer(self.map.shapes[key])

    def add_interpolation(
        self,
        url,
        source,
        sensor_type=None,
        interpolate_pm=None,
        key=None,
        timestamp=None,
    ):
        def interpolation_on_complete(req):
            genojson = js.JSON.parse(req.text)
            document["loading_map"].className = "ui inactive inverted dimmer"
            aod_interpolate_warning = document["fire_report_aod_interpolate_warning"]
            aod_interpolate_warning.style.display = "none"

            if not genojson:
                aod_interpolate_warning.textContent = f"ไม่มีข้อมูลสำหรับวันที่ {timestamp}."
                aod_interpolate_warning.style.display = "block"
                return

            self.map.set_shape_with_key(js.JSON.parse(req.text), key)
            aio.run(self.map.update_climate_legend(self.report_name))

        params = dict(
            source=source,
            sensor_type=sensor_type,
            interpolate_pm=interpolate_pm,
            timestamp=timestamp,
        )
        document["loading_map"].className = "ui active inverted dimmer"

        ajax.get(
            url,
            data=urlencode(params),
            oncomplete=interpolation_on_complete,
            cache=True,
        )

    def on_search_clicked(self, ev):
        self.map.remove_all_climate_legends()
        self.remove_interpolation_layer("AOD_interpolation")

        params = self.report_params.get("AOD", {})
        interpolate_pm = params.get("model_source")

        timestamp_str = document["started_datetime"].value
        timestamp = None

        if timestamp_str:
            timestamp = datetime.datetime.strptime(timestamp_str, "%Y-%m-%d")
        else:
            now = datetime.datetime.now(datetime.timezone.utc)
            timestamp = now - datetime.timedelta(days=1)

        timestamp = timestamp.date().isoformat()

        url = f"{self.fire_report_interpolate}"

        self.add_interpolation(
            url,
            "NASA-aod",
            sensor_type="AOD",
            interpolate_pm=interpolate_pm,
            key="AOD_interpolation",
            timestamp=timestamp,
        )

        params = {}

    def render_year_option(self, year, enabled):
        container = html.DIV(
            Class="ui toggle checkbox",
            style={
                "padding-bottom": "0.5rem",
                "display": "flex",
                "align-items": "center",
            },
        )
        input_el = html.INPUT(
            type="radio", Id=year, name="fire_report_year_panel", disabled=not enabled
        )
        label = html.LABEL(
            year,
            For=year,
            style={
                "font-size": "1.3rem",
                "font-weight": "bold",
                "margin-right": "0.5rem",
            },
        )
        msg = (
            html.SPAN(
                "(Missing JSON file)",
                style={"font-size": "1rem", "color": "gray", "font-style": "italic"},
            )
            if not enabled
            else html.SPAN()
        )
        container <= input_el + label + msg
        document["fire_report_year_panel"] <= container

    def on_model_source_selected(self, ev):
        model_source = ev.target.id

        document["fire_report_calendar_panel"].style.display = "block"
        params = self.report_params.get("AOD", {})
        params["model_source"] = model_source

        if not params:
            return

        if "fire_report_search_data_button" in document:
            document["fire_report_search_data_button"].unbind("click")
            document["fire_report_search_data_button"].bind(
                "click", self.on_search_clicked
            )

    def on_fire_report_category_selected(self, ev):
        report_type = ev.target.id

        if report_type not in document or not document[report_type].checked:
            return

        self.report_name = report_type
        self.remove_all_interpolation_layer()
        self.map.remove_all_climate_legends()

        document["fire_report_year_panel"].clear()
        document["fire_report_calendar_panel"].style.display = "none"
        document["fire_report_enso_phase_panel"].style.display = "none"
        document["fire_report_model_source_panel"].style.display = "none"

        for el in document.select("input[name='model_source']"):
            el.checked = False

        if report_type in ["AOD"]:
            document["fire_report_year_panel"].style.display = "none"
            document["fire_report_model_source_panel"].style.display = "block"

            for el in document.select("[name='model_source']"):
                if not hasattr(el, "bound"):
                    el.bind("click", self.on_model_source_selected)
                    el.bound = True
        else:
            fire_reports = self.report_data.get("fire_reports", [])
            matching = [r for r in fire_reports if r.get("category") == report_type]

            if not matching:
                document["fire_report_year_panel"] <= html.DIV(
                    f"ไม่พบข้อมูลสำหรับ {report_type} สามารถ Upload ได้ที่ Upload file repoort.",
                    Class="ui warning message",
                )
                document["fire_report_year_panel"].style.display = "block"
                return

            unique_by_year = {}
            for report in matching:
                year = report["year"]
                if year not in unique_by_year:
                    unique_by_year[year] = report

            for year, rep in unique_by_year.items():
                self.render_year_option(year, rep.get("sample_doc_id") is not None)

            document["fire_report_year_panel"].style.display = "block"

            for el in document.select("[id='fire_report_year_panel']"):
                el.unbind("click")  # เคลียร์ของเก่าออก
                el.bind(
                    "click",
                    lambda event, reports=matching: self.on_year_selected(
                        event, reports
                    ),
                )
                el.bound = True

    def on_year_selected(self, ev, reports):
        if getattr(ev.target, "_locked", False):
            return

        ev.target._locked = True
        selected_year = ev.target.id

        window.setTimeout(lambda: setattr(ev.target, "_locked", False), 5000)

        report_type = self.report_name
        self.last_selected_year = selected_year
        self.reports = reports

        for el in document.select("input[name='enso_phase']"):
            el.checked = False

        if report_type not in document:
            return

        reports_this_year = [r for r in reports if r["year"] == selected_year]
        if not reports_this_year:
            return

        selected_report = reports_this_year[0]

        if report_type in self.enso_based_reports:
            document["fire_report_enso_phase_panel"].style.display = "block"

            for el in document.select("input[name='enso_phase']"):
                if not el.classList.contains("bound"):
                    el.classList.add("bound")
                    el.bind(
                        "click",
                        lambda ev, report_type=report_type: self.on_enso_phase_selected(
                            ev, report_type
                        ),
                    )
        else:
            self.report_params[report_type]["sample_doc_id"] = selected_report.get(
                "sample_doc_id"
            )
            self.get_fire_report_file(self.report_file_url)

    def on_enso_phase_selected(self, ev, report_type):
        selected_enso_phase = ev.target.id
        reports = self.reports
        enso_label_map = {
            "el_nino": "El Niño",
            "la_nina": "La Niña",
            "neutral": "Neutral",
        }
        selected_phase_label = enso_label_map.get(selected_enso_phase)

        warning_el = document["fire_report_enso_phase_warning"]
        warning_el.style.display = "none"

        selected_year = self.last_selected_year
        if not selected_year:
            return

        matching_report = next(
            (
                r
                for r in reports
                if r["year"] == selected_year
                and r.get("enso_phase") == selected_phase_label
            ),
            None,
        )

        if matching_report and matching_report.get("sample_doc_id"):
            self.report_params[report_type]["sample_doc_id"] = matching_report[
                "sample_doc_id"
            ]
            self.get_fire_report_file(self.report_file_url)
        else:
            warning_el.textContent = (
                f"ไม่มีข้อมูลสำหรับปี {selected_year} '{selected_phase_label}' phase."
            )
            warning_el.style.display = "block"
            return
