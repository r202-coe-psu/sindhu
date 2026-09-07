from browser import alert, window, ajax
import json


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
        self._selected_zone_id = None
        self._on_zone_select = None
        self._zone_renderer = None
        self.reference_boundary_layer = None
        self._reference_boundary_renderer = None
        self.zone_shading_mode = "outline"
        self.zones_visible = True
        self.reference_boundary_visible = True

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
    REFERENCE_BOUNDARY_STYLE = {
        "fillColor": "#000000",
        "color": "#000000",
        "weight": 2,
        "opacity": 1,
        "fillOpacity": 0,
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
        is_ref = (
            zone.get("zone_kind") == "reference"
            or custom_style.get("role") == "reference_boundary"
            or zone.get("code") == "hatyai-boundary"
        )
        dash_array = "8, 6" if is_ref else custom_style.get("dashArray", "")
        stroke_weight = 3.0 if is_ref else max(float(custom_style.get("stroke-width", 2.5)), 2.5)

        zone_shading = custom_style.get("shading_mode") or getattr(self, "zone_shading_mode", "outline")
        is_shaded = (zone_shading == "shaded")
        fill_opacity_normal = float(custom_style.get("fill-opacity", 0.28)) if is_shaded else 0.0
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
                        "fillOpacity": min(fill_opacity_normal + 0.15, 0.65) if is_shaded else 0.08,
                        "color": stroke,
                        "weight": stroke_weight + 1.0,
                        "opacity": 1.0,
                        "dashArray": dash_array,
                    }
                elif state == "selected":
                    return {
                        "fillColor": fill if is_shaded else stroke,
                        "fillOpacity": min(fill_opacity_normal + 0.22, 0.70) if is_shaded else 0.12,
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

        # Active flood alert (risk >= 1: warning, critical, evacuation)
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
            fill_opacity = 0.0 if state == "normal" else (0.08 if state == "hover" else 0.12)

        return {
            "fillColor": alert_fill,
            "fillOpacity": fill_opacity,
            "color": alert_color,
            "weight": stroke_weight + 1.5 if state == "selected" else (stroke_weight + 1.0 if state == "hover" else stroke_weight),
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
        self.clear_reference_boundary()

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

            if zone.get("zone_kind", "flood") == "reference":
                self.show_reference_boundary(
                    boundary,
                    zone.get("name_th") or zone.get("name") or "ขอบเขตหาดใหญ่",
                )
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

            stroke_color = style.get("stroke") or style.get("fill") or self.ZONE_STYLE["color"]
            weight_val = max(float(style.get("stroke-width") or 2.5), 2.5)

            zone_shading = style.get("shading_mode") or getattr(self, "zone_shading_mode", "outline")
            is_shaded = (zone_shading == "shaded")
            fill_color = style.get("fill") or stroke_color if is_shaded else "transparent"
            fill_opacity = float(style.get("fill-opacity") or 0.28) if is_shaded else 0.0

            feature_style = {
                "fillColor": fill_color,
                "fillOpacity": fill_opacity,
                "color": stroke_color,
                "weight": weight_val,
                "opacity": 0.95,
                "dashArray": style.get("dashArray", ""),
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
            }

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
        for entry in self.zone_layers_by_id.values():
            self.map.removeLayer(entry["layer"])
        self.zone_layers_by_id = {}
        self._selected_zone_id = None

    def show_reference_boundary(self, boundary, name="ขอบเขตหาดใหญ่"):
        """Draw a permanent, non-interactive boundary reference.

        This layer is intentionally kept outside ``zone_layers_by_id`` so it
        cannot be selected or recoloured by flood-zone risk updates.
        """
        if not boundary:
            return False

        self.clear_reference_boundary()

        pane = self.map.getPane("reference-boundary")
        if not pane:
            pane = self.map.createPane("reference-boundary")
            pane.style.zIndex = "360"

        if self._reference_boundary_renderer is None:
            self._reference_boundary_renderer = self.leaflet.svg(
                {"pane": "reference-boundary"}
            )

        feature = boundary
        if boundary.get("type") != "Feature":
            feature = {
                "type": "Feature",
                "properties": {"name": name},
                "geometry": boundary,
            }

        layer = self.leaflet.geoJson(
            feature,
            {
                "pane": "reference-boundary",
                "renderer": self._reference_boundary_renderer,
                "interactive": False,
                "style": lambda f: dict(self.REFERENCE_BOUNDARY_STYLE),
            },
        ).addTo(self.map)
        self.reference_boundary_layer = layer
        self.shapes["reference_boundary"] = layer
        return True

    def clear_reference_boundary(self):
        """Remove and forget the reference layer when reloading map data."""
        if self.reference_boundary_layer is not None:
            if self.map.hasLayer(self.reference_boundary_layer):
                self.map.removeLayer(self.reference_boundary_layer)
            self.reference_boundary_layer = None
        self.shapes.pop("reference_boundary", None)

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

        self.geojson = self.leaflet.geoJson(
            data,
            {
                "style": style,
                "onEachFeature": on_each_feature,
                "renderer": self.leaflet.svg(),
            },
        ).addTo(self.map)
        self.shapes["rivers"] = self.geojson

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

                print("🎉 โหลดข้อมูลเส้นแม่น้ำสงขลาลงแผนที่สำเร็จ!")
            else:
                print(f"❌ โหลดข้อมูล GeoJSON ล้มเหลว (Status: {req.status})")

        print("กำลังดึงข้อมูลแม่น้ำจาก API...")
        req = ajax.Ajax()
        req.bind("complete", on_complete)
        req.open("GET", f"{api_url}/v1/basins", True)
        req.send()
