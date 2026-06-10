import math

from sindhu import models


def _haversine(lat1, lon1, lat2, lon2):
    R = 6_371_000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    )
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


async def find_zone_by_location(longitude: float, latitude: float):
    point = {
        "type": "Point",
        "coordinates": [longitude, latitude],
    }
    zone = await models.Zone.find_one(
        {
            "boundary": {"$geoIntersects": {"$geometry": point}},
            "status": "active",
        }
    )
    return zone


async def find_stations_by_zone(zone, user_lng: float = 0, user_lat: float = 0) -> list:
    if not zone:
        return []

    zone_with_links = await models.Zone.find_one(
        models.Zone.id == zone.id, fetch_links=True
    )
    if not zone_with_links:
        return []

    stations = [s for s in zone_with_links.stations if s.status == "active"]

    result = []
    for s in stations:
        d = s.model_dump(mode="json")
        coords = s.coordinates.coordinates if s.coordinates else [0, 0]
        d["distance"] = _haversine(user_lat, user_lng, coords[1], coords[0])
        result.append(d)

    result.sort(key=lambda x: x["distance"])
    return result
