"""Hotspots and the Reduce view: repeat and emerging sites, weekly trend, and the recommended action.

Each hotspot has weekly_counts (12 weeks, oldest first), growing, primary_action and other_actions.
Actions carry no cost: the "cost" text in reduce.json is not served.
Calendar and York cards are dropped (calendar_flags / calendar stay as empty lists for older UI code).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import timedelta

import triage
from common import content, haversine_m, parse_dt, today

R = triage.HOTSPOT_RADIUS_M
CELL_LAT, CELL_LON = 0.0009, 0.0015  # ~100 m cells
STATE_RANK = {"repeat": 0, "emerging": 1, "new_site": 2}
MAX_HOTSPOTS = 12


def _cell(lat, lon):
    return int(lat // CELL_LAT), int(lon // CELL_LON)


class _Grid:
    def __init__(self, pts):
        self.g = defaultdict(list)
        for p in pts:
            self.g[_cell(p[0], p[1])].append(p)

    def near(self, lat, lon, r=R):
        cy, cx = _cell(lat, lon)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                for p in self.g.get((cy + dy, cx + dx), ()):
                    if haversine_m(lat, lon, p[0], p[1]) <= r:
                        yield p


def calendar_cards(ward: str | None) -> list[dict]:
    """Calendar entries for this month, plus the June/July student move-out card always (marked upcoming)."""
    red = content("reduce.json", {}) or {}
    month = today().month
    out, seen = [], set()
    for c in red.get("calendar", []) or []:
        months = c.get("months") or []
        wards = c.get("wards") or []
        in_ward = not wards or ward is None or ward in wards
        is_move_out = bool({6, 7} & set(months)) or any(
            w in (str(c.get("id", "")) + str(c.get("title", ""))).lower() for w in ("student", "move-out", "move out")
        )
        if month in months and in_ward:
            when = "now"
        elif is_move_out:
            when = "upcoming"
        else:
            continue
        if c.get("id") in seen:
            continue
        seen.add(c.get("id"))
        out.append(
            {
                **{k: v for k, v in c.items() if not k.startswith("_")},
                "when": when,
                "upcoming": when == "upcoming",
                "in_ward": in_ward,
            }
        )
    return out


WEEKS = 12
# Short titles (8 words or fewer) for the reduce.json action ids; a "title" key in reduce.json wins.
TITLES = {
    "fast_first_clear": "Clear it within 48 hours",
    "visible_clearance": "Tape it off and clear it visibly",
    "watching_eyes": "Put up watching-eyes signs",
    "design_out": "Site improvements: fencing, barriers, planting or lighting",
    "alley_gating": "Gate the back alley",
    "bulky_amnesty": "Run a free bulky collection",
    "scrap_leaflets": "Leaflet nearby streets about waste carriers",
    "covert_camera": "Deploy a covert camera",
}


def _title(a: dict) -> str:
    if a.get("title"):
        return str(a["title"])
    if a.get("id") in TITLES:
        return TITLES[a["id"]]
    import re

    first = re.split(r"[,:;(]| and ", str(a.get("action") or "Recommended action"))[0].strip()
    return " ".join(first.split()[:8])


def _one_line(text) -> str:
    import re

    t = str(text or "").strip()
    return re.split(r"(?<=[.!?])\s", t)[0] if t else ""


def action_cards(recs: list[dict]) -> tuple[dict | None, list[dict]]:
    if not recs:
        return None, []
    a = recs[0]
    primary = {
        "id": a.get("id"),
        "title": _title(a),
        "why": _one_line(a.get("why")),
        "strength": a.get("strength"),
        "evidence": a.get("evidence"),
        "detail": a.get("action"),
    }
    return primary, [{"id": o.get("id"), "title": _title(o), "strength": o.get("strength")} for o in recs[1:]]


def recommended(state: str, waste: str | None, land: str | None) -> list[dict]:
    red = content("reduce.json", {}) or {}
    out = []
    for n, a in enumerate(red.get("actions", []) or []):
        if state not in (a.get("applies_to") or []):
            continue
        if a.get("waste_types") and waste not in a["waste_types"]:
            continue
        if a.get("land_types") and land not in a["land_types"]:
            continue
        rec = {k: a.get(k) for k in ("id", "title", "action", "why", "evidence", "strength") if k in a}
        # more specific actions (fewer states, or a waste/land filter) rank above general ones of equal strength
        rec["_spec"] = (len(a.get("applies_to") or []) - bool(a.get("waste_types")) - bool(a.get("land_types")), n)
        out.append(rec)
    rank = {"strong": 0, "moderate": 1, "weak": 2}
    out.sort(key=lambda a: (rank.get(a.get("strength"), 3), a["_spec"]))
    for a in out:
        a.pop("_spec", None)
    return out


def build(incidents: list[dict], reports: list[dict] | None = None) -> list[dict]:
    t_end = parse_dt(today().isoformat()) + timedelta(days=1)
    w0 = t_end - timedelta(days=7 * WEEKS)
    d90, d12 = t_end - timedelta(days=91), t_end - timedelta(days=366)

    hist = []
    for p in triage.history_points():
        d = parse_dt(p.get("date"))
        if d is None or p.get("lat") is None or d > t_end or d < d12:
            continue
        hist.append((float(p["lat"]), float(p["lon"]), d, p))
    live = [i for i in incidents if i["status"] != "not_fly_tip"]
    inc_pts = [(i["lat"], i["lon"], parse_dt(i["created_at"]), i) for i in live]
    hg, ig = _Grid(hist), _Grid(inc_pts)
    live_ids = {i["id"] for i in live}
    if reports is not None:
        loc = {i["id"]: (i["lat"], i["lon"]) for i in live}
        rep_pts = []
        for r in reports:
            if r["incident_id"] not in live_ids:
                continue
            lat, lon = (r["lat"], r["lon"]) if r.get("lat") is not None else loc[r["incident_id"]]
            rep_pts.append((lat, lon, parse_dt(r["created_at"])))
    else:
        rep_pts = [
            (i["lat"], i["lon"], parse_dt(i["created_at"]))
            for i in live
            for _ in range(int(i.get("report_count") or 1))
        ]
    wk_pts = [p for p in hist if p[2] >= w0] + [p for p in rep_pts if p[2] and w0 <= p[2] < t_end]
    wg = _Grid(wk_pts)

    def weekly(lat, lon):
        wk = [0] * WEEKS
        for p in wg.near(lat, lon):
            k = int((p[2] - w0).total_seconds() // (7 * 86400))
            if 0 <= k < WEEKS:
                wk[k] += 1
        return wk

    def counts(lat, lon):
        r90 = r12 = 0
        for p in hg.near(lat, lon):
            r12 += 1
            r90 += p[2] >= d90
        for p in ig.near(lat, lon):
            n = int(p[3].get("report_count") or 1)
            if p[2] and p[2] >= d12:
                r12 += n
            if p[2] and p[2] >= d90:
                r90 += n
        return r90, r12

    cands = []
    for i in live:
        st = triage.nearby(i["lat"], i["lon"], t_end.isoformat(), exclude_id=i["id"], incidents=incidents)["state"]
        if st == "new_site":
            continue
        r90, r12 = counts(i["lat"], i["lon"])
        t = i.get("triage") or {}
        cands.append(
            {
                "id": i["id"],
                "incident_id": i["id"],
                "lat": i["lat"],
                "lon": i["lon"],
                "street": i.get("street"),
                "ward": i.get("ward"),
                "reports_90d": r90,
                "reports_12m": r12,
                "state": st,
                "waste_type": t.get("waste_type"),
                "land_type": t.get("land_type"),
                "status": i["status"],
                "photo_url": i.get("photo_url"),
            }
        )

    # history-only repeat sites (no live incident there): >= 3 other reports within 100 m in 90 days
    recent = [p for p in hist if p[2] >= d90]
    rg = _Grid(recent)
    for n, p in enumerate(sorted(recent, key=lambda p: p[2], reverse=True)):
        others = sum(1 for _ in rg.near(p[0], p[1])) - 1
        if others < 3:
            continue
        r90, r12 = counts(p[0], p[1])
        cands.append(
            {
                "id": 100000 + n,
                "incident_id": None,
                "lat": p[0],
                "lon": p[1],
                "street": p[3].get("street"),
                "ward": p[3].get("ward"),
                "reports_90d": r90,
                "reports_12m": r12,
                "state": "repeat",
                "waste_type": None,
                "land_type": None,
                "status": None,
                "photo_url": None,
            }
        )

    cands.sort(key=lambda c: (c["incident_id"] is None, STATE_RANK[c["state"]], -c["reports_90d"], -c["reports_12m"]))
    picked: list[dict] = []
    for c in cands:
        if any(haversine_m(c["lat"], c["lon"], p["lat"], p["lon"]) <= R for p in picked):
            continue
        if c["incident_id"] is None and any(
            (c["street"] and c["street"] == p["street"]) or haversine_m(c["lat"], c["lon"], p["lat"], p["lon"]) <= 250
            for p in picked
        ):
            continue
        picked.append(c)
        if len(picked) >= MAX_HOTSPOTS:
            break
    for c in picked:
        c["recommended"] = recommended(c["state"], c["waste_type"], c["land_type"])
        c["primary_action"], c["other_actions"] = action_cards(c["recommended"])
        c["weekly_counts"] = weekly(c["lat"], c["lon"])
        this, last = c["weekly_counts"][-1], c["weekly_counts"][-2]
        c["growing"] = this >= 2 and this > last
        c["calendar_flags"] = []  # no calendar cards
    return picked


def reduce_view(incidents: list[dict], reports: list[dict] | None = None) -> dict:
    """Everything the Reduce tab needs in one call: hotspots and the rules text."""
    red = content("reduce.json", {}) or {}
    return {"hotspots": build(incidents, reports), "hotspot_rules": red.get("hotspot_rules", {}), "calendar": []}
