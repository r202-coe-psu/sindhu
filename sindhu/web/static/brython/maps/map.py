from browser import alert, window, ajax
import json
import math


def _haversine_distance(coord1, coord2):
    """Calculate distance in meters between two [lon, lat] coordinates."""
    try:
        lon1, lat1 = float(coord1[0]), float(coord1[1])
        lon2, lat2 = float(coord2[0]), float(coord2[1])
        r = 6371000.0
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlam = math.radians(lon2 - lon1)
        a = (
            math.sin(dphi / 2) ** 2
            + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
        )
        return 2 * r * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    except Exception:
        return float("inf")


class Map:
    def __init__(self, center, zoom, min_zoom):
        self.center = center
        self.zoom = zoom
        self.min_zoom = min_zoom
        # get data
        self.shapes = {}
        self.leaflet = window.L

        self.markers = None
        self.user_coord = None
        self.user_mark = []

        self.openstreet = self.leaflet.tileLayer(
            "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
            {
                "maxZoom": 19,
                "attribution": """&copy;
                <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors""",
            },
        )
        self.positron = self.leaflet.tileLayer(
            "https://{s}.basemaps.cartocdn.com/rastertiles/light_all/{z}/{x}/{y}.png",
            {
                "attribution": """&copy; <a href="http://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors,
                                &copy; <a href="http://cartodb.com/attributions">CartoDB</a>""",
                "subdomains": "abcd",
                "maxZoom": 19,
            },
        )
        self.world_imagery = self.leaflet.tileLayer(
            "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
            {
                "maxZoom": 19,
                "attribution": """Tiles &copy; Esri &mdash; Source: Esri, i-cubed, USDA, USGS, AEX, GeoEye,
                 Getmapping, Aerogrid, IGN, IGP, UPR-EGP, and the GIS User Community""",
            },
        )
        self.world_topo = self.leaflet.tileLayer(
            """https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}""",
            {
                "attribution": """Tiles &copy; Esri &mdash; Esri, DeLorme, NAVTEQ, TomTom, Intermap,
                 iPC, USGS, FAO, NPS, NRCAN, GeoBase, Kadaster NL, Ordnance Survey, Esri Japan, METI,
                 Esri China (Hong Kong), and the GIS User Community"""
            },
        )
        self.base_maps = {
            "<b><span style='color: grey'>Positron</span></b>": self.positron,
            "<b><span style='color: blue'>OpenStreet Map</span></b>": self.openstreet,
            "<b><span style='color: green'>World Map</span></b>": self.world_imagery,
            "<b><span style='color: teal'>World Topo Map</span></b>": self.world_topo,
        }

        container = self.leaflet.DomUtil.get("mapid")
        if "leaflet" in container.className:
            container._leaflet_id = ""
            # container.remove()

        self.map = self.leaflet.map(
            "mapid",
            {
                "preferCanvas": True,
                "center": self.center,
                "zoom": self.zoom,
                "min_zoom": self.min_zoom,
                "layers": self.openstreet,
                "renderer": self.leaflet.canvas({"padding": 0.5}),
                "scrollWheelZoom": False,  # disable original zoom function
                "smoothWheelZoom": True,  # enable smooth zoom
                "smoothSensitivity": 1,  # zoom speed. default is 1
                "zoomControl": False,
            },
        )

        self.leaflet.control.zoom({"position": "topright"}).addTo(self.map)

        # window.navigator.geolocation.getCurrentPosition(
        #     navi, nonavi
        # )  # set user's current location on map(success, error)

        self.leaflet.control.layers(self.base_maps).addTo(self.map)

        self.zone_layer = None
        self.station_lines = []
        self.station_markers = []
        self._on_pin_callback = None
        self._on_pin_off_callback = None
        self._pin_mode_active = False
        self._pin_btn = None
        self._reset_btn_container = None

        self.zone_layers_by_id = {}
        self.reference_boundary_layer = None
        self._selected_zone_id = None
        self._on_zone_select = None
        self._zone_renderer = None
        self.zone_shading_mode = "outline"
        self.zones_visible = True
        self.reference_boundary_visible = True
        # Visual feeds are a separate overlay. Station/source/zone filtering
        # only operates on BaseMap.metric_markers and must never mutate this
        # layer.
        self.visual_feed_layer = None
        self.visual_feed_markers = []
        self.visual_feed_markers_by_id = {}
        self.visual_feed_layer_visible = True
        self.visual_feeds = []
        self.latest_stations = []

        # A canvas renderer covers the whole overlay pane and would swallow
        # every click meant for the zone pane below it, so overlays that only
        # need to be seen are drawn with this shared SVG renderer instead.
        self.overlay_svg_renderer = self.leaflet.svg()

    """
    ===========================================================================
    Zones
    ===========================================================================
    """

    # Deliberately heavier than the river lines: the basins cover most of the
    # map, so a subtle outline disappears into them and the zone stops looking
    # clickable.
    # Boundary lines without shaded fill: keeps the underlying map and streets
    # clearly visible while distinctly showing zone perimeters.
    ZONE_STYLE = {
        "fillColor": "transparent",
        "fillOpacity": 0.0,
        "color": "#4338ca",
        "weight": 2.5,
        "opacity": 0.95,
        "dashArray": "",
    }
    ZONE_HOVER_STYLE = {
        "fillColor": "#6366f1",
        "fillOpacity": 0.08,
        "color": "#3730a3",
        "weight": 3.5,
        "opacity": 1.0,
        "dashArray": "",
    }
    ZONE_SELECTED_STYLE = {
        "fillColor": "#2563eb",
        "fillOpacity": 0.12,
        "color": "#1d4ed8",
        "weight": 4.0,
        "opacity": 1.0,
        "dashArray": "",
    }

    def set_zone_risk(self, zone_id, level):
        """Colour a zone by the worst risk among its stations."""
        entry = self.zone_layers_by_id.get(str(zone_id))
        if not entry:
            return False

        entry["risk"] = level
        if self._selected_zone_id != str(zone_id):
            entry["layer"].setStyle(self.zone_style(str(zone_id)))
        else:
            entry["layer"].setStyle(self.zone_style(str(zone_id), "selected"))
        return True

    def zone_style(self, zone_id, state="normal"):
        """Style for one zone in a given interaction state."""
        entry = self.zone_layers_by_id.get(str(zone_id)) or {}
        level = entry.get("risk")
        zone = entry.get("zone") or {}
        custom_style = zone.get("style") or zone.get("metadata") or {}

        fill = custom_style.get("fill", self.ZONE_STYLE["fillColor"])
        stroke = custom_style.get("stroke") or fill or self.ZONE_STYLE["color"]
        is_ref = (custom_style.get("role") == "reference_boundary") or (
            zone.get("code") == "hatyai-boundary"
        )
        dash_array = "8, 6" if is_ref else custom_style.get("dashArray", "")
        stroke_weight = (
            3.0 if is_ref else max(float(custom_style.get("stroke-width", 2.5)), 2.5)
        )

        zone_shading = custom_style.get("shading_mode") or getattr(
            self, "zone_shading_mode", "outline"
        )
        is_shaded = zone_shading == "shaded"
        fill_opacity_normal = (
            float(custom_style.get("fill-opacity", 0.28)) if is_shaded else 0.0
        )
        fill_color_normal = fill if is_shaded else "transparent"

        risk_val = level.get("risk", -1) if level else -1

        # Reference boundary or normal water level (risk <= 0):
        # Strictly preserve the admin-configured zone color and shading mode.
        # NEVER recolor normal zones to green!
        if is_ref or risk_val <= 0:
            if custom_style:
                if state == "hover":
                    return {
                        "fillColor": fill if is_shaded else stroke,
                        "fillOpacity": (
                            min(fill_opacity_normal + 0.15, 0.65) if is_shaded else 0.08
                        ),
                        "color": stroke,
                        "weight": stroke_weight + 1.0,
                        "opacity": 1.0,
                        "dashArray": dash_array,
                    }
                elif state == "selected":
                    return {
                        "fillColor": fill if is_shaded else stroke,
                        "fillOpacity": (
                            min(fill_opacity_normal + 0.22, 0.70) if is_shaded else 0.12
                        ),
                        "color": stroke,
                        "weight": stroke_weight + 1.5,
                        "opacity": 1.0,
                        "dashArray": dash_array,
                    }
                return {
                    "fillColor": fill_color_normal,
                    "fillOpacity": fill_opacity_normal,
                    "color": stroke,
                    "weight": stroke_weight,
                    "opacity": 0.95,
                    "dashArray": dash_array,
                }
            base = {
                "normal": self.ZONE_STYLE,
                "hover": self.ZONE_HOVER_STYLE,
                "selected": self.ZONE_SELECTED_STYLE,
            }[state]
            style_copy = dict(base)
            if is_shaded:
                style_copy["fillColor"] = style_copy.get("fillColor", "#6366f1")
                style_copy["fillOpacity"] = 0.25 if state == "normal" else 0.35
            return style_copy

        # Active flood alert (risk >= 1: warning, critical)
        alert_color = level.get("border") or level.get("color")
        if is_shaded:
            alert_fill = level.get("color")
            fill_opacity = min(level.get("fill_opacity", 0.28), 0.50)
            if state == "hover":
                fill_opacity = min(fill_opacity + 0.12, 0.65)
            elif state == "selected":
                fill_opacity = min(fill_opacity + 0.20, 0.70)
        else:
            alert_fill = "transparent" if state == "normal" else alert_color
            fill_opacity = (
                0.0 if state == "normal" else (0.08 if state == "hover" else 0.12)
            )

        return {
            "fillColor": alert_fill,
            "fillOpacity": fill_opacity,
            "color": alert_color,
            "weight": (
                stroke_weight + 1.5
                if state == "selected"
                else (stroke_weight + 1.0 if state == "hover" else stroke_weight)
            ),
            "opacity": 1.0 if state != "normal" else 0.95,
            "dashArray": dash_array,
        }

    def set_zone_shading_mode(self, mode):
        """Toggle zone fill between outline-only (transparent) and shaded (colored fill)."""
        self.zone_shading_mode = mode
        for key, entry in self.zone_layers_by_id.items():
            state = "selected" if self._selected_zone_id == key else "normal"
            entry["layer"].setStyle(self.zone_style(key, state))

    def set_zone_visible(self, zone_identifier, visible):
        """Set visibility of an individual zone by id, code, or zone_number."""
        ident = str(zone_identifier).strip().lower()
        entry = self.zone_layers_by_id.get(str(zone_identifier))
        if not entry:
            for zid, e in self.zone_layers_by_id.items():
                z = e.get("zone") or {}
                meta = z.get("metadata") or {}
                znum = str(meta.get("zone_number") or "").strip()
                zcode = str(z.get("code") or "").strip().lower()
                zname = str(z.get("name") or "").strip().lower()
                zname_th = str(z.get("name_th") or "").strip().lower()
                if ident in [str(zid).lower(), znum, zcode, zname, zname_th]:
                    entry = e
                    break
        if not entry:
            return False

        layer = entry["layer"]
        if visible:
            if not self.map.hasLayer(layer):
                layer.addTo(self.map)
        else:
            if self.map.hasLayer(layer):
                self.map.removeLayer(layer)
        return True

    def set_zones_visible(self, visible):
        """Show or hide all zone polygon layers."""
        self.zones_visible = visible
        for entry in self.zone_layers_by_id.values():
            layer = entry["layer"]
            if visible:
                if not self.map.hasLayer(layer):
                    layer.addTo(self.map)
            else:
                if self.map.hasLayer(layer):
                    self.map.removeLayer(layer)

    def set_reference_boundary_visible(self, visible):
        """Show or hide the Hat Yai reference boundary layer."""
        self.reference_boundary_visible = visible
        if not self.reference_boundary_layer:
            return
        if visible:
            if not self.map.hasLayer(self.reference_boundary_layer):
                self.reference_boundary_layer.addTo(self.map)
        else:
            if self.map.hasLayer(self.reference_boundary_layer):
                self.map.removeLayer(self.reference_boundary_layer)

    def show_all_zones(self, zones, on_select=None):
        """Draw every zone boundary so users can click a zone directly.

        Zones live in their own pane below the overlay pane, which keeps the
        river lines and the station markers clickable on top of them.
        """
        self._on_zone_select = on_select
        self.clear_all_zones()

        if not zones:
            return

        pane = self.map.getPane("zones")
        if not pane:
            pane = self.map.createPane("zones")
            pane.style.zIndex = "350"

        if self._zone_renderer is None:
            self._zone_renderer = self.leaflet.svg({"pane": "zones"})
        zone_renderer = self._zone_renderer

        for zone in zones:
            if zone.get("status") == "inactive":
                continue

            boundary = zone.get("boundary")
            if not boundary:
                continue

            zone_id = str(zone.get("id", ""))
            if not zone_id:
                continue

            name = zone.get("name_th") or zone.get("name") or ""
            style = zone.get("style") or zone.get("metadata") or {}
            feature = {
                "type": "Feature",
                "properties": {"name": name},
                "geometry": boundary,
            }

            stroke_color = (
                style.get("stroke") or style.get("fill") or self.ZONE_STYLE["color"]
            )
            is_ref = style.get("role") == "reference_boundary"
            weight_val = (
                3.0 if is_ref else max(float(style.get("stroke-width") or 2.5), 2.5)
            )
            dash_array = "8, 6" if is_ref else ""

            zone_shading = style.get("shading_mode") or getattr(
                self, "zone_shading_mode", "outline"
            )
            is_shaded = zone_shading == "shaded"
            fill_color = (
                style.get("fill") or stroke_color if is_shaded else "transparent"
            )
            fill_opacity = (
                float(style.get("fill-opacity") or 0.28) if is_shaded else 0.0
            )

            feature_style = {
                "fillColor": fill_color,
                "fillOpacity": fill_opacity,
                "color": stroke_color,
                "weight": weight_val,
                "opacity": 0.95,
                "dashArray": dash_array,
            }

            layer = self.leaflet.geoJson(
                feature,
                {
                    "pane": "zones",
                    "renderer": zone_renderer,
                    "style": feature_style,
                },
            )
            if name:
                layer.bindTooltip(
                    name,
                    {"sticky": True, "direction": "top", "className": "zone-label"},
                )

            layer.on("mouseover", self._make_zone_hover(zone_id, True))
            layer.on("mouseout", self._make_zone_hover(zone_id, False))
            layer.on("click", self._make_zone_click(zone_id, zone))
            if self.zones_visible:
                layer.addTo(self.map)

            self.zone_layers_by_id[zone_id] = {
                "layer": layer,
                "zone": zone,
                "risk": None,
                "style": style,
            }

    def clear_reference_boundary(self):
        if self.reference_boundary_layer and self.map.hasLayer(
            self.reference_boundary_layer
        ):
            self.map.removeLayer(self.reference_boundary_layer)
        self.reference_boundary_layer = None

    def show_reference_boundary(self, boundary, name="กรอบพื้นที่หาดใหญ่"):
        """Draw the Hat Yai reference boundary frame on the map."""
        if not boundary:
            return
        self.clear_reference_boundary()

        pane = self.map.getPane("reference_boundary")
        if not pane:
            pane = self.map.createPane("reference_boundary")
            pane.style.zIndex = "340"

        ref_renderer = self.leaflet.svg({"pane": "reference_boundary"})

        ref_style = {
            "fillColor": "#0f172a",
            "fillOpacity": 0.0,
            "color": "#0f172a",
            "weight": 3,
            "opacity": 0.85,
            "dashArray": "8, 6",
        }
        self.reference_boundary_layer = self.leaflet.geoJson(
            {
                "type": "Feature",
                "properties": {"name": "กรอบพื้นที่หาดใหญ่"},
                "geometry": boundary,
            },
            {
                "pane": "reference_boundary",
                "renderer": ref_renderer,
                "interactive": True,
                "style": ref_style,
            },
        ).bindTooltip(
            "กรอบพื้นที่หาดใหญ่ (Reference Boundary)",
            {"sticky": True, "direction": "top", "className": "ref-boundary-label"},
        )
        if self.reference_boundary_visible:
            self.reference_boundary_layer.addTo(self.map)

    def fit_to_hatyai_bounds(self):
        """Fit map view to Hat Yai reference boundary or loaded zones."""
        try:
            if self.reference_boundary_layer:
                bounds = self.reference_boundary_layer.getBounds()
                if bounds and bounds.isValid():
                    self.map.fitBounds(bounds, {"padding": [24, 24]})
                    return
            if self.zone_layers_by_id:
                group = self.leaflet.featureGroup(
                    [entry["layer"] for entry in self.zone_layers_by_id.values()]
                )
                bounds = group.getBounds()
                if bounds and bounds.isValid():
                    self.map.fitBounds(bounds, {"padding": [24, 24]})
        except Exception as e:
            print(f"fit_to_hatyai_bounds error: {e}")

    def _make_zone_hover(self, zone_id, entering):
        def handler(e):
            if self._pin_mode_active or self._selected_zone_id == zone_id:
                return
            entry = self.zone_layers_by_id.get(zone_id)
            if not entry:
                return
            entry["layer"].setStyle(
                self.zone_style(zone_id, "hover" if entering else "normal")
            )

        return handler

    def _make_zone_click(self, zone_id, zone):
        def handler(e):
            # Leaflet's _findEventTargets walks the DOM up to the map
            # container, so the map's own click handler fires for this click
            # too. Pin mode is already served by it — stepping in here would
            # place the pin and hit /locate twice.
            if self._pin_mode_active:
                return

            self.select_zone(zone_id)
            if self._on_zone_select:
                self._on_zone_select(zone)

        return handler

    def select_zone(self, zone_id, fit_bounds=True):
        zone_id = str(zone_id)
        entry = self.zone_layers_by_id.get(zone_id)
        if not entry:
            return False

        self._selected_zone_id = zone_id
        # The other zones keep their normal dashed outline: they stay visible
        # and clickable so a different zone can be picked straight away.
        for key, other in self.zone_layers_by_id.items():
            if key == zone_id:
                other["layer"].setStyle(self.zone_style(key, "selected"))
                other["layer"].bringToFront()
            else:
                other["layer"].setStyle(self.zone_style(key))

        if fit_bounds:
            self.map.fitBounds(entry["layer"].getBounds(), {"padding": [24, 24]})

        self.show_reset_button()
        return True

    def clear_zone_selection(self):
        self._selected_zone_id = None
        for zone_id, entry in self.zone_layers_by_id.items():
            entry["layer"].setStyle(self.zone_style(zone_id))

    def clear_all_zones(self):
        # The permanent reference boundary is deliberately not part of this
        # collection. Clearing/selecting flood zones must leave it visible.
        for entry in self.zone_layers_by_id.values():
            self.map.removeLayer(entry["layer"])
        self.zone_layers_by_id = {}
        self._selected_zone_id = None

    def __del__(self):
        self.map.remove()

    def enable_pin_mode(self, callback, off_callback=None):
        self._on_pin_callback = callback
        self._on_pin_off_callback = off_callback
        self._add_pin_control()

    def _add_pin_control(self):
        from browser import document as doc

        zoom_bar = doc.select_one(".leaflet-top.leaflet-right .leaflet-bar")
        if not zoom_bar:
            return

        btn = doc.createElement("a")
        btn.href = "#"
        btn.title = "ปักหมุดบนแผนที่"
        btn.attrs["role"] = "button"
        btn.html = '<svg width="14" height="18" viewBox="0 0 30 40"><path d="M15 0C6.7 0 0 6.7 0 15c0 10.5 13.2 23.7 14 24.5.5.5 1.3.5 1.8 0C16.8 38.7 30 25.5 30 15 30 6.7 23.3 0 15 0z" fill="#6b7280"/><circle cx="15" cy="15" r="6" fill="#fff"/></svg>'
        btn.style.cssText = "display:flex;align-items:center;justify-content:center;width:30px;height:30px;cursor:pointer;border-top:1px solid #ccc;"
        self._pin_btn = btn

        hint = doc.getElementById("pin_hint_banner")

        def toggle(e):
            e.preventDefault()
            e.stopPropagation()
            self._pin_mode_active = not self._pin_mode_active
            svg_path = btn.select_one("path")
            if self._pin_mode_active:
                btn.style.backgroundColor = "#dbeafe"
                if svg_path:
                    svg_path.attrs["fill"] = "#2563eb"
                self.map.getContainer().style.cursor = "crosshair"
                if hint:
                    hint.classList.remove("hidden")
            else:
                btn.style.backgroundColor = ""
                if svg_path:
                    svg_path.attrs["fill"] = "#6b7280"
                self.map.getContainer().style.cursor = ""
                if hint:
                    hint.classList.add("hidden")
                self.remove_pin()
                self.clear_zone_display()
                if self._on_pin_off_callback:
                    self._on_pin_off_callback()

        btn.bind("click", toggle)
        zoom_bar <= btn

        map_container = self.map.getContainer()
        reset_div = doc.createElement("div")
        reset_div.style.cssText = "display:none;position:absolute;bottom:12px;left:50%;transform:translateX(-50%);z-index:1000;"
        reset_btn = doc.createElement("button")
        # The button now restores the whole starting view, not just the markers
        reset_btn.html = (
            '<i class="ph ph-arrow-counter-clockwise"></i> กลับสู่มุมมองเริ่มต้น'
        )
        reset_btn.style.cssText = "background:white;color:#2563eb;border:1px solid #e5e7eb;border-radius:9999px;padding:6px 16px;font-size:13px;cursor:pointer;box-shadow:0 2px 6px rgba(0,0,0,0.15);display:flex;align-items:center;gap:6px;"
        reset_div <= reset_btn
        map_container <= reset_div
        self._reset_btn_container = reset_div

        def on_reset(e):
            e.preventDefault()
            e.stopPropagation()
            self.reset_all()
            if self._on_pin_off_callback:
                self._on_pin_off_callback()

        reset_btn.bind("click", on_reset)

        self.map.on("click", self._handle_map_click)

    def show_reset_button(self, visible=True):
        if self._reset_btn_container:
            self._reset_btn_container.style.display = "block" if visible else "none"

    def reset_view(self):
        """Fly back to the centre and zoom the map was created with."""
        self.map.flyTo(self.center, self.zoom)

    def reset_all(self):
        """Put the map back in the state it had when the page first loaded."""
        self.remove_pin()
        self.clear_zone_display()
        self.reset_view()
        self.show_reset_button(False)

    def set_visual_feed_layer(self, markers):
        """Replace the independent visual-feed layer without touching stations."""
        if self.visual_feed_layer is not None and self.map.hasLayer(
            self.visual_feed_layer
        ):
            self.map.removeLayer(self.visual_feed_layer)

        self.visual_feed_markers = markers if isinstance(markers, list) else []
        layer = self.leaflet.layerGroup()
        for m in self.visual_feed_markers:
            layer.addLayer(m)
        self.visual_feed_layer = layer
        if self.visual_feed_layer_visible:
            self.visual_feed_layer.addTo(self.map)
        return self.visual_feed_layer

    def set_visual_feed_layer_visible(self, visible):
        """Toggle only the visual-feed overlay; station markers are untouched."""
        self.visual_feed_layer_visible = bool(visible)
        if self.visual_feed_layer is None:
            return

        if self.visual_feed_layer_visible:
            if not self.map.hasLayer(self.visual_feed_layer):
                self.visual_feed_layer.addTo(self.map)
        elif self.map.hasLayer(self.visual_feed_layer):
            self.map.removeLayer(self.visual_feed_layer)

    def find_matching_cctv(self, station):
        """Find the nearest co-located CCTV camera for a given water station."""
        if not hasattr(self, "visual_feeds") or not self.visual_feeds:
            return None
        st_code = str(station.get("code") or "").strip().lower()
        scoord_obj = station.get("coordinates")
        s_coords = (
            scoord_obj.get("coordinates") if isinstance(scoord_obj, dict) else None
        )

        best = None
        min_dist = float("inf")
        for feed in self.visual_feeds:
            c_code = str(feed.get("code") or "").strip().lower()
            if st_code and c_code and st_code == c_code:
                return feed
            ccoord_obj = feed.get("coordinates")
            c_coords = (
                ccoord_obj.get("coordinates") if isinstance(ccoord_obj, dict) else None
            )
            if s_coords and c_coords and len(s_coords) >= 2 and len(c_coords) >= 2:
                dist = _haversine_distance(s_coords, c_coords)
                if dist <= 300 and dist < min_dist:
                    min_dist = dist
                    best = feed
        return best

    def find_matching_station(self, feed):
        """Find the nearest co-located water station for a given CCTV camera."""
        if not hasattr(self, "latest_stations") or not self.latest_stations:
            return None
        c_code = str(feed.get("code") or "").strip().lower()
        ccoord_obj = feed.get("coordinates")
        c_coords = (
            ccoord_obj.get("coordinates") if isinstance(ccoord_obj, dict) else None
        )

        best = None
        min_dist = float("inf")
        for station in self.latest_stations:
            st_code = str(station.get("code") or "").strip().lower()
            if c_code and st_code and c_code == st_code:
                return station
            scoord_obj = station.get("coordinates")
            s_coords = (
                scoord_obj.get("coordinates") if isinstance(scoord_obj, dict) else None
            )
            if s_coords and c_coords and len(s_coords) >= 2 and len(c_coords) >= 2:
                dist = _haversine_distance(s_coords, c_coords)
                if dist <= 300 and dist < min_dist:
                    min_dist = dist
                    best = station
        return best

    def show_visual_feeds(self, feeds, on_feed_click=None):
        """Create and display CCTV markers on the visual_feed_layer with custom CCTV hallmark."""
        if not feeds or not hasattr(self, "leaflet") or not self.leaflet:
            return

        self.visual_feeds = feeds
        markers = []
        self.visual_feed_markers_by_id = {}
        availability_colors = {
            "online": "#16a34a",
            "stale": "#d97706",
            "degraded": "#ea580c",
            "offline": "#dc2626",
            "unknown": "#64748b",
        }
        availability_labels = {
            "online": "ออนไลน์",
            "stale": "ข้อมูลเก่า",
            "degraded": "ขัดข้องบางส่วน",
            "offline": "ออฟไลน์",
            "unknown": "ไม่ทราบสถานะ",
        }

        for feed in feeds:
            if not isinstance(feed, dict):
                continue
            coords_obj = feed.get("coordinates")
            if not coords_obj or not isinstance(coords_obj, dict):
                continue
            coords = coords_obj.get("coordinates")
            if not coords or not isinstance(coords, list) or len(coords) < 2:
                continue

            lng, lat = coords[0], coords[1]
            if lat is None or lng is None:
                continue

            availability = str(feed.get("availability", "unknown")).lower()
            color = availability_colors.get(availability, "#64748b")
            status_label = availability_labels.get(availability, "ไม่ทราบสถานะ")

            title = (
                feed.get("title_th")
                or feed.get("name_th")
                or feed.get("name")
                or "กล้อง CCTV"
            )
            source = str(feed.get("source", ""))
            upstream_id = str(feed.get("upstream_id", ""))
            image_url = feed.get("image_url") or ""

            # Hallmark: Modern CCTV camera pin icon with status color
            pulse_ring = (
                f'<div class="cctv-live-glow" style="position: absolute; width: 12px; height: 12px; top: 7px; left: 8px; border-radius: 50%; pointer-events: none;"></div>'
                if availability == "online"
                else ""
            )

            icon_html = f"""<div class="cctv-marker-pin" style="position: relative; filter: drop-shadow(0 2px 5px rgba(0,0,0,0.32)); cursor: pointer;">
  {pulse_ring}
  <svg width="28" height="35" viewBox="0 0 34 42" fill="none" xmlns="http://www.w3.org/2000/svg">
    <path d="M17 0C7.6 0 0 7.6 0 17C0 28.5 15.2 40.8 15.8 41.3C16.5 41.9 17.5 41.9 18.2 41.3C18.8 40.8 34 28.5 34 17C34 7.6 26.4 0 17 0Z" fill="{color}"/>
    <circle cx="17" cy="16" r="12.5" fill="white" fill-opacity="0.25"/>
    <g transform="translate(8.5, 9.5)">
      <rect x="0" y="2" width="11" height="8.5" rx="2" fill="white"/>
      <path d="M11 4.5L16 2V11L11 8.5V4.5Z" fill="white"/>
      <circle cx="5.5" cy="6.25" r="1.8" fill="{color}"/>
    </g>
  </svg>
</div>"""

            pin_icon = self.leaflet.divIcon(
                {
                    "className": "custom-cctv-pin",
                    "html": icon_html,
                    "iconSize": [28, 35],
                    "iconAnchor": [14, 35],
                    "popupAnchor": [0, -32],
                }
            )

            marker = self.leaflet.marker(
                [lat, lng],
                {
                    "icon": pin_icon,
                    "zIndexOffset": 500,
                    "title": title,
                },
            )

            marker.bindTooltip(
                f"<div style='font-family:inherit;font-size:12px;padding:2px;'><div style='font-weight:700;color:#0f172a;'>📷 {title}</div><div style='color:{color};font-weight:600;font-size:11px;margin-top:2px;'>● {status_label}</div></div>",
                {"direction": "top", "offset": [0, -32]},
            )

            preview_img = ""
            if image_url:
                preview_img = f"""<div style="margin-top:6px; border-radius:8px; overflow:hidden; aspect-ratio:16/9; background:#0f172a; box-shadow:0 1px 3px rgba(0,0,0,0.1); display:flex; align-items:center; justify-content:center;">
  <img src="{image_url}" alt="{title}" style="width:100%; height:100%; object-fit:cover; display:block;" onerror="this.style.display='none'; this.parentElement.innerHTML='<div style=\\'color:#94a3b8; font-size:11px;\\'>ไม่มีภาพตัวอย่าง</div>'" />
</div>"""

            # Check if there is a co-located water level station
            matched_st = self.find_matching_station(feed)
            water_btn_html = ""
            if matched_st:
                st_code = str(matched_st.get("code", ""))
                st_src = str(matched_st.get("source", ""))
                st_name = str(matched_st.get("name_th") or matched_st.get("name", ""))
                water_btn_html = f"""
  <button type="button" onclick="if(window.focus_water_station)window.focus_water_station('{st_code}','{st_src}')"
    style="margin-top:5px; width:100%; background:#0284c7; color:white; font-size:11px; font-weight:600; padding:6px 10px; border-radius:8px; border:none; cursor:pointer; text-align:center; display:flex; align-items:center; justify-content:center; gap:4px; box-shadow:0 1px 2px rgba(2,132,199,0.2);">
    <span>🌊 ดูข้อมูลระดับน้ำ ({st_name})</span>
  </button>"""

            popup_html = f"""<div class="cctv-map-popup" style="font-family:inherit; min-width:240px; max-width:280px; padding:4px;">
  <div style="display:flex; align-items:flex-start; justify-content:space-between; gap:6px; margin-bottom:4px;">
    <div style="font-weight:700; font-size:13px; color:#0f172a; line-height:1.25;">{title}</div>
    <span style="background:{color}; color:white; font-size:10px; font-weight:700; padding:2px 7px; border-radius:9999px; white-space:nowrap; box-shadow:0 1px 2px rgba(0,0,0,0.1);">
      {status_label}
    </span>
  </div>
  {preview_img}
  <button type="button" onclick="if(window.open_cctv_detail)window.open_cctv_detail('{source}','{upstream_id}')"
    style="margin-top:8px; width:100%; background:#2563eb; color:white; font-size:11px; font-weight:600; padding:7px 10px; border-radius:8px; border:none; cursor:pointer; text-align:center; box-shadow:0 1px 2px rgba(37,99,235,0.2); transition:background 0.15s;">
    🔍 ดูภาพสด / ประวัติ 7 วัน
  </button>
  {water_btn_html}
</div>"""

            marker.bindPopup(popup_html, {"maxWidth": 290})

            if on_feed_click:
                marker.on("click", lambda e, f=feed: on_feed_click(f))

            markers.append(marker)
            key = f"{source}_{upstream_id}"
            self.visual_feed_markers_by_id[key] = marker

        self.set_visual_feed_layer(markers)

    def fly_to_visual_feed(self, source, upstream_id, zoom=17):
        """Fly map view to the specified camera and open its popup."""
        key = f"{source}_{upstream_id}"
        marker = self.visual_feed_markers_by_id.get(key)
        if marker:
            latlng = marker.getLatLng()
            self.map.flyTo(latlng, zoom)
            marker.openPopup()

    def _handle_map_click(self, e):
        if not self._pin_mode_active:
            return
        lat = e.latlng.lat
        lng = e.latlng.lng
        self.place_pin(lat, lng)
        if self._on_pin_callback:
            self._on_pin_callback(lat, lng)

    def place_pin(self, lat, lng):
        self.user_coord = (lat, lng)
        pin_icon = self.leaflet.divIcon(
            {
                "className": "",
                "html": '<div style="filter:drop-shadow(0 2px 4px rgba(0,0,0,0.35));"><svg width="30" height="40" viewBox="0 0 30 40"><path d="M15 0C6.7 0 0 6.7 0 15c0 10.5 13.2 23.7 14 24.5.5.5 1.3.5 1.8 0C16.8 38.7 30 25.5 30 15 30 6.7 23.3 0 15 0z" fill="#dc2626"/><circle cx="15" cy="15" r="6" fill="#fff"/></svg></div>',
                "iconSize": [30, 40],
                "iconAnchor": [15, 40],
                "popupAnchor": [0, -36],
            }
        )
        if (
            hasattr(self, "user_mark")
            and self.user_mark
            and not isinstance(self.user_mark, list)
        ):
            self.user_mark.setLatLng(self.user_coord)
            self.user_mark.setIcon(pin_icon)
            self.user_mark.setPopupContent("ตำแหน่งที่เลือก")
        else:
            self.user_mark = (
                self.leaflet.marker(
                    self.user_coord,
                    {"icon": pin_icon, "zIndexOffset": 1000},
                )
                .addTo(self.map)
                .bindPopup("ตำแหน่งที่เลือก")
            )
        self.show_reset_button()

    def remove_pin(self):
        if (
            hasattr(self, "user_mark")
            and self.user_mark
            and not isinstance(self.user_mark, list)
        ):
            self.map.removeLayer(self.user_mark)
            self.user_mark = []
            self.user_coord = None
        self.show_reset_button(False)

    def clear_zone_display(self):
        self.clear_zone_selection()
        if self.zone_layer:
            self.map.removeLayer(self.zone_layer)
            self.zone_layer = None
        for line in self.station_lines:
            self.map.removeLayer(line)
        self.station_lines = []
        for marker in self.station_markers:
            self.map.removeLayer(marker)
        self.station_markers = []

    def show_zone(self, zone_geojson):
        if self.zone_layer:
            self.map.removeLayer(self.zone_layer)

        def get_val(obj, key_name, default_val=None):
            if obj is None:
                return default_val
            if isinstance(obj, dict):
                return obj.get(key_name, default_val)
            return getattr(obj, key_name, default_val)

        def get_style(feature):
            props = get_val(feature, "properties", {})
            fill_color = get_val(props, "fillColor", "#3b82f6")
            color = get_val(props, "color", "#2563eb")
            fill_opacity = get_val(props, "fillOpacity", 0.15)
            weight = get_val(props, "weight", 2)
            return {
                "fillColor": fill_color,
                "fillOpacity": fill_opacity,
                "color": color,
                "weight": weight,
                "dashArray": "",
            }

        self.zone_layer = self.leaflet.geoJson(
            zone_geojson,
            {
                "interactive": False,
                "renderer": self.overlay_svg_renderer,
                "style": get_style,
            },
        ).addTo(self.map)

    def show_station_paths(self, user_latlng, stations):
        for line in self.station_lines:
            self.map.removeLayer(line)
        self.station_lines = []
        for marker in self.station_markers:
            self.map.removeLayer(marker)
        self.station_markers = []

        line_renderer = self.overlay_svg_renderer

        first = True
        for station in stations:
            code = station.get("code")
            markers = self.metric_markers_by_code.get(code) or []
            if not markers:
                continue

            marker = markers[0]
            station_latlng = marker.getLatLng()

            if first:
                style = {
                    "color": "#dc2626",
                    "weight": 2.5,
                    "opacity": 0.8,
                    "interactive": False,
                    "renderer": line_renderer,
                }
                first = False
            else:
                style = {
                    "color": "#3b82f6",
                    "weight": 1.5,
                    "opacity": 0.4,
                    "interactive": False,
                    "renderer": line_renderer,
                }

            line = self.leaflet.polyline(
                [list(user_latlng), [station_latlng.lat, station_latlng.lng]],
                style,
            ).addTo(self.map)
            self.station_lines.append(line)

    def fly_to_user(self):
        self.map.locate()

        def on_location_found(e):
            self.user_coord = (e.latlng.lat, e.latlng.lng)

            self.map.flyTo(self.user_coord, 16)

            my_location_icon = self.leaflet.divIcon(
                {
                    "className": "",
                    "html": '<div style="filter:drop-shadow(0 2px 4px rgba(0,0,0,0.35));"><i class="ph-fill ph-map-pin text-blue-600 text-3xl"></i></div>',
                    "iconSize": [30, 30],
                    "iconAnchor": [15, 30],
                    "popupAnchor": [0, -30],
                }
            )

            if (
                hasattr(self, "user_mark")
                and self.user_mark
                and not isinstance(self.user_mark, list)
            ):
                self.user_mark.setLatLng(self.user_coord)
                self.user_mark.setIcon(my_location_icon)
                self.user_mark.setPopupContent("ตำแหน่งของคุณ")
            else:
                self.user_mark = (
                    self.leaflet.marker(
                        self.user_coord,
                        {
                            "icon": my_location_icon,
                            "zIndexOffset": 1000,
                        },
                    )
                    .addTo(self.map)
                    .bindPopup("ตำแหน่งของคุณ")
                )

            self.map.off("locationfound", on_location_found)
            self.map.off("locationerror", on_location_error)

        def on_location_error(e):
            alert(f"ไม่สามารถระบุตำแหน่งได้: {e.message}")
            self.map.off("locationfound", on_location_found)
            self.map.off("locationerror", on_location_error)

        # ผูกเหตุการณ์
        self.map.on("locationfound", on_location_found)
        self.map.on("locationerror", on_location_error)

    def zoom_out(self):
        self.map.zoomOut(1)

    def zoom_in(self):
        self.map.zoomIn(1)

    def on_each_feature(self, feature, layer):  # feature = layer.feature
        def zoom_to_feature(e):
            if self.map.getZoom() < 11:
                self.map.fitBounds(e.target.getBounds())

        def reset_highlight(e):
            for key in self.shapes:
                if self.shapes[key].hasLayer(layer):
                    self.shapes[key].resetStyle(e.target)

        def highlight_feature(e):
            layer = e.target

            layer.setStyle(
                {"weight": 2, "color": "#000000", "dashArray": "", "fillOpacity": 0}
            )

        layer.on(
            {
                "mouseover": highlight_feature,
                "mouseout": reset_highlight,
                "click": zoom_to_feature,
            }
        )

    def set_shape_with_key(self, data, key):
        if not data or len(data) == 0:
            return

        def style(feature):
            # 🌟 ฟังก์ชันตัวช่วย: ดึงค่าได้ชัวร์ๆ ไม่ว่าจะเป็น Dict (Python) หรือ Object (Javascript)
            def get_val(obj, key_name, default_val=None):
                if obj is None:
                    return default_val
                if isinstance(obj, dict):
                    return obj.get(key_name, default_val)  # ท่าของ Python
                return getattr(obj, key_name, default_val)  # ท่าของ Javascript

            default_color = "#C6C6C6"

            # 1. ค่อยๆ แกะข้อมูลออกมาทีละชั้นอย่างปลอดภัย
            properties = get_val(feature, "properties", {})
            geom = get_val(feature, "geometry", {})
            geom_type = get_val(geom, "type", "")

            if geom_type == "Point":
                default_color = "#FF6600"

            # 2. ดึงค่าสี (รองรับการตั้งชื่อตัวแปรที่ต่างกันใน GeoJSON)
            color_fallback = get_val(properties, "color", default_color)
            fill_color = get_val(properties, "fill", color_fallback)

            # รองรับทั้งคีย์ชื่อ "fill_opa" และ "fill-opacity"
            fill_opa_val = get_val(properties, "fill_opa", 0.5)
            fill_opacity = get_val(properties, "fill-opacity", fill_opa_val)

            stroke_w_val = get_val(properties, "stroke_w", 1)
            stroke_w = get_val(properties, "stroke-width", stroke_w_val)

            stroke_opa_val = get_val(properties, "stroke_opa", 1)
            stroke_opacity = get_val(properties, "stroke-opacity", stroke_opa_val)

            stroke_color = get_val(properties, "stroke", default_color)

            return {
                "fillColor": fill_color,
                "fillOpacity": fill_opacity,
                "color": stroke_color,
                "weight": stroke_w,
                "opacity": stroke_opacity,
            }

        def on_each_feature(feature, layer):  # feature = layer.feature

            def get_val(obj, key_name, default_val=None):
                if obj is None:
                    return default_val
                if isinstance(obj, dict):
                    return obj.get(key_name, default_val)
                return getattr(obj, key_name, default_val)

            def zoom_to_feature(e):
                target_feature = e.target.feature

                # 💣 กู้ระเบิดเวลา: แกะ geometry.type แบบปลอดภัย
                geom = get_val(target_feature, "geometry", {})
                geom_type = get_val(geom, "type", "")

                if self.map.getZoom() < 11 and geom_type != "Point":
                    self.map.fitBounds(e.target.getBounds())

            def reset_highlight(e):
                for key in self.shapes:
                    if self.shapes[key].hasLayer(layer):
                        self.shapes[key].resetStyle(e.target)

            def highlight_feature(e):
                target_layer = e.target
                target_layer.setStyle({"weight": 2, "fillOpacity": 0.7})

            popup_detail = ""
            date_txt = {"th": "วันที่", "en": "Date"}
            zone_txt = {"th": "พื้นที่", "en": "Zone"}

            properties = get_val(feature, "properties", {})
            name = get_val(properties, "Name", None)

            if name:
                popup_detail += f"<div>{name}</div>"

            if des_th := get_val(properties, "DES_TH"):
                popup_detail += f"<div>{des_th}</div>"

            if popup_detail != "":
                layer.bindPopup(popup_detail)

            layer.on(
                {
                    "mouseover": highlight_feature,
                    "mouseout": reset_highlight,
                    "click": zoom_to_feature,
                }
            )

        self.geojson = self.leaflet.geoJson(
            data,
            {
                "pointToLayer": lambda feature, latlng: self.leaflet.circle(
                    latlng,
                    {"radius": 250},
                ),
                "style": style,
                "onEachFeature": on_each_feature,
            },
        ).addTo(self.map)
        self.shapes[key] = self.geojson

        if (
            not self.leaflet.Browser.ie
            and not self.leaflet.Browser.opera
            and not self.leaflet.Browser.edge
        ):
            self.geojson.bringToFront()

    def set_rivers_layer(self, data):
        """Dedicated method for rendering river/waterway GeoJSON with flow animation."""
        if not data or len(data) == 0:
            return

        # River selection state (scoped to this layer only)
        self._selected_river = None
        self._river_clicked = False

        def get_val(obj, key_name, default_val=None):
            if obj is None:
                return default_val
            if isinstance(obj, dict):
                return obj.get(key_name, default_val)
            return getattr(obj, key_name, default_val)

        def style(feature):
            properties = get_val(feature, "properties", {})
            stroke_color = get_val(properties, "stroke", "#C6C6C6")
            stroke_w = get_val(
                properties, "stroke-width", get_val(properties, "stroke_w", 2)
            )
            return {
                "color": stroke_color,
                "weight": stroke_w,
                "opacity": 0.3,
                "fillOpacity": 0,
                "className": "river-line",
            }

        def _clear_river_selection(self_ref):
            """Helper to reset the currently selected river layer."""
            if self_ref._selected_river:
                prev = self_ref._selected_river
                if "rivers" in self_ref.shapes and self_ref.shapes["rivers"].hasLayer(
                    prev
                ):
                    self_ref.shapes["rivers"].resetStyle(prev)
                if hasattr(prev, "_path") and prev._path:
                    prev._path.classList.remove("flowing-river")
                self_ref._selected_river = None

        def on_map_click(e):
            if self._river_clicked:
                self._river_clicked = False
                return
            _clear_river_selection(self)

        self.map.on("click", on_map_click)

        def on_each_feature(feature, layer):

            def highlight_feature(e):
                target_layer = e.target
                feature_obj = target_layer.feature
                props = get_val(feature_obj, "properties", {})
                color = get_val(props, "stroke", "#0984e3")
                target_layer.setStyle({"weight": 5, "color": color, "opacity": 0.95})
                if hasattr(target_layer, "_path") and target_layer._path:
                    target_layer._path.classList.add("flowing-river")

            def zoom_to_feature(e):
                if getattr(self, "_pin_mode_active", False):
                    return
                target_layer = e.target
                self._river_clicked = True

                target_feature = target_layer.feature
                geom = get_val(target_feature, "geometry", {})
                geom_type = get_val(geom, "type", "")
                if self.map.getZoom() < 11 and geom_type != "Point":
                    self.map.fitBounds(target_layer.getBounds())

                # Reset previous selection, then set new one
                if self._selected_river and self._selected_river != target_layer:
                    _clear_river_selection(self)
                self._selected_river = target_layer
                highlight_feature(e)

            # Build popup content
            popup_detail = ""
            properties = get_val(feature, "properties", {})
            name = get_val(properties, "Name", None)
            if name:
                display_name = name
                if name == "Waterway":
                    lang = getattr(self, "lang_code", "th")
                    display_name = (
                        "เส้นทางน้ำ (ไม่ระบุชื่อ)"
                        if lang == "th"
                        else "Unnamed Waterway"
                    )
                popup_detail += f"<div>{display_name}</div>"

            if popup_detail:
                layer.bindPopup(popup_detail)

            layer.on(
                {
                    "click": zoom_to_feature,
                }
            )

        if "rivers" in self.shapes and self.shapes["rivers"] is not None:
            if self.map.hasLayer(self.shapes["rivers"]):
                self.map.removeLayer(self.shapes["rivers"])
            self.shapes.pop("rivers", None)

        self.shapes["rivers"] = self.leaflet.geoJson(
            data,
            {
                "style": style,
                "onEachFeature": on_each_feature,
                "renderer": self.leaflet.svg(),
            },
        ).addTo(self.map)

    def set_shape_boundary(self, data):
        def style(feature):
            return {
                "fillColor": "#000000",
                "color": "#000000",
                "weight": 2,
                "opacity": 1,
                "fillOpacity": 0,
            }

        self.geojson = self.leaflet.geoJson(
            data,
            {
                "pointToLayer": lambda feature, latlng: self.leaflet.circle(
                    latlng, {"radius": 250}
                ),
                "style": style,
                "onEachFeature": self.on_each_feature,
            },
        ).addTo(self.map)
        self.shapes["boundary"] = self.geojson
        # self.map.fitBounds(self.geojson.getBounds())

    def get_shape(self):
        return self.geojson

    def load_river_basins(self, api_url):
        """ฟังก์ชันสำหรับดึงข้อมูล GeoJSON ลุ่มน้ำจาก API และวาดลงแผนที่"""

        def on_complete(req):
            if req.status == 200 or req.status == 0:
                geojson_data = json.loads(req.text)

                # กำหนดสไตล์เส้นแม่น้ำ
                river_style = {
                    "color": "#3388ff",  # สีฟ้า
                    "weight": 2,  # ความหนาของเส้น
                    "opacity": 0.8,  # ความโปร่งใส
                }

                # ใช้ self.leaflet.geoJson วาดเส้น และเก็บไว้ใน self.shapes

                # Own canvas renderer, kept transparent to the mouse: a shared
                # canvas covers the whole overlay pane and would otherwise
                # swallow every click meant for the zone polygons underneath.
                basin_renderer = self.leaflet.canvas({"padding": 0.5})
                self.shapes["river_basins"] = self.leaflet.geoJson(
                    geojson_data,
                    {
                        "style": river_style,
                        "interactive": False,
                        "renderer": basin_renderer,
                    },
                ).addTo(self.map)

                basin_canvas = getattr(basin_renderer, "_container", None)
                if basin_canvas:
                    basin_canvas.style.pointerEvents = "none"

                print("[Map] River basins loaded successfully")
            else:
                print(f"[Map] Failed to load river basins (status: {req.status})")

        print("[Map] Fetching river basins from API...")
        req = ajax.Ajax()
        req.bind("complete", on_complete)
        req.open("GET", f"{api_url}/v1/basins", True)
        req.send()
