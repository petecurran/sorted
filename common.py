"""Shared paths, content loading, Defra categories and time helpers for the Sorted backend."""

from __future__ import annotations

import json
import logging
import math
import os
import re
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

log = logging.getLogger("sorted")

APP = Path(__file__).resolve().parent
CONTENT = APP / "content"
SEED = APP / "seed"
STATIC = APP / "static"
# All runtime data (DB, uploads) lives in FT_DATA_DIR (default app/data), so a test server can run on a temp dir.
DATA = Path(os.environ.get("FT_DATA_DIR") or (APP / "data")).expanduser().resolve()
UPLOADS = DATA / "uploads"
DB_PATH = DATA / "app.db"
DEV = APP / "data" / "dev_fixtures"  # backend dev fixtures ship with the code, not the runtime data

SIZES = [
    "Single black bag",
    "Single item",
    "Car boot or less",
    "Small van load",
    "Transit van load",
    "Tipper lorry load",
    "Significant/multiple loads",
]
WASTE = [
    "Animal carcasses",
    "Green",
    "Vehicle parts",
    "White goods",
    "Other electrical",
    "Tyres",
    "Asbestos",
    "Clinical",
    "Construction/demolition/excavation",
    "Black bags - commercial",
    "Black bags - household",
    "Chemical drums, oil or fuel",
    "Other household waste",
    "Other commercial waste",
    "Other (unidentified)",
]
LAND = [
    "Highway",
    "Footpath/bridleway",
    "Back alleyway",
    "Railway",
    "Council land",
    "Agricultural",
    "Private/residential",
    "Commercial/industrial",
    "Watercourse/bank",
    "Other (unidentified)",
]

MODEL_NAME = (
    "Gemma 4 26B (Cloudflare Workers AI)"
    if os.environ.get("FT_CLASSIFIER", "").strip().lower() == "workers-ai"
    else "Gemma 4 12B (on this laptop)"
)

# A hosted copy is one visitor's own copy of the demo, in a Cloudflare container behind the Worker in cloudflare/
# (decision 6). It needs FT_HOSTED=1 and the variable Cloudflare sets in every container, so FT_HOSTED alone on a laptop
# changes nothing.
HOSTED = os.environ.get("FT_HOSTED") == "1" and bool(os.environ.get("CLOUDFLARE_DURABLE_OBJECT_ID"))

# The demo council: a made-up authority (the ONS boundary for Liverpool is relabelled to it in seed/lads_lcr.geojson).
# Every backend string that names "our" council comes from here.
COUNCIL_NAME = "Mersey Vale City Council"
CASE_REF_PREFIX = "MVCC-FT-2026"


def case_ref(iid: int) -> str:
    return f"{CASE_REF_PREFIX}-{int(iid):04d}"


OPEN_EXCLUDED = ("cleared", "not_fly_tip")

_cache: dict[Path, tuple[float, object]] = {}
_warned: set[str] = set()


def resolve(kind: str, name: str) -> Path | None:
    """Real file (content/ or seed/) first, then the backend's dev fixture, else None."""
    real = (CONTENT if kind == "content" else SEED) / name
    if real.exists():
        return real
    dev = DEV / kind / name
    if dev.exists():
        if f"{kind}/{name}" not in _warned:
            _warned.add(f"{kind}/{name}")
            log.warning("using dev fixture for %s/%s (real file not present yet)", kind, name)
        return dev
    return None


def load_json(kind: str, name: str, default=None):
    """Load a content or seed JSON file, cached on mtime so team edits show up without a restart."""
    path = resolve(kind, name)
    if path is None:
        return default
    try:
        mtime = path.stat().st_mtime
        hit = _cache.get(path)
        if hit and hit[0] == mtime:
            return hit[1]
        data = json.loads(path.read_text())
        _cache[path] = (mtime, data)
        return data
    except Exception as e:  # malformed team edit: keep serving the last good copy
        log.error("could not read %s: %s", path, e)
        hit = _cache.get(path)
        return hit[1] if hit else default


def content(name: str, default=None):
    return load_json("content", name, default if default is not None else {})


def seed(name: str, default=None):
    return load_json("seed", name, default)


# The stage rebrand: content/brand.json renames the council for display. Stored data keeps the baseline names above;
# the front ends rewrite what they show (static/shared/brand.js) and exports go through rebrand().
BASE_BRAND = {
    "council_name": COUNCIL_NAME,
    "place": "Mersey Vale",
    "case_prefix": CASE_REF_PREFIX.split("-")[0],
    "colour": "#4E2681",
    "accent": "#FFC71F",
    "mark": "",
}
_BRAND_RX = re.compile(r"Mersey Vale City Council|Mersey Vale|MVCC(?=[-_])|mersey-vale")


def brand() -> dict:
    b = content("brand.json", {}) or {}
    return {
        **BASE_BRAND,
        **{k: v.strip() for k, v in b.items() if k in BASE_BRAND and isinstance(v, str) and v.strip()},
    }


def brand_script(b: dict) -> str:
    """The brand as the /api/brand.js script. A crest named in "mark" is inlined as mark_svg, so the logo is drawn on
    first paint."""
    b = dict(b)
    if b.get("mark"):
        m = b["mark"]
        p = (STATIC / m.removeprefix("/static/")) if m.startswith("/static/") else (STATIC / "shared" / "marks" / m)
        p = p.resolve()
        if p.is_relative_to(STATIC) and p.suffix == ".svg" and p.is_file():
            b["mark_svg"] = p.read_text()
        else:
            log.error("brand.json: mark %r not found (expected an .svg in static/shared/marks/)", m)
    return f"window.CH_BRAND = {json.dumps(b)};\n"


def rebrand(text: str) -> str:
    b = brand()
    slug = re.sub(r"[^a-z0-9]+", "-", b["place"].lower()).strip("-")
    names = {
        "Mersey Vale City Council": b["council_name"],
        "Mersey Vale": b["place"],
        "MVCC": b["case_prefix"],
        "mersey-vale": slug,
    }
    if any(_BRAND_RX.search(v) for v in names.values()):
        return text  # a new name that reuses the old words would be rewritten twice; leave it
    return _BRAND_RX.sub(lambda m: names[m.group(0)], text)


# ---- config -------------------------------------------------------------------------------------

MONTH_NAMES = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
]


def financial_quarter(d: date) -> dict:
    """The WasteDataFlow reporting quarter for a date (the financial year starts in April). In its first month the
    return is for the quarter just ended, since that is the one being prepared. Deadline: the 25th of the month after
    the quarter ends (a demo assumption; set "quarter" in content/config.json to override)."""
    first_month = d.month in (4, 7, 10, 1)
    m = d.month - 3 if first_month else d.month
    y = d.year
    if m < 1:
        m, y = m + 12, y - 1
    n = {4: 1, 5: 1, 6: 1, 7: 2, 8: 2, 9: 2, 10: 3, 11: 3, 12: 3, 1: 4, 2: 4, 3: 4}[m]
    fy = y if n < 4 else y - 1
    sm = {1: 4, 2: 7, 3: 10, 4: 1}[n]
    em = sm + 2
    end = (date(y, em + 1, 1) if em < 12 else date(y + 1, 1, 1)) - timedelta(days=1)
    deadline = date(end.year + (end.month == 12), end.month % 12 + 1, 25)
    return {
        "id": f"{fy}-Q{n}",
        "name": f"Q{n} {fy}/{str(fy + 1)[2:]}",
        "label": f"{MONTH_NAMES[sm - 1]}–{MONTH_NAMES[em - 1]} {y}",
        "start": date(y, sm, 1).isoformat(),
        "end": end.isoformat(),
        "deadline": deadline.isoformat(),
    }


DEFAULT_DEPOT = {"lat": 53.4296, "lon": -2.9531, "name": "Depot"}


def config() -> dict:
    c = dict(content("config.json", {}))
    c.setdefault("city", "Liverpool")
    # The demo follows the calendar: "today" is the real date unless content/config.json or FT_TODAY fixes one.
    c.setdefault("today", os.environ.get("FT_TODAY") or date.today().isoformat())
    c["depot"] = {**DEFAULT_DEPOT, **(c.get("depot") or {})}
    c["quarter"] = {**financial_quarter(date.fromisoformat(str(c["today"])[:10])), **(c.get("quarter") or {})}
    c.setdefault("collection_day_wards", [])
    c.setdefault("bulky_bookings", [])
    return c


def today() -> date:
    try:
        return date.fromisoformat(str(config()["today"])[:10])
    except ValueError:
        return date.today()


# ---- time ---------------------------------------------------------------------------------------


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_dt(s) -> datetime | None:
    if not s:
        return None
    if isinstance(s, datetime):
        return s if s.tzinfo else s.replace(tzinfo=UTC)
    s = str(s).strip()
    try:
        if len(s) == 10:
            return datetime.fromisoformat(s).replace(tzinfo=UTC)
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=UTC)
    except ValueError:
        return None


def iso(d: datetime) -> str:
    return d.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def plus(s: str, **kw) -> str:
    d = parse_dt(s) or datetime.now(UTC)
    return iso(d + timedelta(**kw))


# ---- geometry -----------------------------------------------------------------------------------


def haversine_m(lat1, lon1, lat2, lon2) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


# ---- category normalising -----------------------------------------------------------------------


def _norm(s: str) -> str:
    return "".join(ch for ch in str(s).lower() if ch.isalnum())


def match_category(value, options: list[str]) -> str | None:
    """Map a model's free-ish text onto the exact Defra string, or None (for n/a or unknown)."""
    if value is None:
        return None
    v = str(value).strip()
    if not v or _norm(v) in ("na", "none", "null", "unknown", ""):
        return None
    if v in options:
        return v
    nv = _norm(v)
    for o in options:
        if _norm(o) == nv:
            return o
    for o in options:  # containment either way ("black bags household" / "tyre")
        no = _norm(o)
        if nv and (nv in no or no in nv):
            return o
    import difflib

    close = difflib.get_close_matches(v.lower(), [o.lower() for o in options], n=1, cutoff=0.6)
    if close:
        return next(o for o in options if o.lower() == close[0])
    return None
