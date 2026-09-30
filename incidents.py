"""Incident lifecycle: report intake and merging, classification results, officer actions, and demo seeding."""
from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import db
import geo
import photos
import priority
import triage
from classifier import classifier, cache_lookup, normalise, offline_result
from common import (APP, LAND, OPEN_EXCLUDED, SEED, SIZES, WASTE, case_ref, config, haversine_m, iso, log, now_iso,
                    parse_dt, plus, seed)

MERGE_RADIUS_M = 40
MERGE_DAYS = 21
PHOTO_GPS_MAX_KM = 30  # EXIF GPS further than this from the city is ignored in favour of the device/map location

ACTIONS = ("schedule", "hold", "inspect", "clear", "not_fly_tip", "forward", "override", "warning_letter", "fpn",
           "prosecution", "reopen")
# While an incident is closed every action except "reopen" is refused (error "closed", 409): an officer reopens first.
CLOSED_STATUSES = ("cleared", "not_fly_tip", "forwarded")
ENFORCEMENT = {"warning_letter": "Warning letter sent", "fpn": "Fixed penalty notice issued",
               "prosecution": "Referred for prosecution"}
DECISIONS = ("clear_now", "hold_for_officer", "specialist", "not_a_fly_tip", "review")
TRIAGED_TEXT = {
    "clear_now": "Checked. Crew to clear today.",
    "hold_for_officer": "Checked. Officer to inspect before clearance.",
    "specialist": "Checked. Specialist removal needed.",
    "review": "Checked. Officer review needed.",
    "not_a_fly_tip": "Checked. Not fly-tipping.",
}
DECISION_LABEL = {"clear_now": "Crew today", "hold_for_officer": "Officer to inspect",
                  "specialist": "Specialist removal", "review": "Needs review", "not_a_fly_tip": "Not fly-tipping"}
DECISION_LABEL_V2 = DECISION_LABEL
PUBLIC_TRIAGE_DROP = ("cost", "decision_why", "context_flags", "raw_text", "overridden", "ai_original", "forward_to",
                      "headline_alert")
OVERRIDE_FIELDS = {"size": SIZES, "waste_type": WASTE, "land_type": LAND, "hazards": None}
FIELD_LABEL = {"size": "size", "waste_type": "waste type", "land_type": "land type", "hazards": "hazards"}

# Public status never reveals officer visits.
PUBLIC_STATUS_BY_DECISION = {"clear_now": "crew_booked", "hold_for_officer": "further_inspection",
                             "specialist": "further_inspection", "review": "new_report", "not_a_fly_tip": "new_report"}
PUBLIC_TEXT = {
    TRIAGED_TEXT["hold_for_officer"]: "Checked. Further inspection needed before clearance.",
    TRIAGED_TEXT["review"]: "Checked. The council is reviewing this report.",
    "Officer to inspect before clearance.": "Further inspection needed before clearance.",
    "Site inspected by an officer.": "Site checked by the council.",
}


CLOSED_PUBLIC_HOURS = 24  # a report the council closes as not fly-tipping stays on the public map this long
PUBLIC_LABEL = {"new_report": "New report", "crew_booked": "Crew booked", "further_inspection": "Further inspection",
                "passed_on": "Passed on", "cleared": "Cleared", "closed": "Closed: not fly-tipping"}


def public_status(inc: dict) -> str:
    st = inc["status"]
    if st == "triaging":
        return "new_report"
    if st == "cleared":
        return "cleared"
    if st == "not_fly_tip":
        return "closed"
    if st == "forwarded":
        return "passed_on"
    if st == "scheduled":
        return "crew_booked"
    if st == "held":
        return "further_inspection"
    # Triaged but not yet acted on: the AI's suggestion is not an action, so the public sees "New report"
    # until an officer books a crew, holds it for inspection, forwards it or clears it.
    return "new_report"


def _forward_body(t: dict | None) -> str | None:
    t = t or {}
    return t.get("forward_to") or (t.get("whose_job") or {}).get("body")


def public_label(inc: dict, ps: str) -> str:
    if ps == "passed_on":
        body = _forward_body(inc.get("triage"))
        return f"Passed to {body}" if body else PUBLIC_LABEL["passed_on"]
    return PUBLIC_LABEL.get(ps, "New report")


def _passed_public(text: str) -> str:
    """'Passed to Network Rail' -> 'Passed to Network Rail, who are responsible for this land'."""
    area = "area" if "council" in text.lower() else "land"
    return f"{text}, who are responsible for this {area}"


def closed_at(inc: dict, tl: list[dict]) -> str | None:
    """When a not_fly_tip incident was closed: the last council note or triage entry on its timeline."""
    if inc["status"] != "not_fly_tip":
        return None
    at = [e["at"] for e in tl or [] if e["kind"] in ("note", "triaged")]
    return max(at, key=lambda x: parse_dt(x) or datetime.min.replace(tzinfo=timezone.utc)) if at else inc["updated_at"]


def _public_text(kind: str, text: str) -> str:
    if text in PUBLIC_TEXT:
        return PUBLIC_TEXT[text]
    if kind == "forwarded" and text.startswith("Passed to "):
        return _passed_public(text)
    if kind == "note" and text.startswith("Officer"):
        return "Assessment updated by the council."
    return text

_write = threading.RLock()  # serialises read-modify-write on incidents across request and classifier threads


class ActionError(ValueError):
    def __init__(self, code, status=400):
        super().__init__(code)
        self.code, self.status = code, status


# ---- serialisation ------------------------------------------------------------------------------

def serialize(inc: dict, view: str, tl: list[dict] | None = None, reports: list[dict] | None = None,
              ctx: "priority.Context | None" = None) -> dict:
    council = view == "council"
    t = inc.get("triage")
    if t and ("how_we_know" not in (t.get("whose_job") or {}) or "forward_to" not in t):  # rows triaged earlier
        wj = triage.whose_job(inc["lat"], inc["lon"], t.get("land_type"))
        fwd = triage.forward_to(wj, t.get("decision"))
        t = {**t, "whose_job": wj, "forward_to": fwd}
        if fwd and not t.get("overridden"):
            t["decision_why"] = triage.forward_why(wj)
        t["headline_alert"] = triage.headline_alert(t)
    full = {**inc, "triage": t}
    if t and council:
        try:
            t = {**t, "hotspot": triage.nearby(inc["lat"], inc["lon"], now_iso(), exclude_id=inc["id"],
                                               incidents=ctx.incidents if ctx is not None and hasattr(ctx, "incidents") else None)}
        except Exception as e:  # never break the card over a hotspot recount
            log.warning("hotspot recount failed for %s: %s", inc["id"], e)
    if t and not council:
        t = {k: v for k, v in t.items() if k not in PUBLIC_TRIAGE_DROP}
    elif t:  # no cost in any API (older rows may still store one)
        t = {k: v for k, v in t.items() if k not in ("raw_text", "cost")}
    timeline = []
    for e in tl or []:
        if e["kind"] == "enforcement" and not council:
            continue
        item = {"at": e["at"], "kind": e["kind"], "text": e["text"] if council else _public_text(e["kind"], e["text"])}
        if council and e.get("note"):
            item["note"] = e["note"]
        timeline.append(item)
    if ctx is None:
        ctx = _context()
    pr = priority.compute(inc, ctx)
    seen = [r["created_at"] for r in ctx.reports_by_inc.get(inc["id"], [])] + \
        [c["at"] for c in ctx.conf_by_inc.get(inc["id"], []) if c["still_there"]]
    ps = public_status(full)
    out = {
        "id": inc["id"], "case_ref": case_ref(inc["id"]), "public_status": ps, "public_label": public_label(full, ps),
        "authority": geo.authority_for(inc["lat"], inc["lon"]),
        "lat": inc["lat"], "lon": inc["lon"], "street": inc.get("street"), "ward": inc.get("ward"),
        "created_at": inc["created_at"], "updated_at": inc["updated_at"], "status": inc["status"],
        "report_count": inc["report_count"], "photo_url": inc.get("photo_url"),
        "cleared_photo_url": inc.get("cleared_photo_url"), "cleared_at": inc.get("cleared_at"),
        "public_summary": inc.get("public_summary") or ("Photo being checked" if inc["status"] == "triaging"
                                                         else "Reported fly-tipping"),
        "triage": t, "timeline": timeline,
        "still_there_count": pr["still_there_count"], "gone_count": pr["gone_count"],
        "last_seen_at": max(seen, key=lambda x: parse_dt(x) or datetime.min.replace(tzinfo=timezone.utc)) if seen else inc["created_at"],
        "priority": pr["priority"], "growing": pr["growing"],
    }
    out["closed_at"] = closed_at(inc, tl)  # None unless closed as not fly-tipping (so None again after a reopen)
    if council:
        out["description"] = inc.get("description")
        out["seed_key"] = inc.get("seed_key")
        out["forward_to"] = (full.get("triage") or {}).get("forward_to")
        if reports is None:
            reports = ctx.reports_by_inc.get(inc["id"], [])
        # every merged report, oldest first, for the photo carousel (seeded extra reports have no photo)
        out["reports"] = [{"id": r["id"], "created_at": r["created_at"], "photo_url": r.get("photo_url"),
                           "description": r.get("description"), "loc_source": r.get("loc_source"),
                           "reporter": r.get("reporter")} for r in reports]
    return out


def _context(incs: list[dict] | None = None, reports: list[dict] | None = None) -> "priority.Context":
    return priority.Context(incs if incs is not None else db.list_incidents(),
                            reports if reports is not None else db.all_reports(), db.all_confirmations())


def get(iid: int, view: str) -> dict | None:
    inc = db.get_incident(iid)
    if not inc:
        return None
    all_reps = db.all_reports()
    reps = [r for r in all_reps if r["incident_id"] == iid] if view == "council" else None
    return serialize(inc, view, db.timelines([iid]).get(iid, []), reps, _context(reports=all_reps))


def list_all(view: str) -> list[dict]:
    incs = db.list_incidents()
    tls = db.timelines()
    ctx = _context(incs)
    if view != "council":
        cutoff = datetime.now(timezone.utc) - timedelta(hours=CLOSED_PUBLIC_HOURS)
        incs = [i for i in incs if i["status"] != "not_fly_tip" or
                (parse_dt(closed_at(i, tls.get(i["id"], []))) or cutoff) > cutoff]
    out = [serialize(i, view, tls.get(i["id"], []), ctx=ctx) for i in incs]
    if view == "council":  # priority first, then newest (the DB order is newest first, and sort is stable)
        out.sort(key=lambda i: -i["priority"]["score"])
    return out


def confirm(iid: int, still_there: bool) -> dict:
    """Waze-style "Is it still there?" from a resident. Returns the updated public incident."""
    with _write:
        inc = db.get_incident(iid)
        if not inc:
            raise ActionError("not_found", 404)
        when = now_iso()
        db.add_confirmation(iid, still_there, at=when)
        db.add_timeline(iid, "confirmed", "Resident confirmed it is still there." if still_there
                        else "Resident reported it has gone.", at=when)
        db.update_incident(iid, touch=when)
    return get(iid, "public")


# ---- classification -----------------------------------------------------------------------------

def apply_classification(iid: int, result: dict, at: str | None = None):
    with _write:
        inc = db.get_incident(iid)
        if not inc:
            return
        if (inc.get("triage") or {}).get("overridden"):
            log.info("incident %s already overridden by an officer; model result kept as raw only", iid)
            db.update_incident(iid, model_raw={k: v for k, v in result.items() if k != "raw_text"})
            return
        t = triage.run(result, lat=inc["lat"], lon=inc["lon"], ward=inc.get("ward"), incident_id=iid,
                       created_at=inc["created_at"], incidents=db.list_incidents())
        summary = triage.public_summary(t.get("what_you_see"), fallback=inc.get("public_summary") or
                                        _desc_summary(inc.get("description")))
        status = "triaged" if inc["status"] == "triaging" else inc["status"]
        # Only a rule-level "not fly-tipping" (a booked bulky collection) closes the incident automatically. When
        # the model alone says no, the decision is "review" and a person checks it (it stays in the queue).
        if inc["status"] == "triaging" and t["decision"] == "not_a_fly_tip" and \
                any(f.get("kind") == "bulky_booking" for f in t.get("context_flags") or []):
            status = "not_fly_tip"
        when = at or now_iso()
        db.update_incident(iid, touch=when, triage=t, model_raw={k: v for k, v in result.items() if k != "raw_text"},
                           public_summary=summary, status=status)
        text = (f"Checked. {t['forward_to']} must clear it."
                if t.get("forward_to") else TRIAGED_TEXT.get(t["decision"], "Checked."))
        db.add_timeline(iid, "triaged", text, at=when)
    log.info("incident %s triaged: %s (%s)", iid, t["decision"], t.get("source"))


def _desc_summary(desc: str | None) -> str:
    d = (desc or "").strip()
    return (d[:60].rsplit(" ", 1)[0] + "…") if len(d) > 60 else (d or "Reported fly-tipping")


def classify(iid: int, sha: str, path: str, stage: bool = False) -> str:
    return classifier.submit(iid, sha, path, lambda r: apply_classification(iid, r), stage=stage)


# ---- reports ------------------------------------------------------------------------------------

def _num(v) -> float | None:
    try:
        f = float(v)
        return f if f == f else None
    except (TypeError, ValueError):
        return None


def find_merge_target(lat, lon, now: datetime | None = None) -> dict | None:
    now = now or datetime.now(timezone.utc)
    best, best_d = None, None
    for inc in db.list_incidents():
        if inc["status"] in OPEN_EXCLUDED:
            continue
        c = parse_dt(inc["created_at"])
        if c is None or now - c > timedelta(days=MERGE_DAYS):
            continue
        d = haversine_m(lat, lon, inc["lat"], inc["lon"])
        if d <= MERGE_RADIUS_M and (best_d is None or d < best_d):
            best, best_d = inc, d
    return best


def submit_report(data: bytes, lat=None, lon=None, loc_source=None, description=None, reporter=None,
                  stage: bool = False) -> dict:
    ph = photos.process(data)
    lat, lon = _num(lat), _num(lon)
    source = loc_source if loc_source in ("device", "map") else ("device" if lat is not None else None)
    if ph["gps"]:
        glat, glon = ph["gps"]
        dep = config()["depot"]
        near_city = haversine_m(glat, glon, dep["lat"], dep["lon"]) <= PHOTO_GPS_MAX_KM * 1000
        if near_city or lat is None or lon is None:
            lat, lon, source = glat, glon, "photo"
    if lat is None or lon is None:
        raise ActionError("no_location", 422)
    description = (description or "").strip()[:1000] or None
    reporter = (reporter or "").strip()[:120] or None

    with _write:
        target = find_merge_target(lat, lon)
        if target:
            iid = target["id"]
            rid = db.add_report(iid, lat=lat, lon=lon, loc_source=source, description=description,
                                reporter=reporter, photo_url=ph["url"], photo_sha=ph["sha"])
            db.update_incident(iid, report_count=target["report_count"] + 1,
                               **({} if target.get("photo_url") else {"photo_url": ph["url"], "photo_path": ph["path"]}))
            db.add_timeline(iid, "merged", "Reported by another resident.", note=description)
            merged = True
            needs_triage = not target.get("triage") and not classifier.is_pending(iid)
        else:
            iid = db.insert_incident(lat=lat, lon=lon, street=geo.street_for(lat, lon), ward=geo.ward_for(lat, lon),
                                     status="triaging", report_count=1, photo_url=ph["url"], photo_path=ph["path"],
                                     photo_sha=ph["sha"], description=description,
                                     public_summary=_desc_summary(description) if description else None)
            rid = db.add_report(iid, lat=lat, lon=lon, loc_source=source, description=description,
                                reporter=reporter, photo_url=ph["url"], photo_sha=ph["sha"])
            db.add_timeline(iid, "reported", "Reported by a resident", note=description)
            merged = False
            needs_triage = True
    if needs_triage:
        classify(iid, ph["sha"], ph["path"], stage=stage)
    inc = db.get_incident(iid)
    return {"report_id": rid, "incident_id": iid, "merged": merged, "others_count": inc["report_count"] - 1,
            "location": {"lat": lat, "lon": lon, "source": source}, "status": inc["status"],
            "photo_url": ph["url"]}


# ---- actions ------------------------------------------------------------------------------------

def _override_triage(inc: dict, decision: str | None, fields: dict, when: str, note: str | None) -> tuple[dict, list]:
    """Re-run the rules with officer-corrected Defra fields (and optionally a forced decision)."""
    old = dict(inc.get("triage") or {})
    ai_original = old.get("ai_original") or {k: old.get(k) for k in ("size", "waste_type", "land_type", "hazards",
                                                                      "decision")}
    prev_over = old.get("overridden") if isinstance(old.get("overridden"), list) else []
    base = dict(inc.get("model_raw") or {})
    for k in ("fly_tip", "confidence", "what_you_see", "reason", "size", "waste_type", "land_type", "hazards",
              "model", "seconds"):
        if k in old and k not in fields:
            base[k] = old[k]
    base.update(fields)
    base.pop("offline", None)
    if base.get("fly_tip") != "yes" and fields:
        base["fly_tip"] = "yes"  # an officer who sets the Defra fields has confirmed it is fly-tipping
    t = triage.run(base, lat=inc["lat"], lon=inc["lon"], ward=inc.get("ward"), incident_id=inc["id"],
                   created_at=inc["created_at"], incidents=db.list_incidents())
    changed = [k for k in OVERRIDE_FIELDS if k in fields and fields[k] != old.get(k)]
    if decision:
        t["decision"] = decision
        t["decision_why"] = "Decision changed by officer." + (f" Note: {note}" if note else "")
        if decision != old.get("decision"):
            changed.append("decision")
    elif fields:
        t["decision_why"] = f"Officer corrections applied. {t['decision_why']}"
    t["overridden"] = sorted(set(prev_over) | set(changed) | (set(fields) if fields else set()) |
                             ({"decision"} if decision else set()), key=list(OVERRIDE_FIELDS).__add__(["decision"]).index)
    t["ai_original"] = ai_original
    t["overridden_at"] = when
    t["overridden_note"] = note
    t["model_decision"] = old.get("model_decision")
    if decision:  # a forced decision: forward only if it is still someone else's job to clear
        t["forward_to"] = triage.forward_to(t.get("whose_job"), decision)
    t["headline_alert"] = triage.headline_alert(t)
    t["seconds"], t["model"], t["source"] = old.get("seconds"), old.get("model", t.get("model")), old.get("source", t.get("source"))
    return t, changed


def apply_action(iid: int, action: str, note: str | None = None, decision: str | None = None,
                 photo_bytes: bytes | None = None, photo_url: str | None = None, at: str | None = None,
                 fields: dict | None = None, allow_closed: bool = False) -> dict:
    """allow_closed is only for replaying seed history (e.g. a prosecution recorded after the clearance)."""
    if action not in ACTIONS:
        raise ActionError("unknown_action")
    note = (note or "").strip()[:1000] or None
    with _write:
        inc = db.get_incident(iid)
        if not inc:
            raise ActionError("not_found", 404)
        closed = inc["status"] in CLOSED_STATUSES
        if action == "reopen" and not closed:
            raise ActionError("not_closed", 409)
        if action != "reopen" and closed and not allow_closed:
            raise ActionError("closed", 409)
        when = at or now_iso()
        upd: dict = {}
        if action == "reopen":
            upd.update(status="triaged", cleared_at=None, cleared_photo_url=None)
            db.add_timeline(iid, "reopened", "Reopened", at=when, note=note)
        elif action == "schedule":
            upd["status"] = "scheduled"
            db.add_timeline(iid, "scheduled", "Crew booked.", at=when, note=note)
        elif action == "hold":
            upd["status"] = "held"
            db.add_timeline(iid, "held", "Officer to inspect before clearance.", at=when, note=note)
        elif action == "inspect":
            if inc["status"] in ("triaging", "triaged", "scheduled"):
                upd["status"] = "held"
            db.add_timeline(iid, "inspected", "Site inspected by an officer.", at=when, note=note)
        elif action == "clear":
            if photo_bytes:
                photo_url = photos.process(photo_bytes, prefix="after_")["url"]
            upd.update(status="cleared", cleared_at=when)
            if photo_url:
                upd["cleared_photo_url"] = photo_url
            db.add_timeline(iid, "cleared", "Cleared by the council.", at=when, note=note)
        elif action == "not_fly_tip":
            upd["status"] = "not_fly_tip"
            db.add_timeline(iid, "note", "Checked by the council. Not fly-tipping.", at=when, note=note)
        elif action == "forward":
            t = inc.get("triage") or {}
            body = t.get("forward_to") or triage.forward_to(t.get("whose_job"), "clear_now")
            if not body:
                raise ActionError("nothing_to_forward")
            if not t.get("forward_to"):
                upd["triage"] = {**t, "forward_to": body}
            upd["status"] = "forwarded"  # not triaged/scheduled/held, so it leaves the crew and officer routes
            db.add_timeline(iid, "forwarded", f"Passed to {body}", at=when, note=note)
        elif action == "override":
            fields = {k: v for k, v in (fields or {}).items() if k in OVERRIDE_FIELDS and v not in (None, "")}
            for k, v in fields.items():
                opts = OVERRIDE_FIELDS[k]
                if opts is None:
                    fields[k] = str(v).strip()[:300]
                elif v not in opts:
                    raise ActionError(f"bad_{k}")
            if decision in (None, ""):
                decision = None
            elif decision not in DECISIONS:
                raise ActionError("bad_decision")
            if not decision and not fields:
                raise ActionError("nothing_to_override")
            prev = (inc.get("triage") or {}).get("decision")
            t, changed = _override_triage(inc, decision, fields, when, note)
            decision = t["decision"]
            upd["triage"] = t
            if decision == "not_a_fly_tip":
                upd["status"] = "not_fly_tip"
            elif inc["status"] in ("triaging", "not_fly_tip", "forwarded") or \
                    (decision == "clear_now" and inc["status"] == "held"):
                upd["status"] = "triaged"
            elif decision in ("hold_for_officer", "specialist", "review") and inc["status"] == "scheduled":
                upd["status"] = "triaged"
            parts = []
            fchanged = [FIELD_LABEL[k] for k in changed if k in FIELD_LABEL]
            if fchanged:
                parts.append("Officer corrected the " + (", ".join(fchanged[:-1]) + " and " + fchanged[-1]
                                                         if len(fchanged) > 1 else fchanged[0]) + ".")
            if decision != prev:
                parts.append(f"{'Decision' if parts else 'Officer changed the decision'} "
                             f"{'changed ' if parts else ''}to {DECISION_LABEL_V2[decision]}.")
            text = " ".join(parts) if parts else "Officer confirmed the AI assessment."
            db.add_timeline(iid, "note", text, at=when, note=note)
        else:
            db.add_timeline(iid, "enforcement", ENFORCEMENT[action], at=when, note=note)
        db.add_action(iid, action, at=when, note=note, decision=decision)
        db.update_incident(iid, touch=when, **upd)
    return get(iid, "council")


# ---- seeding ------------------------------------------------------------------------------------

def _seed_photo_url(rel: str | None) -> tuple[str | None, str | None, str | None]:
    """(url, local_path, sha) for a seed photo path like 'seed/photos/x.jpg'."""
    if not rel:
        return None, None, None
    p = Path(rel)
    p = p if p.is_absolute() else APP / p
    if not p.exists():
        alt = SEED / "photos" / Path(rel).name
        if alt.exists():
            p = alt
        else:
            log.warning("seed photo missing: %s", rel)
            return None, None, None
    try:
        root = (SEED / "photos").resolve()
        if p.resolve().is_relative_to(root):
            import hashlib
            rel_url = p.resolve().relative_to(root).as_posix()
            return f"/media/seed/{rel_url}", str(p), hashlib.sha256(p.read_bytes()).hexdigest()
        ph = photos.process(p.read_bytes())
        return ph["url"], ph["path"], ph["sha"]
    except Exception as e:
        log.warning("seed photo unreadable %s: %s", rel, e)
        return None, None, None


def _after_photo(key: str | None) -> Path | None:
    """Team-made "after" image for a seed incident: seed/photos/after/<key>.jpg (wins over the action's photo)."""
    if not key:
        return None
    for ext in (".jpg", ".jpeg", ".png", ".webp"):
        p = SEED / "photos" / "after" / f"{key}{ext}"
        if p.exists():
            return p
    return None


def seed_demo() -> int:
    recs = seed("demo_incidents.json", []) or []
    if not isinstance(recs, list) or not recs:
        log.info("no seed/demo_incidents.json records; starting empty")
        return 0
    now = now_iso()
    recs = sorted(recs, key=lambda r: str(r.get("created_at") or now))
    made = []
    for r in recs:
        try:
            lat, lon = float(r["lat"]), float(r["lon"])
        except (KeyError, TypeError, ValueError):
            log.warning("seed record %s has no location; skipped", r.get("key"))
            continue
        created = r.get("created_at") or now
        url, path, sha = _seed_photo_url(r.get("photo"))
        n = max(1, int(r.get("report_count") or 1))
        desc = r.get("description")
        iid = db.insert_incident(lat=lat, lon=lon, street=r.get("street") or geo.street_for(lat, lon),
                                 ward=r.get("ward") or geo.ward_for(lat, lon), status="triaging", report_count=n,
                                 photo_url=url, photo_path=path, photo_sha=sha, description=desc,
                                 created_at=created, updated_at=created, seed_key=r.get("key"))
        db.add_report(iid, created_at=created, lat=lat, lon=lon, loc_source="device", description=desc,
                      photo_url=url, photo_sha=sha)
        db.add_timeline(iid, "reported", "Reported by a resident", at=created)
        first_action = min((a.get("at") for a in r.get("actions") or [] if a.get("at")), default=None)
        for k in range(1, n):
            t = plus(created, minutes=40 * k)
            if first_action and t >= first_action:
                t = plus(first_action, seconds=-30 * (n - k))
            if t > now:
                t = now
            db.add_report(iid, created_at=t, lat=lat, lon=lon, loc_source="device")
            db.add_timeline(iid, "merged", "Reported by another resident.", at=t)
        made.append((iid, r, sha, path))

    for iid, r, sha, path in made:
        m = r.get("model")
        if isinstance(m, dict) and m:
            result = normalise(m)
            result["seconds"] = m.get("seconds", result.get("seconds"))
        else:
            result = cache_lookup(sha) if sha else None
        created = db.get_incident(iid)["created_at"]
        if result is not None:
            apply_classification(iid, result, at=plus(created, seconds=float(result.get("seconds") or 11)))
        elif path:
            classify(iid, sha, path)  # queued until the worker starts
        else:
            apply_classification(iid, offline_result(), at=plus(created, seconds=5))
        after = _after_photo(r.get("key"))
        for a in r.get("actions") or []:
            try:
                purl = _seed_photo_url(a.get("photo"))[0] if a.get("photo") else None
                if a.get("action") == "clear" and after:
                    purl = _seed_photo_url(str(after))[0] or purl
                apply_action(iid, a.get("action"), note=a.get("note"), decision=a.get("decision"),
                             photo_url=purl, at=a.get("at"), allow_closed=True)
            except ActionError as e:
                log.warning("seed %s action %s failed: %s", r.get("key"), a.get("action"), e.code)
    log.info("seeded %d demo incidents", len(made))
    return len(made)
