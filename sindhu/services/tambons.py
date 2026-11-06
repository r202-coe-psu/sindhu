import datetime
import json
import uuid

from loguru import logger
from pymongo import UpdateOne
from shapely.geometry import shape
from shapely.ops import unary_union
from shapely.validation import make_valid

from sindhu import models
from sindhu.schemas.tambons import TambonRef, coerce_tambon_ref

def is_reference_zone(zone) -> bool:
    """Reference boundaries are map context only, never flood zones.

    A zone is a reference when zone_kind is "reference" or its metadata role
    is "reference_boundary".
    """
    if getattr(zone, "zone_kind", None) == "reference":
        return True
    metadata = getattr(zone, "metadata", None) or {}
    return metadata.get("role") == "reference_boundary"


def is_flood_zone(zone) -> bool:
    return not is_reference_zone(zone)


def _clean_geometry(geom_dict):
    """Return a valid areal shapely geometry or None."""
    if not isinstance(geom_dict, dict):
        return None
    if geom_dict.get("type") not in ("Polygon", "MultiPolygon"):
        return None
    try:
        geom = shape(geom_dict)
    except Exception:
        return None
    if geom.is_empty:
        return None
    if not geom.is_valid:
        try:
            geom = make_valid(geom)
        except Exception:
            geom = geom.buffer(0)
        if not geom.is_valid:
            geom = geom.buffer(0)
    if geom.is_empty or geom.geom_type not in ("Polygon", "MultiPolygon"):
        # make_valid may return a GeometryCollection; keep only areal parts.
        parts = [
            g
            for g in getattr(geom, "geoms", [])
            if g.geom_type in ("Polygon", "MultiPolygon") and not g.is_empty
        ]
        if not parts:
            return None
        geom = unary_union(parts)
    if geom.is_empty or geom.area <= 0:
        return None
    return geom


def parse_tambon_geojson(fc, code_prop, name_prop, amphoe_prop=None):
    """Parse a GeoJSON FeatureCollection into tambon dicts. Pure function.

    Returns {"tambons": [{code, name_th, amphoe_th, boundary}], "skipped": int,
    "warnings": [str]}. Features without a code or name, with a bad geometry,
    or repeating an earlier code are skipped with a warning.
    """
    tambons, warnings, skipped, seen = [], [], 0, set()
    features = fc.get("features") if isinstance(fc, dict) else None
    if not isinstance(features, list):
        return {
            "tambons": [],
            "skipped": 0,
            "warnings": ["ไฟล์ไม่ใช่ GeoJSON FeatureCollection"],
        }

    def _text(v):
        return str(v).strip() if v is not None else ""

    for idx, feature in enumerate(features):
        props = (feature or {}).get("properties") or {}
        code = _text(props.get(code_prop))
        name = _text(props.get(name_prop))
        if not code:
            skipped += 1
            warnings.append(f"ฟีเจอร์ที่ {idx + 1}: ไม่มีรหัสตำบล ({code_prop})")
            continue
        if not name:
            skipped += 1
            warnings.append(f"ฟีเจอร์ที่ {idx + 1} ({code}): ไม่มีชื่อตำบล ({name_prop})")
            continue
        if code in seen:
            skipped += 1
            warnings.append(f"ฟีเจอร์ที่ {idx + 1} ({code}): รหัสซ้ำ ใช้ฟีเจอร์แรก")
            continue

        geom = _clean_geometry((feature or {}).get("geometry"))
        if geom is None:
            skipped += 1
            warnings.append(f"ฟีเจอร์ที่ {idx + 1} ({name}): geometry ไม่ถูกต้อง")
            continue

        seen.add(code)
        amphoe = _text(props.get(amphoe_prop)) if amphoe_prop else ""
        tambons.append(
            {
                "code": code,
                "name_th": name,
                "amphoe_th": amphoe or None,
                "boundary": _to_plain(geom),
            }
        )
    return {"tambons": tambons, "skipped": skipped, "warnings": warnings}


def _to_plain(geom):
    """GeoJSON dict with lists (not tuples) so it is Mongo/JSON friendly."""
    return json.loads(json.dumps(geom.__geo_interface__))


def clip_to_area(tambons, area_geojson):
    """Keep tambons intersecting the area. Returns (kept, dropped_count).

    area_geojson None means no clipping. Pure function.
    """
    if area_geojson is None:
        return list(tambons), 0
    area = _clean_geometry(area_geojson)
    if area is None:
        return list(tambons), 0
    kept = []
    for t in tambons:
        g = _clean_geometry(t.get("boundary"))
        if g is not None and g.intersects(area):
            kept.append(t)
    return kept, len(tambons) - len(kept)


def assign_tambons_to_zones(tambons, zones, min_overlap=0.05):
    """Map each zone id to its TambonRef dicts, sorted by code.

    tambons: [{"code", "name_th", "amphoe_th", "boundary"}]
    zones: [{"id": str, "boundary": geojson}]
    A tambon belongs to a zone when intersection area / tambon area >=
    min_overlap; it may belong to several zones. Every zone id is a key, even
    with no tambons. Pure function.
    """
    result = {str(z["id"]): {} for z in zones}
    zone_geoms = [(str(z["id"]), _clean_geometry(z.get("boundary"))) for z in zones]

    for t in tambons:
        tg = _clean_geometry(t.get("boundary"))
        if tg is None:
            continue
        for zid, zg in zone_geoms:
            if zg is None or not tg.intersects(zg):
                continue
            if tg.intersection(zg).area / tg.area >= min_overlap:
                result[zid][t["code"]] = coerce_tambon_ref(t)

    return {zid: [refs[c] for c in sorted(refs)] for zid, refs in result.items()}


def diff_tambons(current, new):
    """(added, removed) ref lists comparing by code. Pure function."""
    current_by_code = {r["code"]: r for r in map(coerce_tambon_ref, current)}
    new_by_code = {r["code"]: r for r in map(coerce_tambon_ref, new)}
    added = [new_by_code[c] for c in sorted(new_by_code) if c not in current_by_code]
    removed = [
        current_by_code[c] for c in sorted(current_by_code) if c not in new_by_code
    ]
    return added, removed


def _union_geojson(geoms):
    geoms = [g for g in geoms if g is not None]
    if not geoms:
        return None
    return _to_plain(unary_union(geoms))


def _zone_ref_dicts(zone):
    return [coerce_tambon_ref(t) for t in zone.tambons]


async def latest_batch_id():
    """batch_id of the newest tambon (two batches coexist during a swap)."""
    newest = await models.Tambon.find_all().sort("-_id").limit(1).to_list()
    return newest[0].batch_id if newest else None


async def list_latest_tambons():
    batch_id = await latest_batch_id()
    if batch_id is None:
        return []
    tambons = await models.Tambon.find({"batch_id": batch_id}).to_list()
    return sorted(tambons, key=lambda t: t.code)


async def import_tambons(request, dry_run=None, min_overlap=0.05):
    """Import a tambon GeoJSON described by an ImportTambonRequest.

    dry_run defaults to request.dry_run. A dry run writes nothing.
    """
    if dry_run is None:
        dry_run = request.dry_run

    # 1. Compute everything first.
    parsed = parse_tambon_geojson(
        request.feature_collection,
        request.code_property,
        request.name_property,
        request.amphoe_property,
    )

    zones = await models.Zone.find({"status": {"$ne": "delete"}}).to_list()
    flood_zones = [z for z in zones if is_flood_zone(z)]
    reference_zones = [z for z in zones if not is_flood_zone(z)]

    # Clip to the reference zone(s); with none, to the flood zones.
    area_zones = reference_zones or flood_zones
    area = _union_geojson(
        [_clean_geometry(z.boundary.model_dump()) for z in area_zones]
    )
    tambons, clipped_out = clip_to_area(parsed["tambons"], area)

    assignment = assign_tambons_to_zones(
        tambons,
        [{"id": str(z.id), "boundary": z.boundary.model_dump()} for z in flood_zones],
        min_overlap,
    )
    for z in reference_zones:
        assignment[str(z.id)] = []

    changes = {}
    for z in zones:
        added, removed = diff_tambons(z.tambons, assignment.get(str(z.id), []))
        if added or removed:
            changes[str(z.id)] = {
                "zone_name": z.name_th or z.name,
                "added": added,
                "removed": removed,
            }

    result = {
        "dry_run": dry_run,
        "imported": len(tambons),
        "skipped": parsed["skipped"],
        "clipped_out": clipped_out,
        "warnings": parsed["warnings"],
        "zones": assignment,
        "changes": changes,
    }
    if dry_run:
        return result

    zone_ids_by_code = {}
    for zid, refs in assignment.items():
        for r in refs:
            zone_ids_by_code.setdefault(r["code"], []).append(zid)

    # 2. Insert the new batch alongside the old one.
    batch_id = uuid.uuid4().hex
    docs = [
        models.Tambon(
            code=t["code"],
            name_th=t["name_th"],
            amphoe_th=t["amphoe_th"],
            boundary=t["boundary"],
            zone_ids=zone_ids_by_code.get(t["code"], []),
            batch_id=batch_id,
        )
        for t in tambons
    ]
    try:
        if docs:
            await models.Tambon.insert_many(docs)
    except Exception:
        await _delete_batch(batch_id)
        raise

    # 3-5. Snapshot, update every zone in one ordered bulk write, and on
    # failure restore the snapshot and drop the new batch. Standalone MongoDB
    # has no transactions, so this compensating path is the default.
    snapshot = {z.id: (_zone_ref_dicts(z), z.updated_date) for z in zones}
    now = datetime.datetime.now()
    collection = models.Zone.get_pymongo_collection()
    ops = [
        UpdateOne(
            {"_id": z.id},
            {
                "$set": {
                    "tambons": [
                        TambonRef(**r).model_dump() for r in assignment[str(z.id)]
                    ],
                    "updated_date": now,
                }
            },
        )
        for z in zones
    ]
    try:
        if ops:
            await collection.bulk_write(ops, ordered=True)
    except Exception:
        try:
            if snapshot:
                await collection.bulk_write(
                    [
                        UpdateOne(
                            {"_id": zid},
                            {"$set": {"tambons": refs, "updated_date": updated}},
                        )
                        for zid, (refs, updated) in snapshot.items()
                    ],
                    ordered=True,
                )
        except Exception:
            logger.exception("Failed to restore zone tambons after failed import")
        await _delete_batch(batch_id)
        raise

    # 6. Only now retire the old batches.
    await models.Tambon.find({"batch_id": {"$ne": batch_id}}).delete()
    return result


async def _delete_batch(batch_id):
    try:
        await models.Tambon.find({"batch_id": batch_id}).delete()
    except Exception:
        logger.exception("Failed to delete tambon batch {}", batch_id)


async def sync_tambon_zone_links(zone_id, before, after):
    """Keep Tambon.zone_ids in step with a manual edit of Zone.tambons.

    Only the newest batch is touched.
    """
    before_codes = {coerce_tambon_ref(t)["code"] for t in before}
    after_codes = {coerce_tambon_ref(t)["code"] for t in after}
    added = sorted(after_codes - before_codes)
    removed = sorted(before_codes - after_codes)
    if not added and not removed:
        return
    batch_id = await latest_batch_id()
    if batch_id is None:
        return
    collection = models.Tambon.get_pymongo_collection()
    zid = str(zone_id)
    if added:
        await collection.update_many(
            {"batch_id": batch_id, "code": {"$in": added}},
            {"$addToSet": {"zone_ids": zid}},
        )
    if removed:
        await collection.update_many(
            {"batch_id": batch_id, "code": {"$in": removed}},
            {"$pull": {"zone_ids": zid}},
        )


def tambon_summary(t, include_geometry=False):
    d = {
        "code": t.code,
        "name_th": t.name_th,
        "amphoe_th": t.amphoe_th,
        "zone_ids": list(t.zone_ids),
    }
    if include_geometry:
        d["boundary"] = t.boundary
    return d


async def find_tambon_by_location(longitude: float, latitude: float):
    batch_id = await latest_batch_id()
    if batch_id is None:
        return None
    point = {"type": "Point", "coordinates": [longitude, latitude]}
    tambon = await models.Tambon.find_one(
        {
            "batch_id": batch_id,
            "boundary": {"$geoIntersects": {"$geometry": point}},
        }
    )
    return tambon_summary(tambon) if tambon else None
