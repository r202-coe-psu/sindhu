"""Zone role rule shared by the map and monitors.

Matches sindhu.services.zones.is_reference_zone so a zone /locate returns is
always one the map draws.
"""


def is_reference_zone(zone, style=None):
    if zone.get("zone_kind") == "reference":
        return True
    return any(
        (d or {}).get("role") == "reference_boundary"
        for d in (style, zone.get("metadata"), zone.get("style"))
    )
