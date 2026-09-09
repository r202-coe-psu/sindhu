from browser import window, ajax
import json


def on_ajax_complete(req):
    if req.status == 200 or req.status == 0:
        geojson_data = json.loads(req.text)

        river_style = {"color": "#3388ff", "weight": 2, "opacity": 0.8}

        window.L.geoJSON(geojson_data, {"style": river_style}).addTo(window.map)
        print("[Map:Basin] River basins loaded successfully")
    else:
        print(f"[Map:Basin] Failed to load river basins (status: {req.status})")


print("[Map:Basin] Fetching river basins from API...")
req = ajax.Ajax()
req.bind("complete", on_ajax_complete)
req.open("GET", "/v1/basins", True)
req.send()
