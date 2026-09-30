"""Build the small map layers in seed/ from the raw land data.

    uv run --with shapely python scripts/build_geo.py

Writes seed/streets.geojson (named OSM streets, merged by name, simplified),
seed/land_railway.geojson (OSM landuse=railway ways) and
seed/land_national_highways.geojson (National Highways RedLine polygons that
touch Liverpool). Needs seed/wards.geojson for the city outline.

The outputs are in the repository; the raw inputs aren't. To rebuild, put these in data/raw/land/ (sources in NOTICE.md):
osm_named_highways_liverpool.json and osm_landuse_railway_liverpool.json (Overpass API JSON), and
nh_redline_liverpool_bbox.geojson (National Highways Highway Boundary, clipped to a box around Liverpool).
"""

import json
from pathlib import Path

from shapely.geometry import LineString, Polygon, mapping, shape
from shapely.ops import linemerge, unary_union

APP = Path(__file__).resolve().parents[1]
SEED = APP / "seed"
LAND = APP / "data" / "raw" / "land"


def rnd(c, dp=5):
    if isinstance(c, (list, tuple)) and c and isinstance(c[0], (int, float)):
        return [round(c[0], dp), round(c[1], dp)]
    return [rnd(x, dp) for x in c]


def feature(geom, props):
    g = mapping(geom)
    return {
        "type": "Feature",
        "properties": props,
        "geometry": {"type": g["type"], "coordinates": rnd(g["coordinates"])},
    }


def save(name, feats, about):
    fc = {"type": "FeatureCollection", "_about": about, "features": feats}
    (SEED / name).write_text(json.dumps(fc, separators=(",", ":")))
    print(name, len(feats), "features,", round((SEED / name).stat().st_size / 1024), "KB")


city = unary_union([shape(f["geometry"]) for f in json.load(open(SEED / "wards.geojson"))["features"]])
near_city = city.buffer(0.01)  # about 1 km

# Streets: drop footpaths and steps, merge each name's ways, simplify to about 4 m.
SKIP = {"footway", "cycleway", "path", "steps", "track", "construction", "services"}
by_name = {}
for w in json.load(open(LAND / "osm_named_highways_liverpool.json"))["elements"]:
    g = w.get("geometry") or []
    if len(g) < 2 or w["tags"].get("highway") in SKIP:
        continue
    by_name.setdefault(w["tags"]["name"], []).append(LineString([(p["lon"], p["lat"]) for p in g]))
streets = []
for name, lines in sorted(by_name.items()):
    geom = linemerge(lines).simplify(0.00004, preserve_topology=False)
    streets.append(feature(geom, {"name": name}))
save(
    "streets.geojson",
    streets,
    "Named streets in Liverpool from OpenStreetMap (ODbL, © OpenStreetMap contributors), merged by name and simplified.",
)

# Railway land: OSM landuse=railway ways (the two multipolygon relations carry no geometry in the export).
rail = []
for e in json.load(open(LAND / "osm_landuse_railway_liverpool.json"))["elements"]:
    if e["type"] != "way" or len(e.get("geometry") or []) < 4:
        continue
    poly = Polygon([(p["lon"], p["lat"]) for p in e["geometry"]]).buffer(0)
    if poly.is_empty:
        continue
    rail.append(
        feature(
            poly.simplify(0.00003),
            {"source": "OSM landuse=railway", "osm_id": e["id"], "operator": e.get("tags", {}).get("operator")},
        )
    )
save(
    "land_railway.geojson",
    rail,
    "Railway land in Liverpool from OpenStreetMap landuse=railway (ODbL). A stand-in: Network Rail's own boundary is not open.",
)

# National Highways RedLine: keep polygons within about 1 km of the city.
nh = []
for f in json.load(open(LAND / "nh_redline_liverpool_bbox.geojson"))["features"]:
    g = shape(f["geometry"]).buffer(0)
    if g.intersects(near_city):
        nh.append(
            feature(
                g.simplify(0.00003),
                {"source": "National Highways Operational Highway Boundary (RedLine), indicative only"},
            )
        )
save(
    "land_national_highways.geojson",
    nh,
    "National Highways RedLine boundary near Liverpool (© Crown copyright 2026, OS AC0000827444; indicative only, licence custom).",
)
