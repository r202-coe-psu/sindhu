import datetime
from browser import ajax, document, html, window, timer, aio
import javascript as js
from . import charts
import stations


class StationChartMonitor:
    def __init__(
        self,
        station_id,
        api_url,
        lang_code="th",
        started_datetime=None,
        ended_datetime=None,
        every=None,
        chart_times=["daily", "hourly"],
    ):
        self.station_id = station_id
        self.lang_code = lang_code
        self.api_url = api_url
        self.started_datetime = started_datetime
        self.ended_datetime = ended_datetime
        self.chart_times = chart_times

        self.is_monitor = False
        # if not self.started_datetime and not self.ended_datetime:
        #     self.is_monitor = True

        self.acquisition_interval = 60 * 60
        if "minute" in self.chart_times:
            self.acquisition_interval = 60

        self.running = False

        # self.get_token_url = f"/{lang_code}/get_token"
        # self.get_system_setting_url = f"{api_url}/v1/system_settings"
        self.get_station_url = f"{api_url}/v1/stations/{station_id}"
        self.get_station_sensors_url = f"{api_url}/v1/stations/{station_id}/sensors"
        self.get_station_sensor_data_url = f"{api_url}/v1/climates"

        self.station_setting = dict()

        self.first_time = True

    async def request_station_data(self):
        for type_, sensor in self.station.sensors.items():
            await self.get_sensor_data(sensor)

        if self.first_time:
            await self.station_chart_renderer.render()
            self.first_time = False

        await self.station_chart_renderer.update()

    async def get_sensor_data(self, sensor):
        started_datetime_str = document["started_datetime"].value
        ended_datetime_str = document["ended_datetime"].value
        quick_range = document["quick_range"].value
        every = document["every"].value

        if started_datetime_str and ended_datetime_str:
            started_datetime = (
                datetime.datetime.strptime(
                    started_datetime_str, "%Y-%m-%d %H:%M"
                ).astimezone(datetime.timezone.utc)
            ) + datetime.timedelta(hours=7)
            ended_datetime = (
                datetime.datetime.strptime(
                    ended_datetime_str, "%Y-%m-%d %H:%M"
                ).astimezone(datetime.timezone.utc)
            ) + datetime.timedelta(hours=7)
        else:
            ended_datetime = datetime.datetime.now(datetime.timezone.utc)
            started_datetime = ended_datetime - datetime.timedelta(days=5)

        if quick_range:
            ended_datetime = datetime.datetime.now(datetime.timezone.utc)
            started_datetime = ended_datetime - datetime.timedelta(
                days=int(quick_range.split("d")[0])
            )

        params = dict(station_id=self.station_id, sensor_type=sensor.type)
        # api_headers = {
        #     "Authorization": f"{self.token.get('token_type')} {self.token.get('access_token')}"
        # }

        if started_datetime:
            params["started_datetime"] = started_datetime.isoformat().split("+")[0]

        if ended_datetime:
            params["ended_datetime"] = ended_datetime.isoformat().split("+")[0]

        if every:
            params["every"] = every

        # response = await aio.get(
        #     self.get_station_sensor_data_url,
        #     headers=api_headers,
        #     data=params,
        # )
        response = await aio.get(
            self.get_station_sensor_data_url,
            # headers=api_headers,
            data=params,
            cache=True,
        )

        data = js.JSON.parse(response.data)
        await sensor.update("daily", data)

    async def monitor(self):
        await self.setup()

        while self.running:
            print(f"monitor: weak up {datetime.datetime.now()}")
            # await self.request_station_data()
            print(f"monitor: sleep {self.acquisition_interval}s")
            # wait for next aquisition
            await aio.sleep(self.acquisition_interval)

    async def setup(self):
        # response = await aio.get(self.get_token_url)
        # self.token = js.JSON.parse(response.data)
        # api_headers = {
        #     "Authorization": f"{self.token.get('token_type')} {self.token.get('access_token')}"
        # }

        self.station = stations.Station()

        # response = await aio.get(self.get_station_url, headers=api_headers)
        response = await aio.get(self.get_station_url)

        data = js.JSON.parse(response.data)
        await self.station.update(data)

        # response = await aio.get(self.get_station_sensors_url, headers=api_headers)
        response = await aio.get(self.get_station_sensors_url, cache=True)

        data = js.JSON.parse(response.data)
        await self.station.update_sensors(data)
        self.station_chart_renderer = charts.StationChartRenderer(
            self.station.sensors, self.lang_code
        )

        await self.update_station_information()

    async def update_station_information(self):
        INFO_UPDATE = [
            ("station-name", self.station.name),
            ("device-name", ""),
            ("station-location", self.station.location),
            ("station-model", self.station.model),
            ("station-operator", self.station.operator),
            ("station-contributor", self.station.contributor),
            ("station-contributor-url", self.station.contributor_url),
            ("station-logo", self.station.logo_url),
            ("source", self.station.source),
        ]
        for element_id, info in INFO_UPDATE:
            if element_id in document:
                if info:
                    document[element_id] <= info
                else:
                    document[element_id].remove()
        document.title = document.title.replace("{ station_name }", self.station.name)

    async def run_once(self):
        print("run onces")
        await self.setup()
        await self.request_station_data()

    def start(self):
        if self.is_monitor:
            self.running = True
            aio.run(self.monitor())
        else:
            aio.run(self.run_once())
