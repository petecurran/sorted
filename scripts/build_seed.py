"""Build the demo data from our own photos, relative to today, so the demo always looks current.

Writes:
  seed/history.json         two years of simulated past reports: repeat hotspots, repeats near earlier reports,
                            the June student move-out peak, more reports after weekends
  seed/demo_incidents.json  one case per photo in seed/photos, with a simulated place, date, resident's title and
                            history (open cases this week, booked ones last week, closed ones over the past months)
  seed/model_cache.json     the reading of each photo (seed/cases/labels.json), so the seed and the demo kit need no
                            model; uploading one of these photos returns its reading at once
  seed/photos_web/          smaller copies of the photos for phones (not in git)

Nothing here comes from real reports: places are points on real Liverpool streets (OpenStreetMap), and everything
else is simulated. The photos are AI-generated illustrations. scripts/start_server.sh runs this when FT_RESET=1.

Run from the repo root:  uv run python scripts/build_seed.py
"""

from __future__ import annotations

import bisect
import hashlib
import itertools
import json
import math
import random
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from PIL import Image
from shapely.geometry import shape

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))
sys.path.insert(0, str(APP / "scripts"))
from demo_places import GROWING, HOTSPOTS, KIT, KIT_SOURCES, MERGE_PLACE  # noqa: E402

import geo  # noqa: E402
from common import COUNCIL_NAME  # noqa: E402

SEED = APP / "seed"
PHOTOS = SEED / "photos"
rng = random.Random(2909)
NOW = datetime.now(UTC).replace(second=0, microsecond=0)
RULES = json.loads((APP / "content/triage_rules.json").read_text())
LABELS = {k: v for k, v in json.loads((SEED / "cases/labels.json").read_text()).items() if k.startswith("case_")}
CENTRE = (53.4084, -2.9916)
UNIVERSITIES = (53.4040, -2.9660)

# Who is in which part of the queue: (photo, hours ago). The rest are closed, spread over the past five months.
OPEN = [
    ("case_144", 1.6),
    ("case_135", 5),
    ("case_131", 20),
    ("case_087", 26),
    ("case_139", 30),
    ("case_133", 44),
    ("case_142", 52),
    ("case_130", 60),
    ("case_016", 70),
    ("case_138", 76),
    ("case_072", 84),
    ("case_141", 92),
    ("case_104", 100),
    ("case_128", 108),
]
BOOKED = [("case_129", 150), ("case_127", 170), ("case_134", 190), ("case_114", 210)]
PLACE = {"case_144": "Lodge Lane", "case_139": "merge", "case_087": "railway"}  # special places for open cases
PROSECUTE = {"case_089"}  # scrap metal trader: the return shows one prosecution


def iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def metres(lat1, lon1, lat2, lon2) -> float:
    return math.hypot((lon2 - lon1) * 111320 * math.cos(math.radians(lat1)), (lat2 - lat1) * 110540)


def jitter(lat, lon, sd_m):
    return (lat + rng.gauss(0, sd_m) / 110540, lon + rng.gauss(0, sd_m) / (111320 * math.cos(math.radians(lat))))


# ---- places: points on real streets, more of them nearer the centre -------------------------------------------
streets = []
for f in json.loads((SEED / "streets.geojson").read_text())["features"]:
    g = shape(f["geometry"])
    parts = [g] if g.geom_type == "LineString" else list(getattr(g, "geoms", []))
    for part in parts:
        if part.length > 0:
            streets.append((f["properties"].get("name") or "", part))
cum = list(itertools.accumulate(p.length for _, p in streets))


def street_point():
    """A point on a street inside the council's area, weighted towards the centre, with its street and ward."""
    while True:
        name, line = streets[bisect.bisect(cum, rng.random() * cum[-1])]
        p = line.interpolate(rng.random(), normalized=True)
        lat, lon = jitter(p.y, p.x, 4)
        if rng.random() > 1 / (1 + metres(lat, lon, *CENTRE) / 2500):
            continue
        ward = geo.ward_for(lat, lon)
        if ward and geo.authority_for(lat, lon) == COUNCIL_NAME:
            return lat, lon, name, ward


def near(lat, lon, sd_m=25):
    la, lo = jitter(lat, lon, sd_m)
    return la, lo, geo.street_for(la, lo) or "", geo.ward_for(la, lo) or geo.ward_for(lat, lon) or ""


def railway_point():
    """A street point within about 12 m of railway land, so the case goes to Network Rail."""
    for _ in range(40000):
        lat, lon, name, ward = street_point()
        d = geo.railway_distance_m(lat, lon)
        if d is not None and d < 12:
            return lat, lon, name, ward
    raise SystemExit("no street point found next to railway land")


# ---- when: two years of days, weighted by season, weekday and a slight rise over time ------------------------------
SEASON = {1: 1.1, 2: 0.9, 3: 0.95, 4: 1.0, 5: 1.05, 6: 1.5, 7: 1.25, 8: 1.2, 9: 1.05, 10: 1.0, 11: 0.95, 12: 1.1}
WEEKDAY = [1.3, 1.15, 1.0, 1.0, 0.95, 0.85, 0.8]  # Monday first: reports pile up after weekends
DAYS = list(range(1, 731))


def day_weight(back: int, student: bool = False) -> float:
    d = (NOW - timedelta(days=back)).date()
    s = SEASON[d.month] * (1.8 if student and d.month == 6 else 1.0)
    return s * WEEKDAY[d.weekday()] * (1 + 0.25 * (1 - back / 730))


def when(back_range=(1, 730), student=False) -> datetime:
    days = list(range(back_range[0], back_range[1] + 1))
    back = rng.choices(days, weights=[day_weight(b, student) for b in days])[0]
    return (NOW - timedelta(days=back)).replace(hour=rng.randint(7, 21), minute=rng.randint(0, 59))


# ---- 1. simulated past reports -------------------------------------------------------------------------------------
history = []


def add_history(lat, lon, street, ward, dt):
    history.append(
        {"lat": round(lat, 6), "lon": round(lon, 6), "date": dt.date().isoformat(), "ward": ward, "street": street}
    )


for name, lat, lon, recent, older in HOTSPOTS:
    for _ in range(recent):
        add_history(*near(lat, lon, 30), when((1, 90)))
    for _ in range(older):
        add_history(*near(lat, lon, 35), when((91, 730), student=name == "Picton Road"))
    if name in GROWING:
        for _ in range(3):
            add_history(*near(lat, lon, 25), when((1, 5)))
for _ in range(1100):
    lat, lon, street, ward = street_point()
    student = metres(lat, lon, *UNIVERSITIES) < 2000
    dt = when(student=student)
    add_history(lat, lon, street, ward, dt)
    for _ in range(rng.choices([0, 1, 2], weights=[72, 23, 5])[0]):  # repeats near an earlier report
        later = dt + timedelta(days=rng.randint(1, 21))
        if later < NOW - timedelta(days=1):
            add_history(*near(lat, lon, 15), later)
history.sort(key=lambda h: h["date"])
(SEED / "history.json").write_text(json.dumps(history, separators=(",", ":")))
print(f"history: {len(history)} simulated past reports, {history[0]['date']} to {history[-1]['date']}")


# ---- 2. the cases: one per photo -------------------------------------------------------------------------------------
def decision(lab: dict) -> str:
    wt, hz = lab["waste_type"], lab["hazards"]
    if lab["fly_tip"] == "no":
        return "not_a_fly_tip"
    if any(k in hz for k in ("chemical", "fuel")) or wt in RULES.get("specialist_waste_types", []):
        return "specialist"
    if wt in RULES.get("hold_waste_types", []):
        return "hold_for_officer"
    return "clear_now"


def model_for(lab: dict) -> dict:
    return {
        "fly_tip": lab["fly_tip"],
        "confidence": rng.randint(84, 97),
        "what_you_see": lab["what_you_see"],
        "size": lab["size"],
        "waste_type": lab["waste_type"],
        "land_type": lab["land_type"],
        "hazards": lab["hazards"],
        "decision": decision(lab),
        "reason": "",
        "seconds": 0,
        "model": "Demo data",
    }


TITLES = [
    ("fuel", "Fuel cans dumped"),
    ("scooter", "Broken e-scooter and rubbish dumped"),
    ("paint", "Paint tins and building rubbish dumped"),
    ("plasterboard", "Building rubble dumped"),
    ("rubble", "Building rubble dumped"),
    ("sand", "Sand and building waste dumped"),
    ("mattress", "Mattress dumped"),
    ("sofa", "Sofa dumped"),
    ("armchair", "Armchair and bags dumped"),
    ("fridge", "Fridge freezer dumped"),
    ("television", "Old TV and monitor dumped"),
    ("trolley", "Shopping trolley full of rubbish"),
    ("pallets", "Pallets dumped"),
    ("wardrobe", "Broken wardrobe left out"),
    ("drawers", "Broken furniture left out"),
    ("bed base", "Bed base left out"),
    ("gazebo", "Broken gazebo dumped"),
    ("footstool", "Footstool left out"),
    ("scrap", "Scrap metal dumped"),
    ("trade bins", "Rubbish piled round the trade bins"),
    ("cuttings", "Garden waste dumped"),
    ("garden", "Garden waste dumped"),
    ("carpet", "Carpet and bags dumped"),
    ("bags", "Bags of rubbish dumped"),
]


def title_for(lab: dict) -> str:
    if lab["fly_tip"] == "no":
        return "Bins left out in the back lane"
    s = lab["what_you_see"].lower()
    base = next((t for k, t in TITLES if k in s), "Rubbish dumped")
    where = {
        "Back alleyway": "in the alley",
        "Council land": "by the garages",
        "Footpath/bridleway": "on the path",
        "Commercial/industrial": "by the building",
    }.get(lab["land_type"]) or rng.choice(["on the pavement", "on the verge", "on the corner"])
    return f"{base} {where}"


def actions_for(key: str, dec: str, created: datetime, role: str) -> list[dict]:
    after = f"seed/photos/{key}_after.jpg" if (PHOTOS / f"{key}_after.jpg").exists() else None
    if role == "open":
        return []
    if role == "booked":
        held = dec == "hold_for_officer"
        return [
            {
                "at": iso(created + timedelta(hours=8)),
                "action": "hold" if held else "schedule",
                "note": "Held for inspection" if held else "Crew booked",
            }
        ]
    if dec == "not_a_fly_tip":
        return [{"at": iso(created + timedelta(hours=5)), "action": "not_fly_tip", "note": "Not fly-tipping"}]

    def clear(at):
        return {"at": iso(at), "action": "clear", "note": "Cleared by crew", **({"photo": after} if after else {})}

    if dec == "hold_for_officer":
        acts = [
            {"at": iso(created + timedelta(hours=10)), "action": "hold", "note": "Held for inspection"},
            {"at": iso(created + timedelta(days=2)), "action": "inspect", "note": "Site inspected"},
            clear(created + timedelta(days=3)),
        ]
        roll = rng.random()
        if roll < 0.35:
            acts.append(
                {"at": iso(created + timedelta(days=5)), "action": "warning_letter", "note": "Warning letter sent"}
            )
        elif roll < 0.45:
            acts.append(
                {"at": iso(created + timedelta(days=9)), "action": "fpn", "note": "Fixed penalty notice issued"}
            )
        if key in PROSECUTE and created + timedelta(days=30) < NOW:
            acts.append({"at": iso(created + timedelta(days=30)), "action": "prosecution", "note": "Prosecution"})
        return sorted(acts, key=lambda a: a["at"])
    gap = 2 if dec == "specialist" else 1
    return [
        {"at": iso(created + timedelta(hours=6)), "action": "schedule", "note": "Crew booked"},
        clear(created + timedelta(days=gap)),
    ]


hot_cycle = itertools.cycle(HOTSPOTS)
roles = {k: ("open", h) for k, h in OPEN} | {k: ("booked", h) for k, h in BOOKED}
closed = [
    k for k in sorted(LABELS) if k not in roles and k not in KIT_SOURCES and (PHOTOS / f"{k}_before.jpg").exists()
]
closed_age = {k: 10 + (140 * i / max(1, len(closed) - 1)) + rng.uniform(-1.5, 1.5) for i, k in enumerate(closed)}
if "case_089" in closed_age:
    closed_age["case_089"] = max(closed_age["case_089"], 70)  # old enough for the prosecution to have happened

incidents = []
for key in [k for k, _ in OPEN] + [k for k, _ in BOOKED] + closed:
    lab = LABELS[key]
    role = roles.get(key, ("closed", None))[0]
    if role == "closed":
        created = (NOW - timedelta(days=closed_age[key])).replace(hour=rng.randint(7, 21), minute=rng.randint(0, 59))
    else:
        created = NOW - timedelta(hours=dict(OPEN + BOOKED)[key])
    special = PLACE.get(key)
    if special == "railway":
        lat, lon, street, ward = railway_point()
    elif special == "merge":
        lat, lon = MERGE_PLACE[1], MERGE_PLACE[2]
        street, ward = MERGE_PLACE[0], geo.ward_for(lat, lon) or ""
    elif special:
        h = next(h for h in HOTSPOTS if h[0] == special)
        lat, lon, street, ward = near(h[1], h[2], 20)
    elif role == "closed" and rng.random() < 0.25:  # some closed cases sit on the hotspots too
        h = next(hot_cycle)
        lat, lon, street, ward = near(h[1], h[2], 30)
    else:
        lat, lon, street, ward = street_point()
    dec = decision(lab)
    incidents.append(
        {
            "key": key,
            "photo": f"seed/photos/{key}_before.jpg",
            "lat": round(lat, 6),
            "lon": round(lon, 6),
            "street": street or None,
            "ward": ward,
            "created_at": iso(created),
            "report_count": 2 if special == "merge" else 1,
            "description": title_for(lab),
            "model": model_for(lab),
            "actions": actions_for(key, dec, created, role),
            "demo_case": True,
            "source": "Simulated report. AI-generated illustrative photo.",
        }
    )
incidents.sort(key=lambda i: i["created_at"])
(SEED / "demo_incidents.json").write_text(json.dumps(incidents, indent=1))
print(f"cases: {len(incidents)} ({len(OPEN)} open, {len(BOOKED)} booked, {len(closed)} closed)")

# ---- 3. the model's reading of every photo, and of the demo kit --------------------------------------------------------
cache = {}
for i in incidents:
    cache[hashlib.sha256((APP / i["photo"]).read_bytes()).hexdigest()] = i["model"]
kit_dir = SEED / "live_demo"
for file, source, *_ in KIT:
    p = kit_dir / file
    if p.exists():
        cache[hashlib.sha256(p.read_bytes()).hexdigest()] = model_for(LABELS[source])
    else:
        print(f"  demo kit photo missing: {p.name} (run scripts/build_kit.py)")
(SEED / "model_cache.json").write_text(json.dumps(cache, indent=1))
print(f"model cache: {len(cache)} photos")

# ---- 4. smaller copies for phones --------------------------------------------------------------------------------------
web = SEED / "photos_web"
web.mkdir(exist_ok=True)
made = 0
for p in sorted(PHOTOS.glob("*.jpg")):
    out = web / p.name
    if out.exists() and out.stat().st_mtime >= p.stat().st_mtime:
        continue
    im = Image.open(p).convert("RGB")
    im.thumbnail((640, 640))
    im.save(out, "JPEG", quality=68, optimize=True)
    made += 1
print(f"photos for phones: {made} made")
