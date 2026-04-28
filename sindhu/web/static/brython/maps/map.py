from browser import alert, window


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

        def navi(pos):
            self.user_coord = (pos.coords.latitude, pos.coords.longitude)
            self.user_mark = (
                self.leaflet.marker(
                    self.user_coord,
                    {"icon": self.get_icon("my_location"), "zIndexOffset": 1000},
                )
                .addTo(self.map)
                .bindPopup("ต่ำแหน่งของคุณ")
            )

        def nonavi(error):
            alert("Your browser doesn't support geolocation")

        # window.navigator.geolocation.getCurrentPosition(
        #     navi, nonavi
        # )  # set user's current location on map(success, error)

        self.leaflet.control.layers(self.base_maps).addTo(self.map)

    def __del__(self):
        self.map.remove()

    def fly_to_user(self):
        self.map.locate()

        def on_location_found(e):
            self.user_coord = (e.latlng.lat, e.latlng.lng)

            self.map.flyTo(self.user_coord, 16)

            if hasattr(self, "user_mark") and self.user_mark:
                if not isinstance(self.user_mark, list):
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

        def on_location_error(e):
            alert(f"ไม่สามารถระบุตำแหน่งได้: {e.message}")

        # ผูกเหตุการณ์
        self.map.on("locationfound", on_location_found)
        self.map.on("locationerror", on_location_error)

    # def fly_to_user(self):
    #     self.map.flyTo(self.user_coord, 16)
    #     self.user_mark.openPopup()

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

    def set_shape_with_key(self, data, key):  # can set more than one shape
        if not data or len(data) == 0:
            return

        def style(feature):
            default_color = "#C6C6C6"
            properties = dict(feature.properties)
            if feature.geometry.type == "Point":
                default_color = "#FF6600"
            fill_color = properties.get("fill", properties.get("color", default_color))
            fill_opacity = properties.get("fill_opa", 0.3)

            stroke_w = properties.get("stroke_w", 1)
            stroke_opacity = properties.get("stroke_opa", 1)
            stroke_color = properties.get("stroke", default_color)
            return {
                "fillColor": fill_color,
                "fillOpacity": fill_opacity,
                "color": stroke_color,
                "weight": stroke_w,
                "opacity": stroke_opacity,
            }

        def on_each_feature(feature, layer):  # feature = layer.feature
            def zoom_to_feature(e):
                # print(e.target.feature.properties.__dict__)
                if (
                    self.map.getZoom() < 11
                    and e.target.feature.geometry.type != "Point"
                ):
                    self.map.fitBounds(e.target.getBounds())

            def reset_highlight(e):
                for key in self.shapes:
                    if self.shapes[key].hasLayer(layer):
                        self.shapes[key].resetStyle(e.target)

            def highlight_feature(e):
                layer = e.target

                layer.setStyle({"weight": 2, "fillOpacity": 0.7})

            popup_detail = ""
            date_txt = {"th": "วันที่", "en": "Date"}
            zone_txt = {"th": "พื้นที่", "en": "Zone"}

            if name := dict(feature.properties).get("Name"):
                popup_detail += f"<div>{name}</div>"
            if des_th := dict(feature.properties).get("DES_TH"):
                popup_detail += f"<div>{des_th}</div>"
            if fire_date := dict(feature.properties).get("DATE"):
                popup_detail += (
                    f"<div><b>{date_txt[self.lang_code]}</b> : {fire_date}</div>"
                )
            if water_zone := dict(feature.properties).get("Zone"):
                popup_detail += (
                    f"<div><b>{zone_txt[self.lang_code]}</b> : {water_zone}</div>"
                )
            if acq_date := dict(feature.properties).get("ACQ_DATE"):  # fire spot
                popup_detail += (
                    f"<div><b>{date_txt[self.lang_code]}</b> : {acq_date}</div>"
                )

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
