"""Council priority for an incident, computed on read: hazard, age, growth (week on week), repeat site, reporters.

score 0-100; level urgent >= 75, high >= 50, normal >= 25, else low. Reasons are short plain phrases.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

import triage
from common import haversine_m, parse_dt

GROWTH_RADIUS_M = 100
HAZARD_WORDS = [
    "glass",
    "needle",
    "syringe",
    "sharps",
    "asbestos",
    "chemical",
    "clinical",
    "oil drum",
    "gas cylinder",
    "playground",
    "school",
]
PLACE_WORDS = {"playground": "Near a playground", "school": "Near a school"}

W_HAZARD = 50  # specialist decision or a hazard keyword
W_PER_DAY = 8  # per day since first report
MAX_AGE = 32
W_GROWING = 15  # growing week on week, plus W_PER_NEW per extra sighting over last week
W_PER_NEW = 4
MAX_GROWTH = 27
W_REPEAT = 10  # repeat hotspot (3+ reports within 100 m in 90 days)
W_PER_REPORTER = 4  # per extra person reporting
MAX_REPORTERS = 12
W_GONE = -10  # more residents say it's gone than still there


def level_for(score: int) -> str:
    return "urgent" if score >= 75 else "high" if score >= 50 else "normal" if score >= 25 else "low"


def _hazard_word(texts: list[str]) -> str | None:
    for t in texts:
        if not t:
            continue
        low = t.lower()
        for w in HAZARD_WORDS:
            if re.search(rf"\b(no|not|without)\s+(visible\s+)?{re.escape(w)}", low):
                continue
            if re.search(rf"\b{re.escape(w)}", low):
                return w
    return None


class Context:
    """Precomputed sightings (reports + still-there confirmations) so a whole list scores in one pass."""

    def __init__(
        self, incidents: list[dict], reports: list[dict], confirmations: list[dict], now: datetime | None = None
    ):
        self.now = now or datetime.now(UTC)
        self.incidents = incidents
        self.w1 = self.now - timedelta(days=7)
        self.w2 = self.now - timedelta(days=14)
        excluded = {i["id"] for i in incidents if i.get("status") == "not_fly_tip"}
        loc = {i["id"]: (i["lat"], i["lon"]) for i in incidents}
        # (lat, lon, when, incident_id, kind)
        self.sightings: list[tuple] = []
        for r in reports:
            if r["incident_id"] in excluded:
                continue
            d = parse_dt(r["created_at"])
            if d is None or d < self.w2:
                continue
            lat, lon = (
                (r.get("lat"), r.get("lon")) if r.get("lat") is not None else loc.get(r["incident_id"], (None, None))
            )
            if lat is not None:
                self.sightings.append((lat, lon, d, r["incident_id"], "report"))
        self.conf_by_inc: dict[int, list[dict]] = {}
        for c in confirmations:
            self.conf_by_inc.setdefault(c["incident_id"], []).append(c)
            if not c["still_there"] or c["incident_id"] in excluded:
                continue
            d = parse_dt(c["at"])
            if d is None or d < self.w2 or c["incident_id"] not in loc:
                continue
            lat, lon = loc[c["incident_id"]]
            self.sightings.append((lat, lon, d, c["incident_id"], "confirm"))
        for p in triage.history_points():
            d = parse_dt(p.get("date"))
            if d is None or d < self.w2 or p.get("lat") is None:
                continue
            self.sightings.append((float(p["lat"]), float(p["lon"]), d, None, "history"))
        self.reports_by_inc: dict[int, list[dict]] = {}
        for r in reports:
            self.reports_by_inc.setdefault(r["incident_id"], []).append(r)

    def growth(self, inc: dict) -> tuple[int, int, int]:
        """(this_week, last_week, confirmations_this_week) sightings at or within 100 m of the incident."""
        this = last = conf = 0
        lat, lon = inc["lat"], inc["lon"]
        for plat, plon, d, iid, kind in self.sightings:
            if iid != inc["id"]:
                if abs(plat - lat) > 0.0012 or abs(plon - lon) > 0.002:
                    continue
                if haversine_m(lat, lon, plat, plon) > GROWTH_RADIUS_M:
                    continue
            if d >= self.w1:
                this += 1
                conf += kind == "confirm"
            elif d >= self.w2:
                last += 1
        return this, last, conf


def compute(inc: dict, ctx: Context) -> dict:
    """{score, level, reasons, growing, ...counts} for one stored incident row."""
    t = inc.get("triage") or {}
    status = inc.get("status")
    confs = ctx.conf_by_inc.get(inc["id"], [])
    still = sum(1 for c in confs if c["still_there"])
    gone = len(confs) - still
    this, last, conf = ctx.growth(inc)
    growing = this >= 2 and this > last
    out = {"still_there_count": still, "gone_count": gone}
    if status in ("cleared", "not_fly_tip", "forwarded"):
        out["priority"] = {
            "score": 0,
            "level": "low",
            "reasons": [{"cleared": "Cleared", "not_fly_tip": "Not fly-tipping"}.get(status, "Passed on")],
        }
        out["growing"] = False
        return out

    score, reasons = 0, []
    word = _hazard_word([t.get("hazards"), t.get("what_you_see"), inc.get("description"), inc.get("public_summary")])
    if t.get("decision") == "specialist" or word:
        score += W_HAZARD
        if word in PLACE_WORDS:
            reasons.append(PLACE_WORDS[word])
        elif word:
            reasons.append(f"Possible hazard: {word}")
        else:
            reasons.append("Possible hazard")

    if growing:
        score += min(MAX_GROWTH, W_GROWING + W_PER_NEW * max(0, this - max(last, 1)))
        noun = "new reports" if not conf else "new reports and sightings"
        reasons.append(f"Growing: {this} {noun} this week")

    created = parse_dt(inc.get("created_at"))
    days = max(0, int((ctx.now - created).total_seconds() // 86400)) if created else 0
    score += min(MAX_AGE, W_PER_DAY * days)
    if days >= 1:
        reasons.append(f"Open {days} day{'s' if days != 1 else ''}")

    if (t.get("hotspot") or {}).get("state") == "repeat":
        score += W_REPEAT
        reasons.append("Repeat hotspot")

    n = int(inc.get("report_count") or 1)
    if n > 1:
        score += min(MAX_REPORTERS, W_PER_REPORTER * (n - 1))
        reasons.append(f"{n} people reported it")
    if still:
        reasons.append(f"Still there ({still} confirmed)")

    if gone > still:
        score += W_GONE
        reasons.append("Residents say it may be gone")

    if status == "triaging" and not reasons:
        reasons.append("Being checked")
    score = max(0, min(100, int(round(score))))
    out["priority"] = {"score": score, "level": level_for(score), "reasons": reasons or ["New report"]}
    out["growing"] = growing
    return out
