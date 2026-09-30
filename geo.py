"""Ward, street and land lookups for a point. Loads seed GeoJSON if present, degrades to None if not.

Geometry is projected to local planar metres (equirectangular about Liverpool), which is accurate to well under
1% across the city: plenty for 20 m railway buffers and 80 m street snaps.
"""

from __future__ import annotations

import json
import math
import threading
from functools import lru_cache

from shapely import STRtree
from shapely.geometry import Point, shape
from shapely.ops import transform

from common import COUNCIL_NAME, log, resolve

LAT0, LON0 = 53.41, -2.98
KX = 111320.0 * math.cos(math.radians(LAT0))
KY = 110574.0

_lock = threading.Lock()
_layers: dict[str, tuple[float, object]] = {}


def to_xy(lon, lat):
    return (lon - LON0) * KX, (lat - LAT0) * KY


def _proj(x, y, z=None):
    # shapely.ops.transform passes arrays of lon, lat
    return (x - LON0) * KX, (y - LAT0) * KY


def pt(lat, lon) -> Point:
    return Point(*to_xy(lon, lat))


def _load(name: str):
    """Return (geoms, props, tree) for a seed GeoJSON, cached on mtime; None if missing or broken."""
    path = resolve("seed", name)
    if path is None:
        return None
    mtime = path.stat().st_mtime
    with _lock:
        hit = _layers.get(name)
        if hit and hit[0] == mtime:
            return hit[1]
        try:
            gj = json.loads(path.read_text())
            feats = gj.get("features", []) if isinstance(gj, dict) else []
            geoms, props = [], []
            for f in feats:
                try:
                    g = shape(f["geometry"])
                    if g.is_empty:
                        continue
                    g = transform(_proj, g)
                    if not g.is_valid:
                        g = g.buffer(0)
                    geoms.append(g)
                    props.append(f.get("properties") or {})
                except Exception:
                    continue
            layer = (geoms, props, STRtree(geoms) if geoms else None)
            log.info("loaded %s: %d features", name, len(geoms))
        except Exception as e:
            log.error("could not load %s: %s", name, e)
            layer = None
        _layers[name] = (mtime, layer)
        return layer


def ward_for(lat, lon) -> str | None:
    layer = _load("wards.geojson")
    if not layer or layer[2] is None:
        return None
    geoms, props, tree = layer
    p = pt(lat, lon)
    for i in tree.query(p, predicate="intersects"):
        name = props[i].get("ward") or props[i].get("name") or props[i].get("WD24NM") or props[i].get("wd_name")
        if name:
            return name
    # just outside every polygon (e.g. on the river edge): nearest ward within 300 m
    idx, dist = tree.query_nearest(p, max_distance=300, return_distance=True)
    if len(idx):
        return props[int(idx[0])].get("ward") or props[int(idx[0])].get("name")
    return None


def street_for(lat, lon, max_m: float = 80) -> str | None:
    layer = _load("streets.geojson")
    if not layer or layer[2] is None:
        return None
    geoms, props, tree = layer
    p = pt(lat, lon)
    near = [(float(geoms[int(i)].distance(p)), int(i)) for i in tree.query(p.buffer(max_m))]
    near = sorted((d, i) for d, i in near if d <= max_m and props[i].get("name"))
    if not near:
        return None
    # at a junction (several streets within 3 m) prefer the longer street: usually the main road people name
    ties = [i for d, i in near if d <= near[0][0] + 3]
    return props[max(ties, key=lambda i: geoms[i].length)].get("name")


def distance_to_m(name: str, lat, lon) -> float | None:
    layer = _load(name)
    if not layer or layer[2] is None:
        return None
    geoms, props, tree = layer
    p = pt(lat, lon)
    i = tree.nearest(p)
    return float(geoms[int(i)].distance(p)) if i is not None else None


def inside(name: str, lat, lon) -> bool:
    layer = _load(name)
    if not layer or layer[2] is None:
        return False
    geoms, props, tree = layer
    return len(tree.query(pt(lat, lon), predicate="intersects")) > 0


def railway_distance_m(lat, lon) -> float | None:
    return distance_to_m("land_railway.geojson", lat, lon)


def in_national_highways(lat, lon) -> bool:
    return inside("land_national_highways.geojson", lat, lon)


CITY_AUTHORITY = COUNCIL_NAME


@lru_cache(maxsize=4096)
def _authority(lat5: float, lon5: float) -> str | None:
    layer = _load("lads_lcr.geojson")
    if not layer or layer[2] is None:
        return None
    geoms, props, tree = layer
    p = pt(lat5, lon5)
    for i in tree.query(p, predicate="intersects"):
        if props[int(i)].get("authority"):
            return props[int(i)]["authority"]
    # on the river edge or a simplified coastline: nearest authority within 300 m
    idx, _ = tree.query_nearest(p, max_distance=300, return_distance=True)
    return props[int(idx[0])].get("authority") if len(idx) else None


def authority_for(lat, lon) -> str:
    """Local authority for a point, from seed/lads_lcr.geojson (ONS LAD boundaries); the demo council if unknown."""
    try:
        return _authority(round(float(lat), 5), round(float(lon), 5)) or CITY_AUTHORITY
    except Exception:
        return CITY_AUTHORITY
