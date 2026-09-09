from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
import json
from pathlib import Path

router = APIRouter()


@router.get("/basins")
def get_basin_geojson():
    try:

        geojson_path = (
            Path(__file__).resolve().parents[3]
            / "web"
            / "static"
            / "resources"
            / "songkhla_basins.geojson"
        )

        if not geojson_path.exists():
            raise HTTPException(status_code=404, detail="File not found")

        with geojson_path.open("r", encoding="utf-8") as f:
            geojson_data = json.load(f)

        return JSONResponse(content=geojson_data)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
