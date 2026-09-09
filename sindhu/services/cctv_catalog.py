"""Static, source-owned CCTV identity catalogs.

The Hatyai entries are a checked-in extraction of the 28 CCTV entries from
the former Mage registry.  This module intentionally has no dependency on
Mage (or on its checkout) so request-time API code remains independently
deployable.

Catalog dictionaries are treated as immutable by convention.  ``get_camera``
returns a defensive copy so a provider normalizer cannot mutate the registry
shared by another request.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

HATYAI_SOURCE = "hatyai_city_climate"
DWR_SOURCE = "dwr"

HATYAI_REGISTRY_VERSION = "2026-09-05.v1"
DWR_REGISTRY_VERSION = "2026-09-03.v1"

HATYAI_SOURCE_URL = "https://hatyaicityclimate.org/flood/map/camera"
DWR_SOURCE_URL = "https://telemetry.dwr.go.th/api"

# Only the CCTV subset of the Mage registry is public in this release.  The
# radar, satellite, and weather-map entries are deliberately not copied here.
HATYAI_CAMERAS: tuple[dict[str, Any], ...] = (
    {
        "upstream_id": 9,
        "slug": "muangkong",
        "title_th": "สะพานม่วงก็อง",
        "code": "S1",
        "coverage_group": "hatyai_city",
    },
    {
        "upstream_id": 3,
        "slug": "bangsala",
        "title_th": "สะพานบางศาลา",
        "code": "S2",
        "coverage_group": "hatyai_city",
    },
    {
        "upstream_id": 44,
        "slug": "klongwha2",
        "title_th": "สะพานประชาอุทิศ(คลองหวะ)",
        "code": "S7",
        "coverage_group": "hatyai_city",
    },
    {
        "upstream_id": 1,
        "slug": "hatyainai",
        "title_th": "สะพานข้างที่ว่าการ อ.หาดใหญ่",
        "code": "S8",
        "coverage_group": "hatyai_city",
    },
    {
        "upstream_id": 29,
        "slug": "klongwha",
        "title_th": "สี่แยกคลองหวะ",
        "code": "S6",
        "coverage_group": "hatyai_city",
    },
    {
        "upstream_id": 22,
        "slug": "road30m",
        "title_th": "ถนนราษฎร์ยินดี (เหล็กใต้ 30 เมตร)",
        "code": "S9",
        "coverage_group": "hatyai_city",
    },
    {
        "upstream_id": 68,
        "slug": "kalyanamit",
        "title_th": "อุโมงค์กัลยาณมิตร",
        "code": "S13",
        "coverage_group": "hatyai_city",
    },
    {
        "upstream_id": 48,
        "slug": "khuankhirat",
        "title_th": "ควนขี้แรด ต.พะตง",
        "code": "S3",
        "coverage_group": "patong",
    },
    {
        "upstream_id": 40,
        "slug": "patongkn",
        "title_th": "ท้ายวัดควนเนียง ต.พะตง",
        "code": "S4",
        "coverage_group": "patong",
    },
    {
        "upstream_id": 46,
        "slug": "tunglung",
        "title_th": "ป้อม ตร.ตลาดทุ่งลุง",
        "code": "S5",
        "coverage_group": "patong",
    },
    {
        "upstream_id": 60,
        "slug": "klongetum",
        "title_th": "คลองอิตำ ต.ทุ่งตำเสา",
        "code": "S10",
        "coverage_group": "khuan_lang",
    },
    {
        "upstream_id": 61,
        "slug": "klongnon",
        "title_th": "คลองนนท์ ต.ควนลัง",
        "code": "S11",
        "coverage_group": "khuan_lang",
    },
    {
        "upstream_id": 66,
        "slug": "utapao",
        "title_th": "ประตูระบายน้ำ คลองอู่ตะเภา",
        "code": "I1",
        "coverage_group": "r1_drainage",
    },
    {
        "upstream_id": 62,
        "slug": "nhakaun",
        "title_th": "ประตูระบายน้ำ คลอง ร.1",
        "code": "I2",
        "coverage_group": "r1_drainage",
    },
    {
        "upstream_id": 63,
        "slug": "khlongs1r1",
        "title_th": "ประตูระบายน้ำคลองชลประทาน",
        "code": "I3",
        "coverage_group": "r1_drainage",
    },
    {
        "upstream_id": 64,
        "slug": "bangyheeus",
        "title_th": "ประตูระบายน้ำบ้านบางหยี(หน้า)",
        "code": "I4",
        "coverage_group": "r1_drainage",
    },
    {
        "upstream_id": 65,
        "slug": "bangyheeds",
        "title_th": "ประตูระบายน้ำบ้านบางหยี(หลัง)",
        "code": "I5",
        "coverage_group": "r1_drainage",
    },
    {
        "upstream_id": 56,
        "slug": "khgamling",
        "title_th": "อ่างเก็บน้ำแก้มลิงคลองเรียน",
        "code": "K01",
        "coverage_group": "kho_hong",
    },
    {
        "upstream_id": 52,
        "slug": "khklongr6",
        "title_th": "ต้นคลองเรียน-คลอง ร.6",
        "code": "K02",
        "coverage_group": "kho_hong",
    },
    {
        "upstream_id": 58,
        "slug": "khsoi1plugtong",
        "title_th": "ถนนปลักธง(ป้อม อปพร.)",
        "code": "K03",
        "coverage_group": "kho_hong",
    },
    {
        "upstream_id": 51,
        "slug": "khtaisoi",
        "title_th": "ท้ายซอยถนนปลักธง",
        "code": "K04",
        "coverage_group": "kho_hong",
    },
    {
        "upstream_id": 50,
        "slug": "khnailhong",
        "title_th": "ปากซอยนายหลง ปลักธง 1",
        "code": "K05",
        "coverage_group": "kho_hong",
    },
    {
        "upstream_id": 49,
        "slug": "khtwinburana",
        "title_th": "สะพานซอยถวิลบูรณะ",
        "code": "K06",
        "coverage_group": "kho_hong",
    },
    {
        "upstream_id": 53,
        "slug": "khpholpichaihu",
        "title_th": "ถนนพลพิชัย (หน้า ม.หาดใหญ่)",
        "code": "K07",
        "coverage_group": "kho_hong",
    },
    {
        "upstream_id": 57,
        "slug": "khkarnjanavanij6",
        "title_th": "ริมคลอง ร.5 ท้ายซอยกาญจนวนิช 6",
        "code": "K08",
        "coverage_group": "kho_hong",
    },
    {
        "upstream_id": 55,
        "slug": "khparinyavillage",
        "title_th": "ริมคลอง ร.5 ท้ายซอย ม.ปริญญา",
        "code": "K09",
        "coverage_group": "kho_hong",
    },
    {
        "upstream_id": 54,
        "slug": "khpookong",
        "title_th": "ถนนอนุสรณ์ปู่คง",
        "code": "K10",
        "coverage_group": "kho_hong",
    },
    {
        "upstream_id": 69,
        "slug": "kuanhin",
        "title_th": "บ้านควนหิน ต.พะวง",
        "code": "S14",
        "coverage_group": "pawong",
    },
)

DWR_CAMERAS: tuple[dict[str, Any], ...] = (
    {
        "upstream_id": "0e976e02-8381-4f6e-988a-81ecbed96fb9",
        "slug": "ta200303",
        "title_th": "คลองอู่ตะเภาตอนบนทุ่งลาน",
        "code": "TA200303",
        "coverage_group": "dwr_songkhla",
        "station_code": "TA200303",
        "coordinate_status": "verified",
        "coordinates": {
            "type": "Point",
            "coordinates": [100.464160, 6.856463],
        },
        "coordinate_provenance": {
            "source": "กรมทรัพยากรน้ำ public station API",
            "method": "GET /public/station/getByCode/TA200303",
            "effective_date": "2026-09-03",
            "registry_version": DWR_REGISTRY_VERSION,
            "evidence_url": (
                "https://telemetry.dwr.go.th/api/public/station/getByCode/TA200303"
            ),
        },
    },
    {
        "upstream_id": "3e55f300-3d80-4520-acfa-7a12c2a6bef9",
        "slug": "ta200304",
        "title_th": "คลองอู่ตะเภาตอนล่าง",
        "code": "TA200304",
        "coverage_group": "dwr_songkhla",
        "station_code": "TA200304",
        "coordinate_status": "verified",
        "coordinates": {
            "type": "Point",
            "coordinates": [100.455870, 7.002080],
        },
        "coordinate_provenance": {
            "source": "กรมทรัพยากรน้ำ public station API",
            "method": "GET /public/station/getByCode/TA200304",
            "effective_date": "2026-09-03",
            "registry_version": DWR_REGISTRY_VERSION,
            "evidence_url": (
                "https://telemetry.dwr.go.th/api/public/station/getByCode/TA200304"
            ),
        },
    },
)


# Provider location values checked 2026-09-05 against BOTH cameraId and name.
# Input order is latitude, longitude; public GeoJSON reverses that order.
# These are provider-reported installation locations, not a field survey.
_HATYAI_LOCATIONS = {
    9: (6.823193, 100.438272),
    3: (6.93120684682416, 100.439536371),
    44: (6.987275433526357, 100.47408516),
    1: (7.002231, 100.455775),
    29: (6.975332998927496, 100.47989941),
    22: (7.006897940000433, 100.48097271),
    48: (6.824277345889672, 100.54223098),
    40: (6.834999485452772, 100.49879698),
    46: (6.855114054447877, 100.47061833),
    60: (6.975383398004944, 100.36786114),
    61: (6.983757367079641, 100.41982460),
    66: (6.9882408, 100.4618168),
    62: (6.9859383, 100.4589649),
    63: (7.0085673, 100.4421200),
    64: (7.127922, 100.4334709),
    65: (7.1278599, 100.43395),
    56: (6.995112480951006, 100.51211168),
    52: (6.9948285943955355, 100.5011883),
    58: (6.9861621369579545, 100.4945347),
    51: (6.9825450547602825, 100.4980963),
    50: (6.973452578226034, 100.50200556),
    49: (6.972897379412532, 100.49685804),
    53: (6.9816198448781694, 100.4699220),
    57: (7.032156236567186, 100.49066170),
    55: (7.0419274234013995, 100.4933684),
    54: (7.044717341840631, 100.50049802),
    69: (7.100897, 100.567690),
}

for _camera in HATYAI_CAMERAS:
    _location = _HATYAI_LOCATIONS.get(_camera["upstream_id"])
    if _location is None:
        # ID 68 kalyanamit: provider location was an empty string.
        continue
    _latitude, _longitude = _location
    _camera.update(
        {
            "coordinate_status": "verified",
            "coordinates": {"type": "Point", "coordinates": [_longitude, _latitude]},
            "coordinate_provenance": {
                "source": "Hatyai City Climate camera detail API",
                "method": f"GET /api/flood/cam?id={_camera['upstream_id']}; matched cameraId/name; location=latitude,longitude; provider-reported, not field-surveyed",
                "effective_date": "2026-09-05",
                "registry_version": HATYAI_REGISTRY_VERSION,
                "evidence_url": "https://hatyaicityclimate.org/api/flood/cam",
                "reference_url": f"https://hatyaicityclimate.org/flood/cam/{_camera['slug']}",
            },
        }
    )


def _normalise_id(value: Any) -> str:
    return str(value).strip().lower()


_CAMERAS_BY_SOURCE: dict[str, tuple[dict[str, Any], ...]] = {
    HATYAI_SOURCE: HATYAI_CAMERAS,
    DWR_SOURCE: DWR_CAMERAS,
}


def get_camera(source: str, upstream_id: Any) -> dict[str, Any] | None:
    """Return a defensive copy of one registered camera, or ``None``."""

    wanted = _normalise_id(upstream_id)
    for camera in _CAMERAS_BY_SOURCE.get(str(source).strip(), ()):
        if _normalise_id(camera["upstream_id"]) == wanted:
            return deepcopy(camera)
    return None


__all__ = [
    "DWR_CAMERAS",
    "DWR_REGISTRY_VERSION",
    "DWR_SOURCE",
    "DWR_SOURCE_URL",
    "HATYAI_CAMERAS",
    "HATYAI_REGISTRY_VERSION",
    "HATYAI_SOURCE",
    "HATYAI_SOURCE_URL",
    "get_camera",
]
