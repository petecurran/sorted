"""WasteDataFlow quarterly fly-tipping return (Defra categories), with totals checks and a CSV in form order.

No cost figures: WasteDataFlow fills in costs for the smaller sizes itself (content/costs.json is not used here).
"""

from __future__ import annotations

import csv
import io
import re
from datetime import date

from common import CASE_REF_PREFIX, COUNCIL_NAME, LAND, SIZES, WASTE, config, now_iso, parse_dt

MONTHS = [
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


def _fmt(d: date) -> str:
    return f"{d.day} {MONTHS[d.month - 1]} {d.year}"


def quarter(qid: str | None) -> dict:
    """Quarter from content/config.json when it matches; otherwise derived from 'YYYY-Qn' (financial year)."""
    cfg_q = config()["quarter"]
    if not qid or qid == cfg_q.get("id"):
        q = dict(cfg_q)
    else:
        m = re.fullmatch(r"(\d{4})-Q([1-4])", qid.strip())
        if not m:
            q = dict(cfg_q)
        else:
            fy, n = int(m.group(1)), int(m.group(2))
            y = fy if n < 4 else fy + 1
            sm = {1: 4, 2: 7, 3: 10, 4: 1}[n]
            start = date(y, sm, 1)
            em = sm + 2
            end = date(y, em, [31, 29 if y % 4 == 0 else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][em - 1])
            dm, dy = (em + 1, y) if em < 12 else (1, y + 1)
            q = {
                "id": qid,
                "label": f"{MONTHS[sm - 1]}–{MONTHS[em - 1]} {y}",
                "start": start.isoformat(),
                "end": end.isoformat(),
                "deadline": date(dy, dm, 25).isoformat(),
            }
    q.setdefault("name", f"Q{q['id'][-1]} {q['id'][:4]}/{str(int(q['id'][:4]) + 1)[2:]}")
    return q


def _in(d_iso, start: date, end: date) -> bool:
    d = parse_dt(d_iso)
    return d is not None and start <= d.date() <= end


def build(incidents: list[dict], actions: list[dict], qid: str | None = None) -> dict:
    q = quarter(qid)
    start, end = date.fromisoformat(q["start"]), date.fromisoformat(q["end"])

    counted = [
        i
        for i in incidents
        if i.get("triage")
        and (i["triage"].get("fly_tip") or "unsure") != "no"
        and i["status"] != "not_fly_tip"
        and _in(i["created_at"], start, end)
    ]
    land = {k: 0 for k in LAND}
    waste = {k: 0 for k in WASTE}
    size = {k: {"count": 0} for k in SIZES}
    for i in counted:
        t = i["triage"]
        land[t.get("land_type") if t.get("land_type") in land else "Other (unidentified)"] += 1
        waste[t.get("waste_type") if t.get("waste_type") in waste else "Other (unidentified)"] += 1
        if t.get("size") in size:
            size[t["size"]]["count"] += 1

    counted_ids = {i["id"] for i in counted}
    investigated = {i["id"] for i in counted if i["status"] == "held"}
    ew = {"warning_letter": 0, "statutory_notice": 0, "fpn": 0, "prosecution": 0}
    for a in actions:
        if a["action"] in ("hold", "inspect") and a["incident_id"] in counted_ids:
            investigated.add(a["incident_id"])
        if a["action"] in ew and _in(a["at"], start, end):
            ew[a["action"]] += 1
    acts = {
        "investigations": len(investigated),
        "warning_letters": ew["warning_letter"],
        "statutory_notices": ew["statutory_notice"],
        "fixed_penalty_notices": ew["fpn"],
        "prosecutions": ew["prosecution"],
    }

    total = len(counted)
    ls, ws, ss = sum(land.values()), sum(waste.values()), sum(v["count"] for v in size.values())
    checks = [
        {
            "name": "land_type_total",
            "ok": ls == total,
            "text": f"Incidents by land type add up to the total ({ls} of {total})",
        },
        {
            "name": "waste_type_total",
            "ok": ws == total,
            "text": f"Incidents by waste type add up to the total ({ws} of {total})",
        },
        {
            "name": "size_total",
            "ok": ss <= total,
            "text": f"Incidents by size are no more than the total ({ss} of {total})",
        },
    ]
    return {
        "authority": COUNCIL_NAME,
        "quarter": q["id"],
        "quarter_name": q.get("name"),
        "quarter_label": q.get("label"),
        "period": f"{_fmt(start)} to {_fmt(end)}",
        "period_start": q["start"],
        "period_end": q["end"],
        "deadline": q["deadline"],
        "deadline_label": f"Due {_fmt(date.fromisoformat(q['deadline']))}",
        "total_incidents": total,
        "land_type": land,
        "waste_type": waste,
        "size": size,
        "actions": acts,
        "checks": checks,
        "all_checks_ok": all(c["ok"] for c in checks),
        "generated_at": now_iso(),
    }


# The WasteDataFlow form asks for the actual clearance cost only for the two largest sizes.
COST_ROWS = ("Tipper lorry load", "Significant/multiple loads")
ACTION_ROWS = (
    ("investigations", "Investigations"),
    ("warning_letters", "Warning letters"),
    ("statutory_notices", "Statutory notices"),
    ("fixed_penalty_notices", "Fixed penalty notices"),
    ("prosecutions", "Prosecutions"),
)


def _fy(r: dict) -> tuple[str, str]:
    """('2026-27', 'Q2') for quarter id '2026-Q2'."""
    fy, n = r["quarter"].split("-Q")
    return f"{fy}-{str(int(fy) + 1)[2:]}", f"Q{n}"


def csv_filename(r: dict) -> str:
    fy, q = _fy(r)
    return f"{CASE_REF_PREFIX.split('-')[0]}_flytipping_return_{fy}_{q}.csv"


def to_csv(r: dict) -> str:
    """Mirrors the WasteDataFlow fly-tipping form, in order: header lines, a blank line, then one row per question."""
    start, end = date.fromisoformat(r["period_start"]), date.fromisoformat(r["period_end"])
    fy, q = _fy(r)
    period = f"{q} {fy.replace('-', '/')} ({MONTHS[start.month - 1]} to {MONTHS[end.month - 1]} {end.year})"
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\r\n")
    w.writerow(["Authority", r["authority"]])
    w.writerow(["Period", period])
    w.writerow(["Submission deadline", _fmt(date.fromisoformat(r["deadline"]))])
    w.writerow([])
    w.writerow(["Section", "Question", "Category", "Number of incidents", "Clearance cost (£)"])
    w.writerow(["3.3.1", "Total incidents", "All incidents", int(r["total_incidents"] or 0), ""])
    for k in LAND:
        w.writerow(["3.3.2", "Number of incidents by land type", k, int(r["land_type"].get(k) or 0), ""])
    for k in WASTE:
        w.writerow(["3.3.3", "Number of incidents by primary waste type", k, int(r["waste_type"].get(k) or 0), ""])
    for k in SIZES:
        v = r["size"].get(k) or {}
        n = v.get("count", 0) if isinstance(v, dict) else v
        w.writerow(
            ["3.3.4", "Number of incidents by size", k, int(n or 0), "Enter actual cost" if k in COST_ROWS else ""]
        )
    for key, label in ACTION_ROWS:
        w.writerow(["3.5.1", "Number of actions taken", label, int(r["actions"].get(key) or 0), ""])
    return buf.getvalue()
