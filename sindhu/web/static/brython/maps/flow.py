"""Drainage corridors through Hat Yai: coloured lines, direction arrows and
"water comes from" labels that pin to the screen edge when their source is
off screen.

The geometry helpers are pure functions on screen pixels (x right, y down) so
they run under CPython in tests; only ``FlowLayer`` touches Leaflet.
"""

import math

from browser import html, window

CORRIDORS = {
    "utapao": {"name": "คลองอู่ตะเภา", "color": "#1d4ed8"},
    "khuanlang": {"name": "คลองวาด → คลอง ร.1", "color": "#be123c"},
    "khohong": {"name": "คลองเรียน / คลอง ร.3-ร.6 → คลองเตย", "color": "#15803d"},
}

# route: where the water heads.  angle: degrees clockwise from north of the
# big arrow drawn beside the label while the source is on screen.
FLOW_SOURCES = [
    {
        "id": "sadao",
        "title": "น้ำจากสะเดา",
        "route": "ทะเลสาบสงขลา",
        "lat": 6.84,
        "lng": 100.4706,
        "dest_lat": 7.15,
        "dest_lng": 100.465,
        "angle": 0,
        "color": CORRIDORS["utapao"]["color"],
    },
    {
        "id": "khuanlang",
        "title": "น้ำจากควนลัง",
        "route": "คลอง ร.1 → ทะเลสาบ",
        "lat": 6.985,
        "lng": 100.395,
        "dest_lat": 7.15,
        "dest_lng": 100.465,
        "angle": 65,
        "color": CORRIDORS["khuanlang"]["color"],
    },
    {
        "id": "khohong",
        "title": "น้ำจากคอหงส์",
        "route": "คลองเตย → ทะเลสาบ",
        "lat": 6.985,
        "lng": 100.525,
        "dest_lat": 7.15,
        "dest_lng": 100.465,
        "angle": 295,
        "color": CORRIDORS["khohong"]["color"],
    },
    {
        "id": "lake",
        "title": "น้ำออกทะเลสาบ",
        "route": "ทะเลสาบสงขลา",
        "lat": 7.135,
        "lng": 100.465,
        "dest_lat": 7.25,
        "dest_lng": 100.465,
        "angle": 0,
        "color": "#0c4a6e",
    },
]

# The waterway lines are OpenStreetMap data (ODbL), which requires this credit.
OSM_ATTRIBUTION = (
    '&copy; <a href="https://www.openstreetmap.org/copyright">'
    "OpenStreetMap</a> contributors"
)
ARROW_SPACING_PX = 100
ARROW_SIZE_PX = 18
LINE_WEIGHT_PX = 4
LABEL_FLY_MIN_ZOOM = 13
# Between overlayPane (400) and markerPane (600): above the zone fills and
# below the station markers.
LINES_PANE = ("flowLines", "420")
CONTEXT_PANE = ("flowContext", "410")
# The rest of the waterway network: thin and faint so the corridors stay the
# story, and only from city zoom, where it no longer clutters the map.
CONTEXT_MIN_ZOOM = 12
CONTEXT_COLOR = "#0369a1"
CONTEXT_WEIGHT_PX = {"river": 2.0, "canal": 1.5, "stream": 1.0, "drain": 1.0}
ARROWS_PANE = ("flowArrows", "425")
FALLBACK_LABEL_SIZE = (180, 56)
LABEL_EDGE_GAP_PX = 8
# (left, top, right, bottom) px of the map that pinned labels keep clear: the
# brand, locate and panel cards across the top and the zoom controls down the right.
PIN_INSETS = (0, 112, 56, 0)

# The on-screen arrow sits upstream of its label and points at it.
SOURCE_ARROW_SIZE_PX = (28, 96)
SOURCE_ARROW_GAP_PX = 18
SOURCE_ARROW_SVG = (
    '<svg viewBox="-14 -48 28 96" width="28" height="96" style="fill:{color}">'
    '<path d="M0 -46 L13 -22 L4 -22 L4 46 L-4 46 L-4 -22 L-13 -22 Z"/></svg>'
)

ARROW_SVG = (
    '<svg viewBox="-8 -8 16 16" width="{size}" height="{size}" '
    'style="fill:{color};transform:rotate({angle}deg)">'
    '<path d="M0 -7 L6 6 L0 3 L-6 6 Z"/></svg>'
)


def screen_bearing(x1, y1, x2, y2):
    """Degrees clockwise from north of the vector (x1, y1) -> (x2, y2)."""
    return math.degrees(math.atan2(x2 - x1, y1 - y2)) % 360


def arrow_marks(points, spacing):
    """Return (x, y, angle) marks every ``spacing`` px along a pixel path.

    The first mark sits half a spacing in, so consecutive ways of one
    corridor never put two arrows closer than ``spacing`` at their join.
    """
    marks = []
    next_at = spacing / 2
    travelled = 0.0
    for (x1, y1), (x2, y2) in zip(points, points[1:]):
        length = math.hypot(x2 - x1, y2 - y1)
        if length == 0:
            continue
        angle = screen_bearing(x1, y1, x2, y2)
        while next_at <= travelled + length:
            t = (next_at - travelled) / length
            marks.append((x1 + (x2 - x1) * t, y1 + (y2 - y1) * t, angle))
            next_at += spacing
        travelled += length
    return marks


def pin_to_edge(x, y, width, height, margin):
    """Clamp a point into the margin box; name the edge it was pushed to.

    A point past two edges takes the one it overshoots most.
    """
    overshoot = {
        "top": margin - y,
        "bottom": y - (height - margin),
        "left": margin - x,
        "right": x - (width - margin),
    }
    edge, amount = max(overshoot.items(), key=lambda item: item[1])
    clamped_x = min(max(x, margin), width - margin)
    clamped_y = min(max(y, margin), height - margin)
    return clamped_x, clamped_y, edge if amount > 0 else None


def upstream_offset(angle, distance):
    """(dx, dy) on screen from a label to the point ``distance`` px behind it
    along a flow heading ``angle`` (clockwise from north)."""
    radians = math.radians(angle)
    return -math.sin(radians) * distance, math.cos(radians) * distance


def box_reach(width, height, angle):
    """Distance from a box's centre to its edge along heading ``angle``."""
    dx, dy = upstream_offset(angle, 1)
    reaches = []
    if abs(dx) > 1e-9:
        reaches.append(width / 2 / abs(dx))
    if abs(dy) > 1e-9:
        reaches.append(height / 2 / abs(dy))
    return min(reaches)


def spread_along_edge(centres, sizes, low, high):
    """Slide labels along an edge so none overlaps its neighbour.

    ``centres`` and ``sizes`` are along one axis, ``low``..``high`` the room
    available. Order is kept; when everything cannot fit, the overflow goes
    past ``low`` rather than reordering.
    """
    order = sorted(range(len(centres)), key=lambda i: centres[i])
    spread = list(centres)
    edge = low
    for i in order:
        spread[i] = max(spread[i], edge + sizes[i] / 2)
        edge = spread[i] + sizes[i] / 2
    edge = high
    for i in reversed(order):
        spread[i] = min(spread[i], edge - sizes[i] / 2)
        edge = spread[i] - sizes[i] / 2
    return spread


class FlowLayer:
    def __init__(self, leaflet_map):
        self.map = leaflet_map
        self.leaflet = window.L
        self.features = []
        self.line_layers = []
        self.labels = []
        self._marks_by_zoom = None

        self._create_pane(*CONTEXT_PANE)
        self._create_pane(*LINES_PANE)
        self._create_pane(*ARROWS_PANE)
        self.line_renderer = self.leaflet.svg({"pane": LINES_PANE[0]})
        self.context_renderer = self.leaflet.svg({"pane": CONTEXT_PANE[0]})
        self.context_layer = self.leaflet.layerGroup()
        self.arrow_layer = self.leaflet.layerGroup().addTo(self.map)

        if self.map.attributionControl:
            self.map.attributionControl.addAttribution(OSM_ATTRIBUTION)

        self._create_labels()
        self.map.on("zoomend moveend", lambda e: self.refresh_arrows())
        self.map.on("zoomend", lambda e: self.refresh_context())
        self.map.on("move zoom resize", lambda e: self.place_labels())
        self.place_labels()

    def _create_pane(self, name, z_index):
        pane = self.map.getPane(name) or self.map.createPane(name)
        pane.style.zIndex = z_index
        pane.style.pointerEvents = "none"

    def set_corridors(self, geojson):
        for layer in self.line_layers:
            self.map.removeLayer(layer)
        self.line_layers = []
        self.features = []
        self._marks_by_zoom = None

        by_corridor = {}
        for feature in geojson.get("features", []):
            corridor = (feature.get("properties") or {}).get("corridor")
            coordinates = (feature.get("geometry") or {}).get("coordinates") or []
            if corridor not in CORRIDORS or len(coordinates) < 2:
                continue
            latlngs = [[lat, lng] for lng, lat in coordinates]
            self.features.append((corridor, latlngs))
            by_corridor.setdefault(corridor, []).append(latlngs)

        for corridor, parts in by_corridor.items():
            layer = self.leaflet.polyline(
                parts,
                {
                    "pane": LINES_PANE[0],
                    "renderer": self.line_renderer,
                    "interactive": False,
                    "color": CORRIDORS[corridor]["color"],
                    "weight": LINE_WEIGHT_PX,
                    "opacity": 0.9,
                    "lineCap": "round",
                    "lineJoin": "round",
                },
            )
            layer.addTo(self.map)
            self.line_layers.append(layer)
        self.refresh_arrows()

    def set_context(self, geojson):
        self.context_layer.clearLayers()
        by_class = {}
        for feature in geojson.get("features", []):
            coordinates = (feature.get("geometry") or {}).get("coordinates") or []
            if len(coordinates) < 2:
                continue
            fclass = (feature.get("properties") or {}).get("fclass")
            by_class.setdefault(fclass, []).append(
                [[lat, lng] for lng, lat in coordinates]
            )
        for fclass, parts in by_class.items():
            self.context_layer.addLayer(
                self.leaflet.polyline(
                    parts,
                    {
                        "pane": CONTEXT_PANE[0],
                        "renderer": self.context_renderer,
                        "interactive": False,
                        "color": CONTEXT_COLOR,
                        "weight": CONTEXT_WEIGHT_PX.get(fclass, 1.0),
                        "opacity": 0.6,
                        "lineCap": "round",
                        "lineJoin": "round",
                    },
                )
            )
        self.refresh_context()

    def refresh_context(self):
        show = self.map.getZoom() >= CONTEXT_MIN_ZOOM
        if show and not self.map.hasLayer(self.context_layer):
            self.context_layer.addTo(self.map)
        elif not show and self.map.hasLayer(self.context_layer):
            self.map.removeLayer(self.context_layer)

    def _marks_at(self, zoom):
        """Arrow marks of every line at ``zoom``, in world pixels.

        Cached per zoom: panning only moves the view over the same marks, and
        projecting every vertex is the costly part.
        """
        if self._marks_by_zoom and self._marks_by_zoom[0] == zoom:
            return self._marks_by_zoom[1]
        lines = []
        for corridor, latlngs in self.features:
            points = []
            for latlng in latlngs:
                point = self.map.project(latlng, zoom)
                points.append((point.x, point.y))
            xs = [x for x, _ in points]
            ys = [y for _, y in points]
            bounds = (min(xs), min(ys), max(xs), max(ys))
            lines.append((corridor, bounds, arrow_marks(points, ARROW_SPACING_PX)))
        self._marks_by_zoom = (zoom, lines)
        return lines

    def refresh_arrows(self):
        self.arrow_layer.clearLayers()
        zoom = self.map.getZoom()
        view = self.map.getPixelBounds()
        pad = ARROW_SIZE_PX
        left, top = view.min.x - pad, view.min.y - pad
        right, bottom = view.max.x + pad, view.max.y + pad

        for corridor, (min_x, min_y, max_x, max_y), marks in self._marks_at(zoom):
            if max_x < left or min_x > right or max_y < top or min_y > bottom:
                continue
            color = CORRIDORS[corridor]["color"]
            for x, y, angle in marks:
                if left <= x <= right and top <= y <= bottom:
                    self.arrow_layer.addLayer(
                        self._arrow_marker(x, y, angle, color, zoom)
                    )

    def _arrow_marker(self, x, y, angle, color, zoom):
        icon = self.leaflet.divIcon(
            {
                "className": "flow-arrow",
                "html": ARROW_SVG.format(
                    size=ARROW_SIZE_PX, color=color, angle=round(angle, 1)
                ),
                "iconSize": [ARROW_SIZE_PX, ARROW_SIZE_PX],
                "iconAnchor": [ARROW_SIZE_PX / 2, ARROW_SIZE_PX / 2],
            }
        )
        return self.leaflet.marker(
            self.map.unproject(self.leaflet.point(x, y), zoom),
            {
                "icon": icon,
                "pane": ARROWS_PANE[0],
                "interactive": False,
                "keyboard": False,
            },
        )

    def _create_labels(self):
        container = self.map.getContainer()
        for source in FLOW_SOURCES:
            arrow = html.SPAN(Class="flow-label-arrow")
            arrow.innerHTML = ARROW_SVG.format(
                size=ARROW_SIZE_PX + 4, color="currentColor", angle=0
            )
            chip = html.SPAN(
                [
                    arrow,
                    html.SPAN(
                        [
                            html.SPAN(source["title"], Class="flow-label-title"),
                            html.SPAN(
                                f"ไหลมุ่งสู่ {source['route']}",
                                Class="flow-label-route",
                            ),
                        ],
                        Class="flow-label-text",
                    ),
                ],
                Class="flow-label-chip",
            )
            tag = html.SPAN(
                [
                    html.SPAN(source["title"], Class="flow-label-tag-title"),
                    html.SPAN(f"→ {source['route']}", Class="flow-label-tag-route"),
                ],
                Class="flow-label-tag",
            )
            label = html.BUTTON([chip, tag], Class="flow-label", type="button")
            label.style.setProperty("--flow-color", source["color"])
            label.bind("click", lambda ev, s=source: self.fly_to_source(s))
            # The label sits inside the map container; without this the click
            # also reaches the map and drops a pin while pin mode is on.
            self.leaflet.DomEvent.disableClickPropagation(label)

            big_arrow = html.DIV(Class="flow-source-arrow")
            big_arrow.innerHTML = SOURCE_ARROW_SVG.format(color=source["color"])
            container.appendChild(big_arrow)
            container.appendChild(label)
            self.labels.append((source, label, arrow, big_arrow))

    def fly_to_source(self, source):
        zoom = max(self.map.getZoom(), LABEL_FLY_MIN_ZOOM)
        self.map.flyTo([source["lat"], source["lng"]], zoom)

    def place_labels(self):
        size = self.map.getSize()
        left, top, right, bottom = PIN_INSETS
        placed = []
        for source, label, arrow, big_arrow in self.labels:
            width = label.offsetWidth or FALLBACK_LABEL_SIZE[0]
            height = label.offsetHeight or FALLBACK_LABEL_SIZE[1]
            # Pin the label's centre inside a box inset by half its own size,
            # so a pinned label is never cut off by the map edge.
            min_x = left + width / 2 + LABEL_EDGE_GAP_PX
            min_y = top + height / 2 + LABEL_EDGE_GAP_PX
            span_x = max(size.x - right - width - 2 * LABEL_EDGE_GAP_PX - left, 0)
            span_y = max(size.y - bottom - height - 2 * LABEL_EDGE_GAP_PX - top, 0)

            at = self.map.latLngToContainerPoint([source["lat"], source["lng"]])
            x, y, edge = pin_to_edge(at.x - min_x, at.y - min_y, span_x, span_y, 0)
            placed.append(
                {
                    "source": source,
                    "label": label,
                    "arrow": arrow,
                    "big_arrow": big_arrow,
                    "x": x + min_x,
                    "y": y + min_y,
                    "width": width + LABEL_EDGE_GAP_PX,
                    "height": height + LABEL_EDGE_GAP_PX,
                    "edge": edge,
                }
            )

        # Sources close together pin to the same spot on an edge; slide those
        # labels apart along it.
        for edge, axis in (
            ("top", "x"),
            ("bottom", "x"),
            ("left", "y"),
            ("right", "y"),
        ):
            group = [p for p in placed if p["edge"] == edge]
            if axis == "x":
                bounds = (left, size.x - right)
                dim = "width"
            else:
                bounds = (top, size.y - bottom)
                dim = "height"
            spread = spread_along_edge(
                [p[axis] for p in group], [p[dim] for p in group], *bounds
            )
            for p, centre in zip(group, spread):
                p[axis] = centre

        for p in placed:
            if p["edge"]:
                dest = self.map.latLngToContainerPoint(
                    [p["source"]["dest_lat"], p["source"]["dest_lng"]]
                )
                angle = screen_bearing(p["x"], p["y"], dest.x, dest.y)
            else:
                angle = p["source"]["angle"]
            p["label"].style.left = f"{p['x']}px"
            p["label"].style.top = f"{p['y']}px"
            p["arrow"].style.transform = f"rotate({round(angle, 1)}deg)"
            p["label"].classList.toggle("is-pinned", bool(p["edge"]))

            big_arrow = p["big_arrow"]
            if p["edge"]:
                big_arrow.style.display = "none"
                continue
            reach = (
                box_reach(p["width"], p["height"], angle)
                + SOURCE_ARROW_SIZE_PX[1] / 2
                + SOURCE_ARROW_GAP_PX
            )
            dx, dy = upstream_offset(angle, reach)
            big_arrow.style.display = "block"
            big_arrow.style.left = f"{p['x'] + dx}px"
            big_arrow.style.top = f"{p['y'] + dy}px"
            big_arrow.style.transform = (
                f"translate(-50%, -50%) rotate({round(angle, 1)}deg)"
            )
