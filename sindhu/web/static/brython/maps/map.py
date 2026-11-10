from browser import alert, window
from html import escape as escape_html
import re
import json

from maps.cctv_pairing import feed_key as visual_feed_key
from maps.cctv_pairing import pair_cameras, pin_shift
from maps.marker_sizes import CCTV, MY_LOCATION, USER, hit_box_html, is_far_zoom


VISUAL_FEED_POPUP_OPTIONS = {"minWidth": 240, "maxWidth": 280, "autoPanPadding": [24, 24]}


def _open_unless_popup(marker, feed, on_feed_click):
    # A pin showing its popup toggles that popup; it must not also open the
    # full viewer underneath.
    if not marker.getPopup():
        on_feed_click(feed)


class Map:
    # The open camera popup as (marker key, build_content).  It follows the
    # camera, not one marker object, because markers are rebuilt on every poll,
    # and its content is rebuilt from the latest data each time it opens.
    _visual_feed_popup = None
    _visual_feed_popup_flying = False
    _replacing_visual_feed_layer = False

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
        # Default basemap (#67): Windy-style neutral grey without labels, so
        # the rivers, zones and markers are the only colour on the map.  Esri's
        # Light Gray Canvas needs no API key (Carto's tiles now do, and show a
        # watermark without one); the .basemap-gray filter in setup.css turns
        # its land (#efefef) into ≈ #808080 with the sea a little darker.
        esri_canvas = "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas"
        self.gray = self.leaflet.tileLayer(
            esri_canvas + "/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}",
            {
                "attribution": "Tiles &copy; Esri &mdash; Esri, DeLorme, NAVTEQ",
                "maxNativeZoom": 16,  # canvas tiles stop at 16; scale beyond
                "maxZoom": 19,
                "className": "basemap-gray",
            },
        )
        # Place names to lay over the grey basemap when wanted.  Off by
        # default: the zones carry their own labels.
        self.place_labels = self.leaflet.tileLayer(
            esri_canvas + "/World_Dark_Gray_Reference/MapServer/tile/{z}/{y}/{x}",
            {
                "attribution": "Labels &copy; Esri &mdash; Esri, HERE, Garmin",
                "maxNativeZoom": 16,  # canvas tiles stop at 16; scale beyond
                "maxZoom": 19,
                "pane": "placeLabels",
            },
        )
        self.base_maps = {
            "เทา (ค่าเริ่มต้น)": self.gray,
            "OpenStreetMap": self.openstreet,
            "ภาพถ่ายดาวเทียม": self.world_imagery,
            "ภูมิประเทศ": self.world_topo,
        }
        self.overlay_maps = {"ชื่อสถานที่": self.place_labels}

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
                "layers": self.gray,
                "renderer": self.leaflet.canvas({"padding": 0.5}),
                "scrollWheelZoom": False,  # disable original zoom function
                "smoothWheelZoom": True,  # enable smooth zoom
                "smoothSensitivity": 1,  # zoom speed. default is 1
                "zoomControl": False,
            },
        )

        self.leaflet.control.zoom({"position": "topright"}).addTo(self.map)

        # Markers shrink at far zoom through CSS (.map-zoom-far), so the
        # icons never need rebuilding when the zoom changes
        # Pixel distances change with zoom, so camera pins are re-placed too
        self.map.on("zoomend", lambda e: self._on_zoomend())
        self.update_zoom_class()

        # window.navigator.geolocation.getCurrentPosition(
        #     navi, nonavi
        # )  # set user's current location on map(success, error)

        # Above the zones and rivers, below the markers, and transparent to
        # the mouse so everything underneath stays clickable.
        label_pane = self.map.createPane("placeLabels")
        label_pane.style.zIndex = "450"
        label_pane.style.pointerEvents = "none"
        self.leaflet.control.layers(self.base_maps, self.overlay_maps).addTo(self.map)

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
        self._selected_zone_ids = []
        self._on_zone_select = None
        self._zone_renderer = None
        self.zones_visible = True
        self.reference_boundary_visible = True
        # Visual feeds are a separate overlay. Station/source/zone filtering
        # only operates on BaseMap.metric_markers and must never mutate this
        # layer.
        self.visual_feed_layer = None
        self.visual_feed_markers = []
        self.visual_feed_markers_by_id = {}
        # key -> (dx, dy) px a camera pin is moved off its station
        self.visual_feed_shift = {}
        # camera key -> station, station id -> camera (see pair_cameras);
        # rebuilt when cameras or stations load, not on zoom or filter
        self.cctv_station_of = {}
        self.cctv_camera_of = {}
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

    # A zone shows two things at once (#67): its outline says which zone it
    # is, its fill says how risky it is.  The outline colours sit in hue gaps
    # the risk legend leaves free (green/orange/red/purple/grey) and away from
    # the light-cyan rivers; each zone also has its own dash pattern so the
    # three stay apart for colour-blind users.  A dark casing under every
    # outline keeps the lighter colours visible on the grey basemap.
    ZONE_IDENTITIES = (
        {"color": "#fef08a", "dash": ""},  # zone 1: pale lemon, solid
        {"color": "#ff2bd6", "dash": "10 6"},  # zone 2: magenta, dashed
        {"color": "#4f7cff", "dash": "2 6 10 6"},  # zone 3: vivid blue, dash-dot
    )
    ZONE_CASING_COLOR = "#141414"
    ZONE_WEIGHT = 2.6
    ZONE_RISK_FILL_OPACITY = 0.28
    HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")
    DASH_PATTERN = re.compile(r"^[0-9][0-9 ,.]*$")
    ZONE_CODE_NUMBER = re.compile(r"zone[-_ ]?([0-9]+)", re.IGNORECASE)

    @staticmethod
    def _is_reference_zone(zone, style=None):
        style = style or zone.get("style") or zone.get("metadata") or {}
        code = str(zone.get("code") or "").lower()
        return (
            zone.get("zone_kind") == "reference"
            or style.get("role") == "reference_boundary"
            or code in ("hatyai-boundary", "hatyai")
            or ("hatyai" in code and "zone" not in code)
            or zone.get("name") in ("Hat Yai", "Hat Yai Boundary", "กรอบพื้นที่หาดใหญ่")
            or zone.get("name_th") in ("หาดใหญ่", "กรอบพื้นที่หาดใหญ่")
        )

    @staticmethod
    def zone_number(zone):
        meta = zone.get("metadata") or {}
        number = meta.get("zone_number")
        if number is None:
            match = Map.ZONE_CODE_NUMBER.search(str(zone.get("code") or ""))
            number = match.group(1) if match else None
        try:
            number = int(number)
        except (TypeError, ValueError):
            return None
        return number if number > 0 else None

    @classmethod
    def _zone_order_key(cls, zone):
        number = cls.zone_number(zone)
        if number is not None:
            return (0, number, str(zone.get("code") or ""))
        return (1, 0, str(zone.get("code") or zone.get("name") or ""))

    def zone_identity(self, zone, fallback_index=0):
        style = zone.get("style") or zone.get("metadata") or {}
        number = self.zone_number(zone)
        index = number - 1 if number is not None else fallback_index
        preset = self.ZONE_IDENTITIES[index % len(self.ZONE_IDENTITIES)]
        color = str(style.get("stroke") or "")
        dash = str(style.get("dashArray") or "")
        return {
            "color": color if self.HEX_COLOR.match(color) else preset["color"],
            "dash": dash if self.DASH_PATTERN.match(dash) else preset["dash"],
        }

    def set_zone_risk(self, zone_id, level):
        """Fill a zone with the worst risk among its stations."""
        entry = self.zone_layers_by_id.get(str(zone_id))
        if not entry:
            return False

        entry["risk"] = level
        state = "selected" if str(zone_id) in self._selected_zone_ids else "normal"
        self._apply_zone_style(str(zone_id), state)
        return True

    def zone_style(self, zone_id, state="normal"):
        """Style for one zone in a given interaction state."""
        entry = self.zone_layers_by_id.get(str(zone_id)) or {}
        level = entry.get("risk")
        zone = entry.get("zone") or {}
        custom_style = zone.get("style") or zone.get("metadata") or {}

        # Reference boundaries are geographic context, not a risk zone.
        # Keep them as a plain outline without fill and never recolour them.
        if self._is_reference_zone(zone, custom_style):
            ref_color = (
                custom_style.get("stroke")
                or (
                    custom_style.get("fill")
                    if custom_style.get("fill") != "transparent"
                    else None
                )
                or "#0f172a"
            )
            return {
                "fillColor": "transparent",
                "fillOpacity": 0.0,
                "color": ref_color,
                "weight": 2.0,
                "opacity": 0.95,
                "dashArray": "",
                "interactive": False,
            }

        identity = entry.get("identity") or self.zone_identity(zone, 0)
        weight = self.ZONE_WEIGHT + {"hover": 1.0, "selected": 1.5}.get(state, 0.0)
        style = {
            "color": identity["color"],
            "dashArray": identity["dash"],
            "weight": weight,
            "opacity": 1.0,
            "fillColor": "transparent",
            "fillOpacity": 0.0,
        }

        # The fill carries the risk.  No data stays unfilled: grey on the
        # grey basemap would say nothing, and the legend calls it "ไม่ทราบ".
        risk = level.get("risk", -1) if level else -1
        if risk is not None and risk >= 0:
            base = self.ZONE_RISK_FILL_OPACITY
            try:
                if custom_style.get("fill-opacity") is not None:
                    base = min(max(float(custom_style["fill-opacity"]), 0.0), 1.0)
            except (TypeError, ValueError):
                pass
            style["fillColor"] = level.get("color")
            style["fillOpacity"] = min(
                base + {"hover": 0.10, "selected": 0.17}.get(state, 0.0), 0.6
            )
        elif state != "normal":
            # Still show which zone is under the pointer or selected.
            style["fillColor"] = identity["color"]
            style["fillOpacity"] = 0.08 if state == "hover" else 0.12
        return style

    def zone_casing_style(self, zone_style):
        """Dark line drawn under a zone outline so it reads on any basemap."""
        return {
            "color": self.ZONE_CASING_COLOR,
            "weight": zone_style["weight"] + 2.5,
            "opacity": 0.85,
            "fill": False,
            "dashArray": "",
        }

    def _apply_zone_style(self, zone_id, state="normal"):
        entry = self.zone_layers_by_id.get(str(zone_id))
        if not entry:
            return
        style = self.zone_style(str(zone_id), state)
        entry["layer"].setStyle(style)
        casing = entry.get("casing")
        if casing:
            casing.setStyle(self.zone_casing_style(style))

    def _set_zone_entry_visible(self, entry, visible):
        for key in ("casing", "layer"):
            layer = entry.get(key)
            if not layer:
                continue
            if visible and not self.map.hasLayer(layer):
                layer.addTo(self.map)
            elif not visible and self.map.hasLayer(layer):
                self.map.removeLayer(layer)

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

        self._set_zone_entry_visible(entry, visible)
        self._refresh_zone_legend()
        return True

    def set_zones_visible(self, visible):
        """Show or hide all zone polygon layers."""
        self.zones_visible = visible
        for entry in self.zone_layers_by_id.values():
            self._set_zone_entry_visible(entry, visible)
        self._refresh_zone_legend()

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
        river lines and the station markers clickable on top of them.  Their
        name labels sit in a pane above the rivers but below the markers.
        """
        self._on_zone_select = on_select
        self.clear_all_zones()

        if not zones:
            self._refresh_zone_legend()
            return

        pane = self.map.getPane("zones")
        if not pane:
            pane = self.map.createPane("zones")
            pane.style.zIndex = "350"
        label_pane = self.map.getPane("zoneLabels")
        if not label_pane:
            label_pane = self.map.createPane("zoneLabels")
            label_pane.style.zIndex = "450"
            label_pane.style.pointerEvents = "none"

        casing_pane = self.map.getPane("zoneCasings")
        if not casing_pane:
            casing_pane = self.map.createPane("zoneCasings")
            casing_pane.style.zIndex = "349"
            casing_pane.style.pointerEvents = "none"

        if self._zone_renderer is None:
            self._zone_renderer = self.leaflet.svg({"pane": "zones"})
            self._zone_casing_renderer = self.leaflet.svg({"pane": "zoneCasings"})
        zone_renderer = self._zone_renderer

        flood_zones = []
        for zone in zones:
            if zone.get("status") == "inactive" or not zone.get("boundary"):
                continue
            if not str(zone.get("id", "")) or self._is_reference_zone(zone):
                continue
            flood_zones.append(zone)
        flood_zones.sort(key=self._zone_order_key)

        for index, zone in enumerate(flood_zones):
            zone_id = str(zone.get("id"))
            name = zone.get("name_th") or zone.get("name") or ""
            style = zone.get("style") or zone.get("metadata") or {}
            identity = self.zone_identity(zone, index)
            feature = {
                "type": "Feature",
                "properties": {"name": name},
                "geometry": zone.get("boundary"),
            }
            entry = {
                "zone": zone,
                "risk": None,
                "style": style,
                "identity": identity,
            }
            self.zone_layers_by_id[zone_id] = entry
            initial = self.zone_style(zone_id)

            entry["casing"] = self.leaflet.geoJson(
                feature,
                {
                    "pane": "zoneCasings",
                    "renderer": self._zone_casing_renderer,
                    "interactive": False,
                    "style": self.zone_casing_style(initial),
                },
            )
            layer = self.leaflet.geoJson(
                feature,
                {
                    "pane": "zones",
                    "renderer": zone_renderer,
                    "interactive": True,
                    "style": initial,
                },
            )
            entry["layer"] = layer
            if name:
                layer.bindTooltip(
                    f'<span class="zone-chip" style="color:{identity["color"]};'
                    f'border-color:{identity["color"]};">{escape_html(name)}</span>',
                    {
                        "permanent": True,
                        "direction": "center",
                        "className": "zone-label",
                        "pane": "zoneLabels",
                        "interactive": False,
                    },
                )

            layer.on("mouseover", self._make_zone_hover(zone_id, True))
            layer.on("mouseout", self._make_zone_hover(zone_id, False))
            layer.on("click", self._make_zone_click(zone_id, zone))
            if self.zones_visible:
                self._set_zone_entry_visible(entry, True)

        self._refresh_zone_legend()

    def visible_zone_legend_entries(self):
        if not getattr(self, "zones_visible", True):
            return []
        entries = []
        for entry in getattr(self, "zone_layers_by_id", {}).values():
            layer = entry.get("layer")
            if layer is None or not self.map.hasLayer(layer):
                continue
            zone = entry.get("zone") or {}
            entries.append(
                {
                    "name": zone.get("name_th") or zone.get("name") or "",
                    "color": entry["identity"]["color"],
                    "dash": entry["identity"]["dash"],
                }
            )
        return entries

    def _refresh_zone_legend(self):
        """Let the legend (maps/legend.py) list the zone outlines it now has."""
        refresh = getattr(self, "refresh_legend", None)
        if refresh:
            refresh()

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
        pane.style.pointerEvents = "none"

        ref_renderer = self.leaflet.svg({"pane": "reference_boundary"})

        ref_style = {
            "fillColor": "transparent",
            "fillOpacity": 0.0,
            "color": "#0f172a",
            "weight": 2.0,
            "opacity": 0.95,
            "dashArray": "",
            "interactive": False,
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
                "interactive": False,
                "style": ref_style,
            },
        )
        if self.reference_boundary_visible:
            self.reference_boundary_layer.addTo(self.map)

    def fit_to_hatyai_bounds(self):
        """Fit map view to every loaded zone and the reference boundary."""
        try:
            bounds = self.leaflet.latLngBounds([])
            has_bounds = False

            # Extend the bounds explicitly instead of handing a Brython list to
            # Leaflet.featureGroup().  The latter can omit a layer while the
            # zones are still being initialised, which left Zone 4 clipped at
            # the top edge of the initial viewport.
            for entry in self.zone_layers_by_id.values():
                layer_bounds = entry["layer"].getBounds()
                if layer_bounds and layer_bounds.isValid():
                    bounds.extend(layer_bounds)
                    has_bounds = True

            if self.reference_boundary_layer:
                reference_bounds = self.reference_boundary_layer.getBounds()
                if reference_bounds and reference_bounds.isValid():
                    bounds.extend(reference_bounds)
                    has_bounds = True

            if has_bounds and bounds.isValid():
                self.map.invalidateSize({"pan": False})
                self.map.fitBounds(bounds, self.fit_bounds_options())
        except Exception as e:
            print(f"fit_to_hatyai_bounds error: {e}")

    def _make_zone_hover(self, zone_id, entering):
        def handler(e):
            if self._pin_mode_active or zone_id in self._selected_zone_ids:
                return
            entry = self.zone_layers_by_id.get(zone_id)
            if not entry:
                return
            self._apply_zone_style(zone_id, "hover" if entering else "normal")

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
        return self.select_zones([zone_id], fit_bounds)

    def select_zones(self, zone_ids, fit_bounds=True):
        """Highlight one or more zones and (optionally) fit their union bounds."""
        ids = []
        for zone_id in zone_ids or []:
            zone_id = str(zone_id)
            if zone_id in self.zone_layers_by_id and zone_id not in ids:
                ids.append(zone_id)
        if not ids:
            return False

        self._selected_zone_ids = ids
        # The other zones keep their normal dashed outline: they stay visible
        # and clickable so a different zone can be picked straight away.
        for key, other in self.zone_layers_by_id.items():
            if key in ids:
                self._apply_zone_style(key, "selected")
                if other.get("casing"):
                    other["casing"].bringToFront()
                other["layer"].bringToFront()
            else:
                self._apply_zone_style(key)

        if fit_bounds:
            bounds = None
            for key in ids:
                b = self.zone_layers_by_id[key]["layer"].getBounds()
                if bounds is None:
                    bounds = self.leaflet.latLngBounds(b.getSouthWest(), b.getNorthEast())
                else:
                    bounds.extend(b)
            self.map.fitBounds(bounds, self.fit_bounds_options())

        self.show_reset_button()
        return True

    def clear_zone_selection(self):
        self._selected_zone_ids = []
        for zone_id in self.zone_layers_by_id:
            self._apply_zone_style(zone_id)

    def clear_all_zones(self):
        # The permanent reference boundary is deliberately not part of this
        # collection. Clearing/selecting flood zones must leave it visible.
        for entry in self.zone_layers_by_id.values():
            self._set_zone_entry_visible(entry, False)
        self.zone_layers_by_id = {}
        self._selected_zone_ids = []

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
        btn.html = '<svg width="14" height="18" viewBox="0 0 30 40"><path d="M15 0C6.7 0 0 6.7 0 15c0 10.5 13.2 23.7 14 24.5.5.5 1.3.5 1.8 0C16.8 38.7 30 25.5 30 15 30 6.7 23.3 0 15 0z" fill="currentColor"/><circle cx="15" cy="15" r="6" style="fill:var(--color-base-100)"/></svg>'
        btn.style.cssText = "display:flex;align-items:center;justify-content:center;width:30px;height:30px;cursor:pointer;border-top:1px solid var(--color-ink-200);"
        self._pin_btn = btn

        hint = doc.getElementById("pin_hint_banner")

        def toggle(e):
            e.preventDefault()
            e.stopPropagation()
            self._pin_mode_active = not self._pin_mode_active
            svg_path = btn.select_one("path")
            if self._pin_mode_active:
                btn.style.backgroundColor = "var(--color-brand-100)"
                if svg_path:
                    svg_path.style.fill = "var(--color-brand-600)"
                self.map.getContainer().style.cursor = "crosshair"
                if hint:
                    hint.classList.remove("hidden")
            else:
                btn.style.backgroundColor = ""
                if svg_path:
                    svg_path.style.fill = ""
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
        reset_div.className = "map-reset"
        reset_div.style.cssText = "display:none;position:absolute;bottom:12px;left:50%;transform:translateX(-50%);z-index:1000;"
        reset_btn = doc.createElement("button")
        # The button now restores the whole starting view, not just the markers
        reset_btn.html = (
            '<i class="ph ph-arrow-counter-clockwise"></i> กลับสู่มุมมองเริ่มต้น'
        )
        reset_btn.style.cssText = "background:var(--color-base-100);color:var(--color-brand-600);border:1px solid var(--color-ink-200);border-radius:9999px;padding:6px 16px;font-size:13px;cursor:pointer;box-shadow:0 2px 6px rgba(0,0,0,0.15);display:flex;align-items:center;gap:6px;"
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

    """
    ===========================================================================
    Map focus mode
    ===========================================================================
    """

    FOCUS_BODY_CLASS = "map-focus"

    def add_focus_control(self):
        """Add the ⛶ button that hides every card floating on the map.

        The map already fills the window, so focus mode only toggles a class
        on <body>; CSS hides the `.map-ui` cards, the legends and the basemap
        picker.  Nothing changes size, so Leaflet needs no invalidateSize().
        """
        from browser import document as doc

        # Join the zoom bar (+ − and the pin) so ⛶ matches their size and
        # stays put when focus mode hides the basemap picker below it.
        zoom_bar = self.map.getContainer().querySelector(
            ".leaflet-top.leaflet-right .leaflet-control-zoom"
        )
        if getattr(self, "_focus_btn", None):
            return
        if not zoom_bar:
            print("[Map] focus control not added: zoom bar not found")
            return

        btn = doc.createElement("a")
        btn.href = "#"
        btn.className = "map-focus-btn"
        btn.attrs["role"] = "button"
        zoom_bar <= btn
        self._focus_btn = btn
        self._sync_focus_button(False)

        def on_click(ev):
            ev.preventDefault()
            self.set_focus_mode(not self.is_focus_mode())

        def on_key(ev):
            if ev.key != "Escape" or not self.is_focus_mode():
                return
            if ev.defaultPrevented or doc.querySelector("dialog[open]"):
                return
            self.set_focus_mode(False)

        btn.bind("click", on_click)
        doc.bind("keydown", on_key)

    def is_focus_mode(self):
        from browser import document as doc

        return doc.body.classList.contains(self.FOCUS_BODY_CLASS)

    def set_focus_mode(self, active):
        from browser import document as doc

        if active:
            doc.body.classList.add(self.FOCUS_BODY_CLASS)
        else:
            doc.body.classList.remove(self.FOCUS_BODY_CLASS)
        self._sync_focus_button(active)
        reset = getattr(self, "_reset_btn_container", None)
        lift = getattr(self, "_lift_reset_button_over_legends", None)
        if not active and lift and reset and reset.style.display != "none":
            lift()

    def _sync_focus_button(self, active):
        btn = getattr(self, "_focus_btn", None)
        if not btn:
            return
        label = "แสดงเมนูกลับมา" if active else "ซ่อนเมนู ดูแผนที่เต็มจอ"
        icon = "ph-corners-in" if active else "ph-corners-out"
        btn.title = label
        btn.attrs["aria-label"] = label
        btn.attrs["aria-pressed"] = "true" if active else "false"
        btn.html = f'<i class="ph {icon}" aria-hidden="true"></i>'

    def fit_bounds_options(self, margin=24):
        """fitBounds padding that keeps the target clear of the floating cards.

        The brand and user cards sit along the top.  The open data panel is a
        column on the right, so the right edge is padded by its width; a
        folded panel is only a pill under the user card, which the top
        padding already clears.  On a phone the open panel covers most of the
        map, so it is ignored rather than squeezing the target into a sliver.
        """
        from browser import document as doc

        top, right = margin, margin
        if not self.is_focus_mode():
            top = margin + 56
            panel = doc.getElementById("monitor_panel")
            if panel:
                rect = panel.getBoundingClientRect()
                is_column = rect.height > window.innerHeight / 2
                on_right_side = rect.left > window.innerWidth / 2
                if rect.width > 0 and is_column and on_right_side:
                    right = max(margin, window.innerWidth - rect.left + margin)
        return {
            "paddingTopLeft": [margin, top],
            "paddingBottomRight": [right, margin],
        }

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
            # Removing the old markers closes their popup; that is not the user.
            self._replacing_visual_feed_layer = True
            try:
                self.map.removeLayer(self.visual_feed_layer)
            finally:
                self._replacing_visual_feed_layer = False

        self.visual_feed_markers = markers if isinstance(markers, list) else []
        layer = self.leaflet.layerGroup()
        for m in self.visual_feed_markers:
            layer.addLayer(m)
        self.visual_feed_layer = layer
        if self.visual_feed_layer_visible:
            self.visual_feed_layer.addTo(self.map)
        if not self._visual_feed_popup_flying:
            self._show_visual_feed_popup()
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

    def update_zoom_class(self):
        container = self.map.getContainer()
        if is_far_zoom(self.map.getZoom()):
            container.classList.add("map-zoom-far")
        else:
            container.classList.remove("map-zoom-far")

    def _on_zoomend(self):
        self.update_zoom_class()
        self.refresh_cctv_pins()

    def station_marker(self, station_id):
        """The Leaflet marker of a station. The base Map draws no stations;
        BaseMap overrides this."""
        return None

    def update_cctv_pairs(self):
        """Re-pair cameras with stations; call when either list changes."""
        self.cctv_station_of, self.cctv_camera_of = pair_cameras(
            self.visual_feeds, self.latest_stations
        )

    def find_matching_cctv(self, station):
        """The CCTV camera linked to a water station (see pair_cameras)."""
        if not isinstance(station, dict):
            return None
        return self.cctv_camera_of.get(station.get("id"))

    @staticmethod
    def _feed_status(feed):
        """(is_fresh, pin color, Thai status label) of a camera."""
        is_fresh = str(feed.get("image_freshness", "stale")).lower() == "fresh"
        color = "#0284c7" if is_fresh else "#9ca3af"
        label = "ออนไลน์" if is_fresh else "ขาดการเชื่อมต่อ"
        return is_fresh, color, label

    @staticmethod
    def _feed_status_text_color(is_fresh):
        """Status text colour on the dark tooltip; matches .cctv-status--*."""
        return "var(--color-brand-600)" if is_fresh else "var(--color-ink-500)"

    def _build_cctv_icon(self, feed, shift=(0, 0)):
        """divIcon for a camera pin, moved by ``shift`` px off its station."""
        is_fresh, color, _label = self._feed_status(feed)
        # Modern CCTV camera pin icon with status color
        pulse_ring = (
            f'<div class="cctv-live-glow absolute w-2 h-2 top-[5px] left-[6px] rounded-full pointer-events-none"></div>'
            if is_fresh
            else ""
        )
        pin_w, pin_h = CCTV.pin
        pin_html = f"""<div class="cctv-marker-pin relative cursor-pointer [filter:drop-shadow(0_2px_5px_rgba(0,0,0,0.32))]">
  {pulse_ring}
  <svg class="block" width="{pin_w}" height="{pin_h}" viewBox="0 0 34 42" preserveAspectRatio="xMidYMax meet" fill="none" xmlns="http://www.w3.org/2000/svg">
    <path d="M17 0C7.6 0 0 7.6 0 17C0 28.5 15.2 40.8 15.8 41.3C16.5 41.9 17.5 41.9 18.2 41.3C18.8 40.8 34 28.5 34 17C34 7.6 26.4 0 17 0Z" fill="{color}"/>
    <circle cx="17" cy="16" r="12.5" fill="white" fill-opacity="0.25"/>
    <g transform="translate(8.5, 9.5)">
      <rect x="0" y="2" width="11" height="8.5" rx="2" fill="white"/>
      <path d="M11 4.5L16 2V11L11 8.5V4.5Z" fill="white"/>
      <circle cx="5.5" cy="6.25" r="1.8" fill="{color}"/>
    </g>
  </svg>
</div>"""
        return self._pin_icon(CCTV, pin_html, "custom-cctv-pin", shift)

    def _pin_icon(self, spec, pin_html, class_name="", shift=(0, 0)):
        """divIcon for a pin (a PinSpec) whose tip marks the point.

        ``shift`` moves the pin that many px off the point.
        """
        # iconAnchor is the icon pixel that lands on the point, so moving
        # the pin by (sx, sy) means subtracting it from the anchor. Popup
        # and tooltip anchors are relative to that point, so they move by
        # (sx, sy) to stay on the pin.
        sx, sy = shift
        anchor_x, anchor_y = spec.anchor
        return self.leaflet.divIcon(
            {
                "className": class_name,
                "html": hit_box_html(pin_html, *spec.hit_box, align="bottom"),
                "iconSize": list(spec.hit_box),
                "iconAnchor": [anchor_x - sx, anchor_y - sy],
                "popupAnchor": [sx, sy + spec.popup_offset_y],
                "tooltipAnchor": [sx, sy],
            }
        )

    def refresh_cctv_pins(self):
        """Move each camera pin off the station it is linked to, if they overlap.

        Call whenever stations load, are filtered, or the zoom changes. Only
        pins whose shift changed get a new icon.
        """
        if not self.visual_feeds or not self.visual_feed_markers_by_id:
            return
        for feed in self.visual_feeds:
            if not isinstance(feed, dict):
                continue
            key = visual_feed_key(feed.get("source", ""), feed.get("upstream_id", ""))
            marker = self.visual_feed_markers_by_id.get(key)
            if marker is None:
                continue
            shift = (0, 0)
            station = self.cctv_station_of.get(key)
            s_marker = self.station_marker(station.get("id")) if station else None
            # a filtered-out station covers nothing, so the pin stays put
            if s_marker is not None and self.map.hasLayer(s_marker):
                s_pt = self.map.latLngToLayerPoint(s_marker.getLatLng())
                c_pt = self.map.latLngToLayerPoint(marker.getLatLng())
                shift = pin_shift(c_pt.x - s_pt.x, c_pt.y - s_pt.y)
            if self.visual_feed_shift.get(key, (0, 0)) != shift:
                self.visual_feed_shift[key] = shift
                marker.setIcon(self._build_cctv_icon(feed, shift))
                # an open popup/tooltip reads its anchor only when it opens
                # or the map zooms, so move it to the new pin position
                if marker.isPopupOpen():
                    marker.getPopup().update()
                if marker.isTooltipOpen():
                    marker.getTooltip().update()

    def show_visual_feeds(self, feeds, on_feed_click=None):
        """Create and display CCTV markers on the visual_feed_layer."""
        if not hasattr(self, "leaflet") or not self.leaflet:
            return
        if not feeds:
            self.visual_feeds = []
            self.visual_feed_markers_by_id = {}
            self.visual_feed_shift = {}
            self.update_cctv_pairs()
            self.set_visual_feed_layer([])
            return

        self.visual_feeds = feeds
        markers = []
        self.visual_feed_markers_by_id = {}
        self.visual_feed_shift = {}
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

            is_fresh, _color, status_label = self._feed_status(feed)
            status_color = self._feed_status_text_color(is_fresh)

            title = (
                feed.get("title_th")
                or feed.get("name_th")
                or feed.get("name")
                or "กล้อง CCTV"
            )
            source = str(feed.get("source", ""))
            upstream_id = str(feed.get("upstream_id", ""))

            pin_icon = self._build_cctv_icon(feed)

            marker = self.leaflet.marker(
                [lat, lng],
                {
                    "icon": pin_icon,
                    "zIndexOffset": 500,
                    "title": title,
                },
            )

            marker.bindTooltip(
                f"<div class='font-sans text-xs p-0.5'><div class='font-bold text-ink-900'>{title}</div><div class='font-semibold text-[11px] mt-0.5' style='color:{status_color};'>● {status_label}</div></div>",
                {"direction": "top", "offset": [0, CCTV.popup_offset_y]},
            )

            if on_feed_click:
                marker.on(
                    "click",
                    lambda e, m=marker, f=feed: _open_unless_popup(m, f, on_feed_click),
                )

            markers.append(marker)
            key = visual_feed_key(source, upstream_id)
            self.visual_feed_markers_by_id[key] = marker

        self.set_visual_feed_layer(markers)
        # stations may have loaded before these cameras
        self.update_cctv_pairs()
        self.refresh_cctv_pins()

    def fly_to_visual_feed(self, source, upstream_id, zoom=17):
        """Fly the map to the specified camera without opening a second UI."""
        key = visual_feed_key(source, upstream_id)
        marker = self.visual_feed_markers_by_id.get(key)
        if marker:
            latlng = marker.getLatLng()
            self.map.flyTo(latlng, zoom)

    def open_visual_feed_popup(self, source, upstream_id, build_content, zoom=17):
        """Fly to a camera pin and show ``build_content()`` in a popup above it.

        Returns False when the pin is not on the map, so the caller can fall
        back to its own viewer.
        """
        key = visual_feed_key(source, upstream_id)
        marker = self.visual_feed_markers_by_id.get(key)
        if not marker or not self.visual_feed_layer_visible:
            return False
        self._visual_feed_popup = (key, build_content)
        # On a phone the map is stacked above the camera list.
        container = self.map.getContainer()
        rect = container.getBoundingClientRect()
        if rect.bottom < 0 or rect.top > window.innerHeight:
            container.scrollIntoView({"behavior": "smooth", "block": "center"})
        latlng = marker.getLatLng()
        if self.map.getZoom() == zoom and self.map.getCenter().equals(latlng):
            self._show_visual_feed_popup()
        else:
            self._visual_feed_popup_flying = True
            self.map.once("moveend", self._on_visual_feed_fly_end)
            self.map.flyTo(latlng, zoom)
        return True

    def _on_visual_feed_fly_end(self, _event=None):
        self._visual_feed_popup_flying = False
        self._show_visual_feed_popup()

    def _show_visual_feed_popup(self):
        """Open the remembered popup on the camera's current marker."""
        popup = self._visual_feed_popup
        if popup is None:
            return
        key, build_content = popup
        marker = self.visual_feed_markers_by_id.get(key)
        if not marker or not self.visual_feed_layer_visible:
            self._visual_feed_popup = None
            return
        marker.bindPopup(build_content(), VISUAL_FEED_POPUP_OPTIONS)
        marker.once(
            "popupclose",
            lambda _event: self._on_visual_feed_popup_close(marker, popup),
        )
        marker.openPopup()

    def _on_visual_feed_popup_close(self, marker, popup):
        # Unbind so a later pin click still opens the full viewer.
        marker.unbindPopup()
        # Forget the popup only when the user closed this one, not when a
        # marker refresh or a newer popup replaced it.
        if not self._replacing_visual_feed_layer and self._visual_feed_popup is popup:
            self._visual_feed_popup = None

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
        pin_w, pin_h = USER.pin
        pin_icon = self._pin_icon(
            USER,
            f'<div style="filter:drop-shadow(0 2px 4px rgba(0,0,0,0.35));"><svg style="display: block;" width="{pin_w}" height="{pin_h}" viewBox="0 0 30 40" preserveAspectRatio="xMidYMax meet"><path d="M15 0C6.7 0 0 6.7 0 15c0 10.5 13.2 23.7 14 24.5.5.5 1.3.5 1.8 0C16.8 38.7 30 25.5 30 15 30 6.7 23.3 0 15 0z" fill="#dc2626"/><circle cx="15" cy="15" r="6" fill="#fff"/></svg></div>',
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

    def fly_to_user(self, on_found=None, on_error=None):
        self.map.locate()

        def on_location_found(e):
            self.user_coord = (e.latlng.lat, e.latlng.lng)

            self.map.flyTo(self.user_coord, 16)

            my_location_icon = self._pin_icon(
                MY_LOCATION,
                f'<div style="filter:drop-shadow(0 2px 4px rgba(0,0,0,0.35));"><i class="ph-fill ph-map-pin text-brand-600 block" style="font-size: {MY_LOCATION.pin[1]}px; line-height: 1;"></i></div>',
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
            if on_found:
                on_found(self.user_coord[0], self.user_coord[1])

        def on_location_error(e):
            self.map.off("locationfound", on_location_found)
            self.map.off("locationerror", on_location_error)
            if on_error:
                on_error(e)

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

    # Waterways from songkhla_basins.geojson, styled by OSM fclass (#67).
    # Light cyan reads on the grey basemap (river 3.2:1 against #808080).
    # Streams and drains are the bulk of the 807 lines, so they only appear
    # from zoom 11, where they no longer blur into a mesh.
    RIVER_STYLES = {
        "river": {"color": "#a5f3fc", "weight": 3.0, "opacity": 1.0, "dash": ""},
        "canal": {"color": "#7dd3fc", "weight": 2.0, "opacity": 1.0, "dash": ""},
        "stream": {"color": "#7dd3fc", "weight": 1.1, "opacity": 0.75, "dash": ""},
        "drain": {"color": "#7dd3fc", "weight": 1.0, "opacity": 0.75, "dash": "3 3"},
    }
    RIVER_DETAIL_ZOOM = 11
    RIVER_HIGHLIGHT = "#ecfeff"

    def river_style(self, fclass, zoom):
        """Leaflet style for one waterway at a zoom level."""
        spec = self.RIVER_STYLES.get(fclass) or self.RIVER_STYLES["stream"]
        minor = fclass not in ("river", "canal")
        if minor and (zoom or 0) < self.RIVER_DETAIL_ZOOM:
            # Weight 0 also removes the hit area, so hidden streams can't be
            # clicked by accident.
            return {
                "weight": 0,
                "opacity": 0,
                "fillOpacity": 0,
                "className": "river-line",
            }
        scale = 1.4 if (zoom or 0) >= 14 else (1.2 if (zoom or 0) >= 12 else 1.0)
        return {
            "color": spec["color"],
            "weight": round(spec["weight"] * scale, 2),
            "opacity": spec["opacity"],
            "dashArray": spec["dash"],
            "fillOpacity": 0,
            "className": "river-line",
        }

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
            return self.river_style(
                get_val(properties, "fclass", None), self.map.getZoom()
            )

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
                target_layer.setStyle(
                    {"weight": 5, "color": self.RIVER_HIGHLIGHT, "opacity": 1.0}
                )
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

        def on_zoom(_event=None):
            rivers = self.shapes.get("rivers")
            if not rivers:
                return
            rivers.setStyle(style)
            selected = self._selected_river
            if selected and rivers.hasLayer(selected):
                selected.setStyle(
                    {"weight": 5, "color": self.RIVER_HIGHLIGHT, "opacity": 1.0}
                )

        if not getattr(self, "_river_zoom_bound", False):
            self.map.on("zoomend", on_zoom)
            self._river_zoom_bound = True

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
