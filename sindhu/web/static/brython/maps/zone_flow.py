"""Where an upstream zone's water enters the selected zone.

Pure geometry on GeoJSON coordinates ([lng, lat]); nothing here touches the
browser, so it runs under CPython tests as well as in Brython.
"""

import math

# Zone outlines are traced independently, so a shared border is two lines a
# few metres apart rather than one line.  About 220 m at Hat Yai's latitude.
BORDER_TOLERANCE_DEG = 0.002


def zone_rings(boundary):
    """Outer rings of a Polygon, MultiPolygon, Feature or FeatureCollection."""
    if not boundary:
        return []
    kind = boundary.get("type")
    if kind == "FeatureCollection":
        return [
            ring
            for feature in boundary.get("features") or []
            for ring in zone_rings(feature)
        ]
    if kind == "Feature":
        return zone_rings(boundary.get("geometry"))
    coordinates = boundary.get("coordinates") or []
    if kind == "Polygon":
        return [coordinates[0]] if coordinates else []
    if kind == "MultiPolygon":
        return [polygon[0] for polygon in coordinates if polygon]
    return []


def _signed_area_and_centroid(ring):
    area = cx = cy = 0.0
    for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
        cross = x1 * y2 - x2 * y1
        area += cross
        cx += (x1 + x2) * cross
        cy += (y1 + y2) * cross
    area /= 2
    if area == 0:
        xs = [point[0] for point in ring]
        ys = [point[1] for point in ring]
        return 0.0, (sum(xs) / len(xs), sum(ys) / len(ys))
    return area, (cx / (6 * area), cy / (6 * area))


def _open(ring):
    ring = [(point[0], point[1]) for point in ring]
    return ring[:-1] if len(ring) > 1 and ring[0] == ring[-1] else ring


def ring_centroid(ring):
    """Area-weighted centroid (lng, lat) of one ring."""
    return _signed_area_and_centroid(_open(ring))[1]


def rings_centroid(rings):
    weighted = []
    for ring in rings:
        area, centroid = _signed_area_and_centroid(_open(ring))
        weighted.append((abs(area), centroid))
    total = sum(area for area, _ in weighted)
    if total == 0:
        return weighted[0][1]
    return (
        sum(area * centroid[0] for area, centroid in weighted) / total,
        sum(area * centroid[1] for area, centroid in weighted) / total,
    )


def _distance_to_segment(point, start, end):
    px, py = point
    sx, sy = start
    dx, dy = end[0] - sx, end[1] - sy
    length_sq = dx * dx + dy * dy
    t = 0.0 if length_sq == 0 else ((px - sx) * dx + (py - sy) * dy) / length_sq
    t = max(0.0, min(1.0, t))
    return math.hypot(px - (sx + t * dx), py - (sy + t * dy))


def _near_any_edge(point, rings, tolerance):
    for ring in rings:
        for start, end in zip(ring, ring[1:] + ring[:1]):
            if _distance_to_segment(point, start, end) <= tolerance:
                return True
    return False


def _shared_runs(ring, other_rings, tolerance):
    """Runs of consecutive vertices of ``ring`` that lie on ``other_rings``."""
    near = [_near_any_edge(point, other_rings, tolerance) for point in ring]
    if not any(near):
        return []
    if all(near):
        return [ring + ring[:1]]
    # Start just after a vertex that is off the border so no run wraps.
    first_off = near.index(False)
    order = [(first_off + 1 + i) % len(ring) for i in range(len(ring))]
    runs, run = [], []
    for index in order:
        if near[index]:
            run.append(ring[index])
        elif run:
            runs.append(run)
            run = []
    if run:
        runs.append(run)
    return runs


def _run_length(run):
    return sum(math.dist(a, b) for a, b in zip(run, run[1:]))


def _middle_of_run(run):
    half = _run_length(run) / 2
    for start, end in zip(run, run[1:]):
        step = math.dist(start, end)
        if step >= half and step > 0:
            t = half / step
            return (
                start[0] + t * (end[0] - start[0]),
                start[1] + t * (end[1] - start[1]),
            )
        half -= step
    return run[0]


def _lng_scale(rings):
    lats = [point[1] for ring in rings for point in ring]
    return math.cos(math.radians(sum(lats) / len(lats)))


def shared_border_anchor(rings_a, rings_b, tolerance):
    """Middle of the longest border the two zones share, or None.

    A border is a run of vertices of one outline lying within ``tolerance``
    degrees of the other outline.
    """
    if not rings_a or not rings_b:
        return None
    scale = _lng_scale(rings_a + rings_b)

    def flat(rings):
        return [[(x * scale, y) for x, y in _open(ring)] for ring in rings]

    flat_a, flat_b = flat(rings_a), flat(rings_b)
    best = None
    for ring_set, other in ((flat_a, flat_b), (flat_b, flat_a)):
        for ring in ring_set:
            for run in _shared_runs(ring, other, tolerance):
                length = _run_length(run)
                if best is None or length > best[0]:
                    best = (length, run)
    if best is None:
        return None
    x, y = _middle_of_run(best[1])
    return (x / scale, y)


def upstream_arrow(upstream_rings, selected_rings, tolerance=BORDER_TOLERANCE_DEG):
    """Arrow entering the selected zone: {"lng", "lat", "angle"}.

    ``angle`` is degrees clockwise from north, from the upstream centroid
    towards the selected centroid.  The arrow sits on their shared border, or
    halfway between the centroids when the zones do not touch.
    """
    from_lng, from_lat = rings_centroid(upstream_rings)
    to_lng, to_lat = rings_centroid(selected_rings)
    east = (to_lng - from_lng) * math.cos(math.radians((from_lat + to_lat) / 2))
    north = to_lat - from_lat
    angle = math.degrees(math.atan2(east, north)) % 360
    anchor = shared_border_anchor(upstream_rings, selected_rings, tolerance)
    if anchor is None:
        anchor = ((from_lng + to_lng) / 2, (from_lat + to_lat) / 2)
    return {"lng": anchor[0], "lat": anchor[1], "angle": angle}
