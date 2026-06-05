from browser import window, ajax
import json

def on_ajax_complete(req):
    if req.status == 200 or req.status == 0:
        geojson_data = json.loads(req.text)

        river_style = {
            "color": "#3388ff",
            "weight": 2,
            "opacity": 0.8
        }
        
        window.L.geoJSON(geojson_data, {"style": river_style}).addTo(window.map)
        print(" โหลดข้อมูลแม่น้ำลงแผนที่สำเร็จ")
    else:
        print(f" โหลดข้อมูลล้มเหลว Status: {req.status}")

print("กำลังโหลดข้อมูลแม่น้ำ...")
req = ajax.Ajax()
req.bind('complete', on_ajax_complete)
req.open('GET', 'http://127.0.0.1:8000/v1/basins', True) 
req.send()