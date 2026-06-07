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
        self.icon_types = {"default": "fire", "my_location": "my_location"}

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
        reset_btn.html = '<i class="ph ph-arrow-counter-clockwise"></i> แสดงสถานีทั้งหมด'
        reset_btn.style.cssText = "background:white;color:#2563eb;border:1px solid #e5e7eb;border-radius:9999px;padding:6px 16px;font-size:13px;cursor:pointer;box-shadow:0 2px 6px rgba(0,0,0,0.15);display:flex;align-items:center;gap:6px;"
        reset_div <= reset_btn
        map_container <= reset_div
        self._reset_btn_container = reset_div

        def on_reset(e):
            e.preventDefault()
            e.stopPropagation()
            self.remove_pin()
            self.clear_zone_display()
            if self._on_pin_off_callback:
                self._on_pin_off_callback()

        reset_btn.bind("click", on_reset)

        self.map.on("click", self._handle_map_click)

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
        if hasattr(self, "user_mark") and self.user_mark and not isinstance(self.user_mark, list):
            self.user_mark.setLatLng(self.user_coord)
        else:
            pin_icon = self.leaflet.divIcon({
                "className": "",
                "html": '<div style="filter:drop-shadow(0 2px 4px rgba(0,0,0,0.35));"><svg width="30" height="40" viewBox="0 0 30 40"><path d="M15 0C6.7 0 0 6.7 0 15c0 10.5 13.2 23.7 14 24.5.5.5 1.3.5 1.8 0C16.8 38.7 30 25.5 30 15 30 6.7 23.3 0 15 0z" fill="#dc2626"/><circle cx="15" cy="15" r="6" fill="#fff"/></svg></div>',
                "iconSize": [30, 40],
                "iconAnchor": [15, 40],
                "popupAnchor": [0, -36],
            })
            self.user_mark = (
                self.leaflet.marker(
                    self.user_coord,
                    {"icon": pin_icon, "zIndexOffset": 1000},
                )
                .addTo(self.map)
                .bindPopup("ตำแหน่งที่เลือก")
            )
        if self._reset_btn_container:
            self._reset_btn_container.style.display = "block"

    def remove_pin(self):
        if hasattr(self, "user_mark") and self.user_mark and not isinstance(self.user_mark, list):
            self.map.removeLayer(self.user_mark)
            self.user_mark = []
            self.user_coord = None
        if self._reset_btn_container:
            self._reset_btn_container.style.display = "none"

    def clear_zone_display(self):
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

        self.zone_layer = self.leaflet.geoJson(
            zone_geojson,
            {
                "style": lambda feature: {
                    "fillColor": "#3b82f6",
                    "fillOpacity": 0.15,
                    "color": "#2563eb",
                    "weight": 2,
                    "dashArray": "5, 5",
                },
            },
        ).addTo(self.map)

    def show_station_paths(self, user_latlng, stations):
        for line in self.station_lines:
            self.map.removeLayer(line)
        self.station_lines = []
        for marker in self.station_markers:
            self.map.removeLayer(marker)
        self.station_markers = []

        first = True
        for station in stations:
            code = station.get("code")
            if not code or code not in self.metric_markers_by_code:
                continue

            marker = self.metric_markers_by_code[code]
            station_latlng = marker.getLatLng()

            if first:
                style = {"color": "#dc2626", "weight": 2.5, "opacity": 0.8, "dashArray": "6, 4"}
                first = False
            else:
                style = {"color": "#3b82f6", "weight": 1.5, "opacity": 0.4, "dashArray": "6, 4"}

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

            if hasattr(self, "user_mark") and self.user_mark and not isinstance(self.user_mark, list):
                self.user_mark.setLatLng(self.user_coord)
            else:
                self.user_mark = (
                    self.leaflet.marker(
                        self.user_coord,
                        {
                            "icon": self.get_icon("my_location"),
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
            stroke_w = get_val(properties, "stroke-width", get_val(properties, "stroke_w", 2))
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
                if "rivers" in self_ref.shapes and self_ref.shapes["rivers"].hasLayer(prev):
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
                    display_name = "เส้นทางน้ำ (ไม่ระบุชื่อ)" if lang == "th" else "Unnamed Waterway"
                popup_detail += f"<div>{display_name}</div>"

            if popup_detail:
                layer.bindPopup(popup_detail)

            layer.on({
                "click": zoom_to_feature,
            })

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

    def get_icon(self, type="default"):
        return self.leaflet.icon(
            dict(
                iconUrl=f"/static/resources/marks/{self.icon_types[type]}.svg",
                iconSize=[35, 35],
                iconAnchor=[22, 40],
                popupAnchor=[0, -30],
            )
        )
    
    def load_river_basins(self, api_url):
        """ฟังก์ชันสำหรับดึงข้อมูล GeoJSON ลุ่มน้ำจาก API และวาดลงแผนที่"""
        
        def on_complete(req):
            if req.status == 200 or req.status == 0:
                geojson_data = json.loads(req.text)
                
                # กำหนดสไตล์เส้นแม่น้ำ
                river_style = {
                    "color": "#3388ff", # สีฟ้า
                    "weight": 2,        # ความหนาของเส้น
                    "opacity": 0.8      # ความโปร่งใส
                }
                
                # ใช้ self.leaflet.geoJson วาดเส้น และเก็บไว้ใน self.shapes
                self.shapes['river_basins'] = self.leaflet.geoJson(
                    geojson_data, 
                    {"style": river_style}
                ).addTo(self.map)
                
                print("🎉 โหลดข้อมูลเส้นแม่น้ำสงขลาลงแผนที่สำเร็จ!")
            else:
                print(f"❌ โหลดข้อมูล GeoJSON ล้มเหลว (Status: {req.status})")

        print("กำลังดึงข้อมูลแม่น้ำจาก API...")
        req = ajax.Ajax()
        req.bind('complete', on_complete)
        req.open('GET', f'{api_url}/v1/basins', True) 
        req.send()
