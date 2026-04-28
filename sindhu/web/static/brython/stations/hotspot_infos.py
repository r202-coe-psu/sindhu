SATELLITE_NAMES = ["modis", "noaa-20", "noaa-21", "suomi"]
HTML_HOTSPOT_SENSOR_NAMES = dict(
    confidence="Confidence",
    daynight="DAYNIGHT",
    frp="FRP",
    satellite="Satellite",
    scan="Scan",
    sensor_type="Sensor Type",
    track="Track",
    version="Version",
)
HTML_HOTSPOT_LEGENDS = dict(
    modis_hotspots=[
        {"DES": "0-29", "fill": "#f1a7a7"},
        {"DES": "30-79", "fill": "#ea7b7b"},
        {"DES": "80-100", "fill": "#dd3131"},
    ],
    viir_hotspots=[
        {"DES": "low", "fill": "#ffc299"},
        {"DES": "nominal", "fill": "#ff944d"},
        {"DES": "high", "fill": "#ff6600"},
    ],
)

HTML_HOTSPOT_LEGEND_TITLES = dict(
    modis_hotspots="Modis Hotspot Confidence",
    viir_hotspots="VIIRS Hotspot Confidence",
)
