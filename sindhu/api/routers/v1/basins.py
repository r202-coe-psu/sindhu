from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
import json
import os

router = APIRouter()

@router.get("/basins")
def get_basin_geojson():
    try:

        geojson_path = "sindhu/web/static/data/songkhla_basins.geojson"
        
        if not os.path.exists(geojson_path):
             raise HTTPException(status_code=404, detail="File not found")

        with open(geojson_path, 'r', encoding='utf-8') as f:
            geojson_data = json.load(f)
            
        return JSONResponse(content=geojson_data)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))