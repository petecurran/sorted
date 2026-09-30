"""Council rules on top of the model: decision precedence, context flags, whose job, hotspot state (no cost).

Precedence:
  specialist (waste type or hazard keyword) -> bulky booking (not_a_fly_tip, the only automatic close) -> collection
  day -> model says no or unsure (review: a person checks) -> hold waste types -> clear_now.
Then, if someone else must clear it (whose_job), `forward_to` names them and the decision_why says pass it on.
"""
from __future__ import annotations

import re
from datetime import timedelta

import geo
from common import COUNCIL_NAME, MODEL_NAME, config, content, haversine_m, parse_dt, seed, today

HOTSPOT_RADIUS_M = 100


# ---- helpers ------------------------------------------------------------------------------------

# Too common in plain descriptions ("a plastic sheet", "bags of cement") to count unless the model calls them a hazard.
TEXT_SKIP = {"sheet", "sheeting", "cement"}


def _text_keywords(keywords: list[str]) -> list[str]:
    """Keywords to look for in the description and item list, as opposed to the hazards field."""
    return [k for k in keywords if len(k) > 4 and k.lower() not in TEXT_SKIP]


def _hazard_hit(hazards: str, keywords: list[str]) -> str | None:
    """First specialist keyword present in the hazards text, ignoring negated fragments ('no asbestos')."""
    if not hazards:
        return None
    for frag in re.split(r"[,;/]| and ", hazards.lower()):
        frag = frag.strip()
        if not frag or frag in ("none", "n/a", "unknown", "none visible", "nothing") or re.match(r"^(no|none|not)\b", frag):
            continue
        for kw in keywords:
            if re.search(rf"\b{re.escape(kw.lower())}", frag):
                return kw
    return None


def public_summary(what_you_see: str, fallback: str = "Reported fly-tipping") -> str:
    s = (what_you_see or "").strip()
    if not s:
        return fallback
    s = re.sub(r"^(the (photo|image|picture) shows|this (photo|image) shows|(i|we) (can )?see|there (is|are)|"
               r"a photo of|an image of|image of|photo of)\s+", "", s, flags=re.I)
    s = re.split(r"(?<=[.!?])\s", s)[0].rstrip(" .!?")
    if len(s) > 100:
        cut = s[:100].rsplit(" ", 1)[0]
        s = re.sub(r"\b(and|or|with|on|in|near|next|to|of|a|an|the|by|at)$", "", cut.rstrip(" ,;")).rstrip(" ,;")
    return (s[:1].upper() + s[1:]) if s else fallback


def _how_we_know(match: dict, land_type, rail_m) -> str:
    if "near_railway_m" in match:
        return f"Map check: {rail_m:.0f} m from railway land (OpenStreetMap)."
    if "in_national_highways" in match:
        return "Map check: inside the National Highways boundary."
    if "land_type" in match:
        return f"Land type from the photo: {land_type or 'unknown'}."
    return (f"Land type from the photo: {land_type or 'unknown'}. "
            "No railway or National Highways land on the map.")


def whose_job(lat, lon, land_type) -> dict:
    wj = content("whose_job.json", {}) or {}
    rail = None
    out = None
    for rule in wj.get("rules", []):
        m = rule.get("match") or {}
        ok = bool(m)
        if "near_railway_m" in m:
            if rail is None:
                rail = geo.railway_distance_m(lat, lon)
            ok = ok and rail is not None and rail <= float(m["near_railway_m"])
        if "in_national_highways" in m:
            ok = ok and geo.in_national_highways(lat, lon) == bool(m["in_national_highways"])
        if "land_type" in m:
            lt = m["land_type"] if isinstance(m["land_type"], list) else [m["land_type"]]
            ok = ok and land_type in lt
        if ok:
            out = {"body": rule.get("body"), "law": rule.get("law"), "note": rule.get("note", ""),
                   "clear_first_bill_later": bool(rule.get("clear_first_bill_later", False)), "rule": rule.get("id"),
                   "how_we_know": _how_we_know(m, land_type, rail)}
            break
    if out is None:
        d = wj.get("default") or {"body": COUNCIL_NAME,
                                  "law": "Environmental Protection Act 1990 s.33 and s.89", "note": ""}
        out = {"body": d.get("body"), "law": d.get("law"), "note": d.get("note", ""),
               "clear_first_bill_later": bool(d.get("clear_first_bill_later", False)), "rule": "default",
               "how_we_know": _how_we_know({}, land_type, rail)}
    auth = geo.authority_for(lat, lon)
    out["authority"] = auth
    if auth != geo.CITY_AUTHORITY:
        if out["body"] and "council" in str(out["body"]).lower():
            out["body"] = auth
            out["note"] = f"{auth} area, outside the {COUNCIL_NAME} boundary. Forward to {auth}."
            out["how_we_know"] = f"Map check: inside the {auth} boundary (ONS)."
        else:
            out["note"] = (out["note"] + " " if out["note"] else "") + f"In the {auth} area."
    return out


def history_points() -> list[dict]:
    pts = seed("history.json", []) or []
    return pts if isinstance(pts, list) else []


def nearby(lat, lon, at, exclude_id=None, incidents=None) -> dict:
    """Counts of other reports (history + other incidents) within 100 m, in windows before `at`."""
    at_d = parse_dt(at) or parse_dt(today().isoformat())
    c28 = c90 = c12 = 0
    pts = [(p.get("lat"), p.get("lon"), p.get("date")) for p in history_points()]
    for inc in incidents or []:
        if inc["id"] == exclude_id or inc.get("status") == "not_fly_tip":
            continue
        pts.append((inc["lat"], inc["lon"], inc["created_at"]))
    # cheap bounding box before haversine (100 m is ~0.0009 deg lat, ~0.0015 deg lon here)
    for plat, plon, pdate in pts:
        if plat is None or plon is None or abs(plat - lat) > 0.0012 or abs(plon - lon) > 0.002:
            continue
        d = parse_dt(pdate)
        if d is None or d > at_d + timedelta(minutes=1):
            continue
        if haversine_m(lat, lon, plat, plon) > HOTSPOT_RADIUS_M:
            continue
        age = (at_d - d).days
        if age <= 365:
            c12 += 1
        if age <= 90:
            c90 += 1
        if age <= 28:
            c28 += 1
    state = "repeat" if c90 >= 3 else "emerging" if c28 >= 1 else "new_site"
    return {"state": state, "nearby_28d": c28, "nearby_90d": c90, "nearby_12m": c12}


def _bulky_hit(lat, lon, radius_m):
    t = today().isoformat()
    for b in config().get("bulky_bookings") or []:
        if str(b.get("date", ""))[:10] not in (t, "today"):  # "today": booked for whatever day the demo runs
            continue
        try:
            if haversine_m(lat, lon, float(b["lat"]), float(b["lon"])) <= radius_m:
                return b
        except (KeyError, TypeError, ValueError):
            continue
    return None


# ---- forwarding and the single alert ------------------------------------------------------------

FORWARDABLE = ("clear_now", "hold_for_officer", "specialist")


def forward_to(wj: dict | None, decision: str | None) -> str | None:
    """Body to pass the report to, when someone other than the demo council must clear it; else None.

    Private land where the council may clear first and recover costs (clear_first_bill_later) stays with us, and
    so do reports a person still has to check (review) or that are not fly-tipping.
    """
    wj = wj or {}
    body = wj.get("body")
    if not body or body == COUNCIL_NAME or wj.get("clear_first_bill_later") or decision not in FORWARDABLE:
        return None
    return body


def forward_why(wj: dict) -> str:
    """e.g. 'Network Rail land. Forward to Network Rail.'"""
    body = str(wj.get("body") or "")
    if "council" in body.lower():
        return f"{body} area. Forward to {body}."
    if body.lower().startswith("landowner"):
        return "Private land. Forward to the landowner."
    return f"{body} land. Forward to {body}."


HAZARD_WORDS = {"asbestos": "asbestos", "sheeting": "asbestos sheeting", "corrugated": "asbestos sheeting",
                "needle": "needles", "syringe": "needles", "chemical": "chemicals", "oil": "oil or fuel",
                "drum": "chemical drums", "gas cylinder": "gas cylinder"}
WASTE_WORDS = {"Asbestos": "asbestos", "Clinical": "clinical waste", "Chemical drums, oil or fuel": "chemicals or fuel"}


def headline_alert(t: dict) -> str | None:
    """ONE short alert for the triage card, from the highest-severity item, or None.

    Severity: rule hazard (specialist) > AI alone suggests specialist > context flag (bulky booking, bin day).
    """
    if not t:
        return None
    rules = content("triage_rules.json", {}) or {}
    keywords = rules.get("specialist_hazard_keywords", list(HAZARD_WORDS))
    if t.get("decision") == "specialist":
        waste = t.get("waste_type")
        kw = _hazard_hit(t.get("hazards") or "", keywords) or \
            _hazard_hit(f'{t.get("what_you_see") or ""}, {t.get("items") or ""}', _text_keywords(keywords))
        what = WASTE_WORDS.get(waste) or (HAZARD_WORDS.get(kw.lower(), kw.lower()) if kw else None)
        return f"Possible {what}: specialist removal" if what else "Specialist removal needed"
    if t.get("model_decision") == "specialist":
        return "Possible hazard. Check the photo."
    for f in t.get("context_flags") or []:
        if f.get("kind") in ("bulky_booking", "collection_day") and f.get("text"):
            return f["text"]
    return None


# ---- main ---------------------------------------------------------------------------------------

def run(m: dict, *, lat, lon, ward, incident_id=None, created_at=None, incidents=None) -> dict:
    """Build the full triage block from a normalised model result `m` (see classifier.normalise)."""
    rules = content("triage_rules.json", {}) or {}
    cfg = config()
    waste, size, land = m.get("waste_type"), m.get("size"), m.get("land_type") or "Other (unidentified)"
    hazards = m.get("hazards") or ""
    flags: list[dict] = []
    decision = why = None

    spec_types = rules.get("specialist_waste_types", ["Asbestos", "Clinical", "Chemical drums, oil or fuel"])
    keywords = rules.get("specialist_hazard_keywords", ["asbestos", "sheeting", "corrugated", "needle", "syringe",
                                                        "chemical", "oil", "drum", "gas cylinder"])
    # The model's description and item list are scanned too: it often lists "paint tins" without calling them a hazard.
    seen = f'{m.get("what_you_see", "")}, {m.get("items", "")}'
    kw = _hazard_hit(hazards, keywords) or (_hazard_hit(seen, _text_keywords(keywords))
                                            if m.get("fly_tip") != "no" else None)

    bulky_rule = rules.get("bulky_booking") or {}
    bulky = _bulky_hit(lat, lon, float(bulky_rule.get("radius_m", 30)))
    coll_rule = rules.get("collection_day") or {}
    coll = bool(ward) and ward in (cfg.get("collection_day_wards") or []) and \
        waste in (coll_rule.get("applies_to_waste") or ["Black bags - household"])

    if bulky:
        flags.append({"kind": "bulky_booking",
                      "text": bulky_rule.get("text") or "Bulky collection booked today",
                      "address": bulky.get("address")})
    if coll:
        flags.append({"kind": "collection_day",
                      "text": (coll_rule.get("text") or "Bin day in this ward. Bags are likely awaiting collection.")
                      .replace("{ward}", ward or "")})

    if m.get("offline"):
        decision, why = "review", m.get("reason") or "Model offline. Check the photo."
    elif waste in spec_types or kw:
        decision = "specialist"
        what = waste if waste in spec_types else f"possible {kw}"
        why = rules.get("specialist_note") or f"Possible hazardous waste ({what}). Send a licensed specialist team."
        if "{" in why:
            why = why.replace("{what}", what)
        if kw:
            flags.append({"kind": "hazard_rule", "text": f"Possible hazard: {kw}. Specialist removal."})
    elif bulky:
        decision = bulky_rule.get("decision", "not_a_fly_tip")
        why = bulky_rule.get("note") or (bulky_rule.get("text") or "Bulky collection booked today").rstrip(".") + ". Not fly-tipping."
    elif coll:
        decision = coll_rule.get("decision", "review")
        why = coll_rule.get("note") or (coll_rule.get("text") or "Bin day in this ward").rstrip(".") + \
            ". Check before sending a crew."
    elif m.get("fly_tip") == "no":
        # The model alone never closes a resident's report: a person checks it.
        decision, why = "review", rules.get("model_no_note") or "AI reading: possibly not fly-tipping. Check the photo."
    elif m.get("fly_tip") == "unsure":
        decision, why = "review", rules.get("unsure_note") or "AI not confident. Check the photo."
    elif waste in (rules.get("hold_waste_types") or ["Black bags - household", "Black bags - commercial",
                                                        "Other commercial waste"]):
        decision = "hold_for_officer"
        why = rules.get("hold_note") or "Bags and trade waste may hold evidence. Officer to inspect before clearance."
    else:
        decision = "clear_now"
        why = rules.get("clear_note") or "No evidence expected. Book a crew."
    why = why.replace("{waste}", waste or "waste")

    hs = nearby(lat, lon, created_at, exclude_id=incident_id, incidents=incidents)
    wj = whose_job(lat, lon, land)
    fwd = forward_to(wj, decision)
    if fwd:
        why = forward_why(wj)
    t = {
        "fly_tip": m.get("fly_tip"),
        "confidence": m.get("confidence"),
        "what_you_see": m.get("what_you_see"),
        "reason": m.get("reason"),
        "size": size, "waste_type": waste, "land_type": land, "hazards": hazards,
        "model_decision": m.get("decision") if m.get("decision") != "review" else None,
        "decision": decision,
        "decision_why": why,
        "context_flags": flags,
        "whose_job": wj,
        "forward_to": fwd,
        "hotspot": hs,
        "model": m.get("model") or MODEL_NAME,
        "seconds": m.get("seconds"),
        "source": "cache" if m.get("cached") else ("offline" if m.get("offline") else "model"),
    }
    t["headline_alert"] = headline_alert(t)
    return t
