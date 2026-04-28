import datetime

from . import sensor_colors
from . import sensor_infos
from . import hotspot_colors
from . import hotspot_infos
from . import fire_report_infos


class Sensor:
    def __init__(self, id=None, type="unknow", value=0, unit="unit"):
        self.id = id
        self.value = value
        self.type = type
        self.last_update = None
        self.data = dict(hourly=[], daily=[])
        self.unit = unit

    async def update(self, every, data):
        self.data[every] = [
            [d["timestamp"], d["value"], d["date_week"]] for d in data["climates"]
        ]


class Station:
    def __init__(self):
        self.name = ""
        self.source = ""
        self.sensors = dict()
        self.location = ""
        self.coordinate = [0, 0]
        self.device_id = ""
        self.status = False
        self.last_update = None
        self.model = ""
        self.operator = ""
        self.contributor = ""
        self.contributor_url = ""
        self.logo_url = ""
        self.id = ""

    async def update(self, data):
        self.id = data.get("id", self.id)
        self.source = data.get("source", self.source)
        self.coordinate = data.get("coordinate", self.coordinate)
        self.location = data.get("location", self.location)
        self.station = data.get("station", self.location)
        self.device_id = data.get("device_id", self.device_id)
        self.name = data.get("name", self.name)
        self.model = data.get("model", self.model)
        self.operator = data.get("operator", self.operator)
        self.contributor = data.get("contributor", self.contributor)
        self.contributor_url = data.get("contributor_url", self.contributor_url)
        self.logo_url = data.get("logo_url", self.logo_url)

        last_update = data.get("last_update", self.last_update)

        device_status = data.get("device_status", {})
        if device_status:
            self.status = device_status.get("status", self.status)
            last_update = device_status.get("last_update", last_update)

        if type(last_update) == datetime.datetime:
            self.last_update = last_update
        elif last_update and type(last_update) == str and last_update != "Unknow":
            self.last_update = datetime.datetime.fromisoformat(last_update)

        sensors = data.get("sensors", {})
        for type_, value in sensors.items():
            type_ = type_.lower()
            sensor = self.sensors.get(type_, Sensor(type=type_, value=value))
            if type_ not in self.sensors:
                self.sensors[type_] = sensor

    async def update_sensors(self, sensors):
        for sensor in sensors:
            key = sensor.get("name", sensor.get("type")).lower()
            if key not in self.sensors:
                self.sensors[key] = Sensor(type=key, value=sensor.get("value"))
            self.sensors[key].value = sensor["value"]


class ClimateFormula:
    def __init__(self):
        self.name = ""
        self.source = ""
        self.sensors = dict()
        self.location = ""
        self.coordinate = [0, 0]
        self.device_id = ""
        self.status = False
        self.last_update = None
        self.model = ""
        self.operator = ""
        self.contributor = ""
        self.contributor_url = ""
        self.logo_url = ""
        self.id = ""

    async def update(self, data):
        self.id = data.get("id", self.id)
        self.source = data.get("source", self.source)
        self.coordinate = data.get("coordinate", self.coordinate)
        self.location = data.get("location", self.location)
        self.station = data.get("station", self.location)
        self.device_id = data.get("device_id", self.device_id)
        self.name = data.get("name", self.name)
        self.model = data.get("model", self.model)
        self.operator = data.get("operator", self.operator)
        self.contributor = data.get("contributor", self.contributor)
        self.contributor_url = data.get("contributor_url", self.contributor_url)
        self.logo_url = data.get("logo_url", self.logo_url)

        last_update = data.get("last_update", self.last_update)

        device_status = data.get("device_status", {})
        if device_status:
            self.status = device_status.get("status", self.status)
            last_update = device_status.get("last_update", last_update)

        if type(last_update) == datetime.datetime:
            self.last_update = last_update
        elif last_update and type(last_update) == str and last_update != "Unknow":
            self.last_update = datetime.datetime.fromisoformat(last_update)

        sensors = data.get("sensors", {})
        for type_, value in sensors.items():
            type_ = type_.lower()
            sensor = self.sensors.get(type_, Sensor(type=type_, value=value))
            if type_ not in self.sensors:
                self.sensors[type_] = sensor

    async def update_sensors(self, sensors):
        # print("---", sensors)

        for sensor in sensors:
            key = sensor.get("name", sensor.get("type")).lower()
            if key not in self.sensors:
                self.sensors[key] = Sensor(type=key, value=sensor.get("value"))
            self.sensors[key].value = sensor["value"]
