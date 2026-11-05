import math

from beanie import PydanticObjectId
from pydantic import BaseModel, Field

from sindhu import models

_FLOOD_KIND = {"$or": [{"zone_kind": "flood"}, {"zone_kind": {"$exists": False}}]}


class _UpstreamEdges(BaseModel):
    id: PydanticObjectId = Field(alias="_id")
    upstream_zone_ids: list[PydanticObjectId] = Field(default_factory=list)


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
            # Reference boundaries are map context only. They must never win
            # point location or be treated as a flood-monitoring zone.
            "$or": [
                {"zone_kind": "flood"},
                {"zone_kind": {"$exists": False}},
            ],
        }
    )
    return zone


async def find_stations_by_zone(zone, user_lng: float = 0, user_lat: float = 0) -> list:
    if not zone or getattr(zone, "zone_kind", "flood") == "reference":
        return []

    zone_with_links = await models.Zone.find_one(
        models.Zone.id == zone.id, fetch_links=True
    )
    if not zone_with_links:
        return []

    stations = [
        s for s in zone_with_links.stations if s.status == "active" and s.is_visible
    ]

    result = []
    for s in stations:
        d = s.model_dump(mode="json")
        coords = s.coordinates.coordinates if s.coordinates else [0, 0]
        d["distance"] = _haversine(user_lat, user_lng, coords[1], coords[0])
        result.append(d)

    result.sort(key=lambda x: x["distance"])
    return result


def upstream_violation(
    zone_id: str | None,
    upstream_ids: list[str],
    graph: dict[str, list[str]],
) -> str | None:
    """Thai error for an upstream list a zone may not take, or None if valid.

    `graph` maps each existing flood zone id to its stored upstream ids.
    `zone_id` is None when the zone is being created, which cannot form a
    cycle because nothing yet points at it.
    """
    if zone_id is not None and zone_id in upstream_ids:
        return "โซนไม่สามารถเป็นต้นน้ำของตัวเองได้"

    if any(upstream_id not in graph for upstream_id in upstream_ids):
        return "ไม่พบโซนต้นน้ำที่ระบุ หรือโซนนั้นถูกลบ/ไม่ใช่โซนน้ำท่วม"

    if zone_id is None:
        return None

    # Whole graph, not one level: the map shows one level but A -> B -> C -> A
    # is just as invalid. The zone's own stored edges never matter because the
    # walk stops the moment it reaches the zone.
    seen: set[str] = set()
    stack = list(upstream_ids)
    while stack:
        current = stack.pop()
        if current == zone_id:
            return "ไม่สามารถกำหนดต้นน้ำนี้ได้ เพราะทำให้เกิดวงวนระหว่างโซน"
        if current in seen:
            continue
        seen.add(current)
        stack.extend(graph.get(current, []))
    return None


async def check_upstream(zone_id: str | None, upstream_ids: list[str]) -> str | None:
    docs = (
        await models.Zone.find({"status": {"$ne": "delete"}, **_FLOOD_KIND})
        .project(_UpstreamEdges)
        .to_list()
    )
    graph = {str(d.id): [str(u) for u in d.upstream_zone_ids] for d in docs}
    return upstream_violation(zone_id, upstream_ids, graph)
