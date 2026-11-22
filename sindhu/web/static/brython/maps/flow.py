"""Drainage corridors through Hat Yai: coloured lines, direction arrows and
"water comes from" labels that pin to the screen edge when their source is
off screen.

The geometry helpers are pure functions on screen pixels (x right, y down) so
they run under CPython in tests; only ``FlowLayer`` touches Leaflet.
"""

import math

from browser import html, window

CORRIDORS = {
    "utapao-main": {"name": "คลองอู่ตะเภา (สายหลัก)", "color": "#1d4ed8"},
    "khlong-r1": {"name": "คลอง ร.1 (ผันน้ำเลี่ยงเมือง)", "color": "#be123c"},
    "khlong-toei": {"name": "คลองเตย", "color": "#15803d"},
    "kho-hong": {"name": "คอหงส์ / คลอง ร.3-ร.6", "color": "#b45309"},
    "khlong-non": {"name": "คลองวาด (ควนลัง)", "color": "#7e22ce"},
    "phawong": {"name": "คลองสำโรง (พะวง)", "color": "#0e7490"},
}

# angle: degrees clockwise from north for the label arrow while the source is
# on screen.
FLOW_SOURCES = [
    {
        "id": "sadao",
        "title": "น้ำจากสะเดา",
        "route": "ไหลสู่ทะเลสาบสงขลา",
        "lat": 6.84,
        "lng": 100.4706,
        "dest_lat": 7.15,
        "dest_lng": 100.465,
        "angle": 0,
        "color": CORRIDORS["utapao-main"]["color"],
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
        "color": CORRIDORS["khlong-r1"]["color"],
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
        "color": CORRIDORS["khlong-toei"]["color"],
    },
    {
        "id": "lake",
        "title": "น้ำออกทะเลสาบ",
        "route": "ระบายลงทะเลสาบสงขลา",
        "lat": 7.135,
        "lng": 100.465,
        "dest_lat": 7.25,
        "dest_lng": 100.465,
        "angle": 0,
        "color": "#0c4a6e",
    },
]

ARROW_SPACING_PX = 100
ARROW_SIZE_PX = 18
LINE_WEIGHT_PX = 4
LABEL_FLY_MIN_ZOOM = 13
# Between overlayPane (400) and markerPane (600): above the zone fills and
# below the station markers.
LINES_PANE = ("flowLines", "420")
ARROWS_PANE = ("flowArrows", "425")
FALLBACK_LABEL_SIZE = (180, 56)
LABEL_EDGE_GAP_PX = 8
# (left, top, right, bottom) px of the map that pinned labels keep clear: the
# brand, locate and panel cards across the top and the zoom controls down the right.
PIN_INSETS = (0, 112, 56, 0)

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

        self._create_pane(*LINES_PANE)
        self._create_pane(*ARROWS_PANE)
        self.line_renderer = self.leaflet.svg({"pane": LINES_PANE[0]})
        self.arrow_layer = self.leaflet.layerGroup().addTo(self.map)

        self._create_labels()
        self.map.on("zoomend moveend", lambda e: self.refresh_arrows())
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
            text = html.SPAN(
                [
                    html.SPAN(source["title"], Class="flow-label-title"),
                    html.SPAN(source["route"], Class="flow-label-route"),
                ],
                Class="flow-label-text",
            )
            label = html.BUTTON([arrow, text], Class="flow-label", type="button")
            label.style.background = source["color"]
            label.bind("click", lambda ev, s=source: self.fly_to_source(s))
            container.appendChild(label)
            self.labels.append((source, label, arrow))

    def fly_to_source(self, source):
        zoom = max(self.map.getZoom(), LABEL_FLY_MIN_ZOOM)
        self.map.flyTo([source["lat"], source["lng"]], zoom)

    def place_labels(self):
        size = self.map.getSize()
        left, top, right, bottom = PIN_INSETS
        placed = []
        for source, label, arrow in self.labels:
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
