"""The Songkhla waterway network, with the three drainage systems through
Hat Yai marked by direction arrows and "water comes from" labels that pin to
the screen edge when their source is off screen.

Every line is drawn in one blue; picking a label colours its system.

The geometry helpers are pure functions on screen pixels (x right, y down) so
they run under CPython in tests; only ``FlowLayer`` touches Leaflet.
"""

import math

from browser import html, window

CORRIDORS = {
    "utapao": {"name": "คลองอู่ตะเภา", "color": "#1d4ed8"},
    "khuanlang": {"name": "คลองวาด → คลอง ร.1", "color": "#be123c"},
    "khohong": {"name": "คลองเรียน / คลอง ร.3-ร.6 → คลองเตย", "color": "#15803d"},
    "lake": {"name": "ทางน้ำออกทะเลสาบ", "color": "#7e22ce"},
}

# route: where the water heads.  angle: degrees clockwise from north of the
# big arrow drawn beside the label while the source is on screen.  system: the
# drainage system the label selects, or None for a label that only flies.
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
        "system": "utapao",
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
        "system": "khuanlang",
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
        "system": "khohong",
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
        "system": "lake",
        "color": CORRIDORS["lake"]["color"],
    },
]

# The waterway lines are OpenStreetMap data (ODbL), which requires this credit.
OSM_ATTRIBUTION = (
    '&copy; <a href="https://www.openstreetmap.org/copyright">'
    "OpenStreetMap</a> contributors"
)
ARROW_SPACING_PX = 100
ARROW_SIZE_PX = 18
# Panes sit between overlayPane (400) and markerPane (600): above the zone
# fills and below the station markers.  Corridor lines get their own pane above
# the rest of the network so a selected system draws over the lines it crosses.
NETWORK_PANE = ("waterways", "410")
CORRIDOR_PANE = ("flowLines", "420")
ARROWS_PANE = ("flowArrows", "425")
# A mid blue that reads on the light basemap and stays apart from the
# highlighted utapao blue (#1d4ed8).
WATERWAY_COLOR = "#2f8fe0"
WATERWAY_WEIGHT_PX = {"river": 3.0, "canal": 2.2, "stream": 1.4, "drain": 1.1}
WATERWAY_OPACITY = 0.85
SELECTED_WEIGHT_PX = 4.5
SELECTED_OPACITY = 0.95
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


def waterway_style(fclass, systems, selected):
    """Leaflet style of one waterway line.

    A line in the ``selected`` system takes that system's colour and a heavier
    weight; every other line, in a system or not, is drawn as a plain waterway
    of its fclass.
    """
    if selected in systems:
        color, weight, opacity = (
            CORRIDORS[selected]["color"],
            SELECTED_WEIGHT_PX,
            SELECTED_OPACITY,
        )
    else:
        color = WATERWAY_COLOR
        weight = WATERWAY_WEIGHT_PX.get(fclass, WATERWAY_WEIGHT_PX["stream"])
        opacity = WATERWAY_OPACITY
    return {"color": color, "weight": weight, "opacity": opacity}


def arrow_color(systems, selected):
    return CORRIDORS[selected]["color"] if selected in systems else WATERWAY_COLOR


def fits_without_zooming_out(bounds_zoom, current_zoom):
    """Whether fitting a system keeps the map at its zoom or closer.

    A system bigger than the view (Sadao runs 140 km to the border) is shown
    by panning to its label instead, so a click never throws the user out.
    """
    return bounds_zoom >= current_zoom


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
    def __init__(self, leaflet_map, fit_options=None):
        self.map = leaflet_map
        self.leaflet = window.L
        self.fit_options = fit_options or (lambda: {})
        self.selected = None
        self.visible = True
        self.features = []
        # (corridor, polyline) per group of lines sharing a corridor and fclass.
        self.line_groups = []
        self.system_bounds = {}
        self.labels = []
        self._marks_by_zoom = None

        for pane in (NETWORK_PANE, CORRIDOR_PANE, ARROWS_PANE):
            self._create_pane(*pane)
        self.renderers = {
            pane[0]: self.leaflet.svg({"pane": pane[0]})
            for pane in (NETWORK_PANE, CORRIDOR_PANE)
        }
        self.line_layer = self.leaflet.layerGroup().addTo(self.map)
        self.arrow_layer = self.leaflet.layerGroup().addTo(self.map)

        if self.map.attributionControl:
            self.map.attributionControl.addAttribution(OSM_ATTRIBUTION)

        self._create_labels()
        self.map.on("zoomend moveend", lambda e: self.refresh_arrows())
        self.map.on("move zoom resize", lambda e: self.place_labels())
        self.map.on("click", self._on_map_click)
        self.place_labels()

    def _create_pane(self, name, z_index):
        pane = self.map.getPane(name) or self.map.createPane(name)
        pane.style.zIndex = z_index
        pane.style.pointerEvents = "none"

    def set_waterways(self, geojson):
        self.line_layer.clearLayers()
        self.line_groups = []
        self.features = []
        self.system_bounds = {}
        self._marks_by_zoom = None

        grouped = {}
        for feature in geojson.get("features", []):
            properties = feature.get("properties") or {}
            coordinates = (feature.get("geometry") or {}).get("coordinates") or []
            if len(coordinates) < 2:
                continue
            systems = tuple(
                s for s in properties.get("systems") or [] if s in CORRIDORS
            )
            latlngs = [[lat, lng] for lng, lat in coordinates]
            grouped.setdefault((systems, properties.get("fclass")), []).append(latlngs)
            if systems:
                self.features.append((systems, latlngs))
                for system in systems:
                    self.system_bounds.setdefault(system, []).extend(latlngs)

        for (systems, fclass), parts in grouped.items():
            pane = CORRIDOR_PANE if systems else NETWORK_PANE
            layer = self.leaflet.polyline(
                parts,
                {
                    "pane": pane[0],
                    "renderer": self.renderers[pane[0]],
                    "interactive": False,
                    "lineCap": "round",
                    "lineJoin": "round",
                    **waterway_style(fclass, systems, self.selected),
                },
            )
            self.line_layer.addLayer(layer)
            self.line_groups.append((systems, fclass, layer))
        self.refresh_arrows()

    def _on_map_click(self, e):
        # Selection stays put while the waterways are hidden, ready for the
        # checkbox to bring it back.
        if self.visible:
            self.select(None)

    def select(self, system):
        """Colour one drainage system, or all-blue for ``None``."""
        if system == self.selected:
            return
        self.selected = system
        for systems, fclass, layer in self.line_groups:
            layer.setStyle(waterway_style(fclass, systems, system))
            if system in systems:
                layer.bringToFront()
        for source, label, _arrow, _big_arrow in self.labels:
            label.setAttribute(
                "aria-pressed", str(bool(system and source["system"] == system)).lower()
            )
        self.refresh_arrows()

    def on_source_click(self, source):
        """Pick a label's system again to clear it."""
        system = source["system"]
        if system == self.selected:
            self.select(None)
        else:
            self.select(system)
            self.show_system(system, source)

    def show_system(self, system, source):
        bounds = self.leaflet.latLngBounds(self.system_bounds[system])
        current = self.map.getZoom()
        if fits_without_zooming_out(self.map.getBoundsZoom(bounds), current):
            self.map.fitBounds(bounds, {**self.fit_options(), "maxZoom": 15})
        else:
            self.map.flyTo([source["lat"], source["lng"]], current)

    def set_visible(self, visible):
        self.visible = visible
        for layer in (self.line_layer, self.arrow_layer):
            if visible:
                layer.addTo(self.map)
            else:
                self.map.removeLayer(layer)
        if visible:
            self.refresh_arrows()
        self.place_labels()

    def _marks_at(self, zoom):
        """Arrow marks of every line at ``zoom``, in world pixels.

        Cached per zoom: panning only moves the view over the same marks, and
        projecting every vertex is the costly part.
        """
        if self._marks_by_zoom and self._marks_by_zoom[0] == zoom:
            return self._marks_by_zoom[1]
        lines = []
        for systems, latlngs in self.features:
            points = []
            for latlng in latlngs:
                point = self.map.project(latlng, zoom)
                points.append((point.x, point.y))
            xs = [x for x, _ in points]
            ys = [y for _, y in points]
            bounds = (min(xs), min(ys), max(xs), max(ys))
            lines.append((systems, bounds, arrow_marks(points, ARROW_SPACING_PX)))
        self._marks_by_zoom = (zoom, lines)
        return lines

    def refresh_arrows(self):
        self.arrow_layer.clearLayers()
        if not self.visible:
            return
        zoom = self.map.getZoom()
        view = self.map.getPixelBounds()
        pad = ARROW_SIZE_PX
        left, top = view.min.x - pad, view.min.y - pad
        right, bottom = view.max.x + pad, view.max.y + pad

        for systems, (min_x, min_y, max_x, max_y), marks in self._marks_at(zoom):
            if max_x < left or min_x > right or max_y < top or min_y > bottom:
                continue
            color = arrow_color(systems, self.selected)
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
            label.setAttribute("aria-pressed", "false")
            label.bind("click", lambda ev, s=source: self.on_source_click(s))
            big_arrow = html.DIV(Class="flow-source-arrow")
            big_arrow.innerHTML = SOURCE_ARROW_SVG.format(color=source["color"])
            big_arrow.bind("click", lambda ev, s=source: self.on_source_click(s))
            # Both sit inside the map container; without this a click also
            # reaches the map, which would drop a pin in pin mode and clear
            # the selection it just made.
            for control in (label, big_arrow):
                self.leaflet.DomEvent.disableClickPropagation(control)

            container.appendChild(big_arrow)
            container.appendChild(label)
            self.labels.append((source, label, arrow, big_arrow))

    def place_labels(self):
        for _source, label, _arrow, big_arrow in self.labels:
            display = "" if self.visible else "none"
            label.style.display = display
            if not self.visible:
                big_arrow.style.display = display
        if not self.visible:
            return
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
