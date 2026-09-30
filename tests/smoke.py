"""End-to-end smoke test: start the server (FT_RESET=1), post a photo, poll until triaged, hit every endpoint.

Run from the repo root:   FT_CLASSIFIER=cache uv run python tests/smoke.py
Env: FT_PORT (default 8810, so it never clashes with the demo server on 8800), FT_DATA_DIR (default: a fresh temp
dir, so the demo's data/app.db is never touched), FT_CLASSIFIER (default gemma), SMOKE_PHOTO, SMOKE_TIMEOUT.
"""

from __future__ import annotations

import io
import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import requests
from PIL import Image

APP = Path(__file__).resolve().parents[1]
PORT = int(os.environ.get("FT_PORT", "8810"))
DATA_DIR = Path(os.environ.get("FT_DATA_DIR") or tempfile.mkdtemp(prefix="ft_smoke_"))
BASE = f"http://127.0.0.1:{PORT}"
PHOTO = Path(os.environ.get("SMOKE_PHOTO", APP / "seed/live_demo/4_mattress_makin_street.jpg"))
MODE = os.environ.get("FT_CLASSIFIER", "gemma")
TIMEOUT = float(os.environ.get("SMOKE_TIMEOUT", "240" if MODE == "gemma" else "30"))

results: list[tuple[str, bool, str]] = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), str(detail)[:160]))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}  {str(detail)[:160]}", flush=True)
    return ok


def get(path, **kw):
    return requests.get(BASE + path, timeout=30, **kw)


def port_free(port):
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def main():
    if not port_free(PORT):
        print(f"port {PORT} is busy: stop the other server or set FT_PORT", file=sys.stderr)
        return 2
    if DATA_DIR.resolve() == (APP / "data").resolve():
        print("refusing to reset the demo data dir; set FT_DATA_DIR to a temp dir", file=sys.stderr)
        return 2
    subprocess.run(
        [sys.executable, str(APP / "scripts/build_seed.py")], check=True, stdout=subprocess.DEVNULL
    )  # fresh data for today
    env = {**os.environ, "FT_RESET": "1", "FT_CLASSIFIER": MODE, "FT_DATA_DIR": str(DATA_DIR)}
    log = open(DATA_DIR / "smoke_server.log", "w")
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "server:app", "--host", "127.0.0.1", "--port", str(PORT)],
        cwd=APP,
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    t0 = time.time()
    try:
        return run(proc, t0)
    finally:
        os.killpg(proc.pid, signal.SIGTERM)
        try:
            proc.wait(10)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
        print(f"\nserver stopped; log at {DATA_DIR / 'smoke_server.log'}")


V2_FIELDS = (
    "case_ref",
    "public_status",
    "public_label",
    "authority",
    "still_there_count",
    "gone_count",
    "last_seen_at",
    "priority",
    "growing",
)
PUBLIC_STATUSES = ("new_report", "crew_booked", "further_inspection", "passed_on", "cleared", "closed")


def cost_keys(obj, path=""):
    """Every key anywhere in a JSON value whose name mentions cost."""
    out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if "cost" in str(k).lower():
                out.append(f"{path}.{k}")
            out += cost_keys(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for n, v in enumerate(obj):
            out += cost_keys(v, f"{path}[{n}]")
    return out


CSV_HEAD = [
    "Authority,Mersey Vale City Council",
    "Period,Q2 2026/27 (July to September 2026)",
    "Submission deadline,25 October 2026",
    "",
]


def csv_checks():
    import csv as _csv

    r = get("/api/return.csv")
    check(
        "return.csv filename",
        r.headers.get("content-disposition") == 'attachment; filename="MVCC_flytipping_return_2026-27_Q2.csv"',
        r.headers.get("content-disposition"),
    )
    text = r.content.decode("utf-8-sig")
    lines = text.splitlines()
    check("return.csv header lines", lines[:4] == CSV_HEAD, lines[:4])
    rows = list(_csv.reader(lines[4:]))
    head, body = rows[0], rows[1:]
    check(
        "return.csv columns",
        head == ["Section", "Question", "Category", "Number of incidents", "Clearance cost (£)"],
        head,
    )
    sections = [row[0] for row in body]
    want = ["3.3.1"] + ["3.3.2"] * 10 + ["3.3.3"] * 15 + ["3.3.4"] * 7 + ["3.5.1"] * 5
    check("return.csv sections in form order", sections == want, f"{len(body)} rows")
    check("return.csv counts are integers, zeros not blanks", all(row[3].isdigit() for row in body), "")
    costed = [row[2] for row in body if row[4]]
    check(
        "return.csv clearance cost only for the two largest sizes",
        costed == ["Tipper lorry load", "Significant/multiple loads"]
        and all(row[4] == "Enter actual cost" for row in body if row[4]),
        costed,
    )
    ret = get("/api/return").json()
    check("return.csv total matches /api/return", body[0][3] == str(ret["total_incidents"]), body[0])
    check(
        "return.csv actions rows",
        [row[2] for row in body[-5:]]
        == ["Investigations", "Warning letters", "Statutory notices", "Fixed penalty notices", "Prosecutions"],
        "",
    )


def no_cost_checks():
    for path in (
        "/api/return",
        "/api/hotspots",
        "/api/reduce",
        "/api/incidents?view=council",
        "/api/incidents?view=public",
        "/api/routes?team=crew",
        "/api/routes?team=officer",
    ):
        keys = cost_keys(get(path).json())
        check(f"no cost fields in {path}", not keys, keys[:4])


def trust_checks():
    """Only this laptop reaches the council console without a password (trust.py). A phone, another site's page open
    in this browser, or a DNS-rebound name is asked to sign in, and still gets the public site."""
    council = "/api/incidents?view=council"
    phone = {"cf-connecting-ip": "203.0.113.9"}
    check("trust: this laptop reads the council list", get(council).status_code == 200)
    for who, headers in (
        ("a phone through the tunnel", phone),
        ("another site's page", {"Origin": "https://evil.example"}),
        ("a DNS-rebound name", {"Host": "rebind.evil.example"}),
    ):
        r = get(council, headers=headers)
        check(f"trust: {who} is asked to sign in", r.status_code == 401 and r.json().get("error") == "sign_in", r.text)
    target = get(council).json()[0]
    r = requests.post(
        BASE + f"/api/incidents/{target['id']}/actions",
        json={"action": "schedule"},
        headers={"Origin": "https://evil.example"},
        timeout=30,
    )
    after = get(f"/api/incidents/{target['id']}?view=council").json()
    check(
        "trust: another site's page cannot act on a report",
        r.status_code == 401 and after["status"] == target["status"],
        f"{r.status_code} {target['status']} -> {after['status']}",
    )
    check("trust: a phone still gets the public list", get("/api/incidents?view=public", headers=phone).ok)


def v2_checks(iid):
    council = get("/api/incidents?view=council").json()
    public = get("/api/incidents?view=public").json()
    public = public.get("incidents", []) if isinstance(public, dict) else public  # {version, incidents}
    check(
        "incident fields present",
        all(all(k in i for k in V2_FIELDS) for i in council + public),
        f"example: { ({k: council[0].get(k) for k in V2_FIELDS}) }",
    )
    check(
        "case_ref format", all(i["case_ref"] == f"MVCC-FT-2026-{i['id']:04d}" for i in council), council[0]["case_ref"]
    )
    check(
        "public_status values",
        all(i["public_status"] in PUBLIC_STATUSES for i in public),
        sorted({i["public_status"] for i in public}),
    )
    check(
        "public not_fly_tip only as recently closed",
        all(
            i["public_status"] == "closed" and i["public_label"] == "Closed: not fly-tipping"
            for i in public
            if i["status"] == "not_fly_tip"
        ),
        f"{len(public)} of {len(council)}",
    )
    check(
        "no Liverpool City Council in API",
        "Liverpool City Council" not in json.dumps(council)
        and get("/api/return").json()["authority"] == "Mersey Vale City Council",
        "",
    )
    tri = [i for i in council if i.get("triage")]
    check(
        "triage has forward_to and headline_alert",
        all("forward_to" in i["triage"] and "headline_alert" in i["triage"] and "forward_to" in i for i in tri),
        [(i["case_ref"], i["triage"]["forward_to"], i["triage"]["headline_alert"]) for i in tri[:4]],
    )
    pub_t = [i["triage"] for i in public if i.get("triage")]
    check(
        "public triage hides forward_to/headline_alert",
        all("forward_to" not in t and "headline_alert" not in t for t in pub_t),
        "",
    )
    check(
        "council list has every merged report",
        all(
            isinstance(i.get("reports"), list)
            and len(i["reports"]) == i["report_count"]
            and all({"id", "created_at", "photo_url", "description"} <= set(r) for r in i["reports"])
            for i in council
        ),
        [(i["case_ref"], i["report_count"], len(i.get("reports") or [])) for i in council[:4]],
    )
    one = get(f"/api/incidents/{iid}?view=council").json()
    check(
        "council single incident has reports",
        len(one.get("reports") or []) == one["report_count"],
        f"{len(one.get('reports') or [])} reports",
    )
    auto = [
        i
        for i in council
        if i["status"] == "not_fly_tip"
        and not any(f["kind"] == "bulky_booking" for f in (i.get("triage") or {}).get("context_flags") or [])
        and not any(e["kind"] == "note" for e in i["timeline"])
    ]
    check("model alone never auto-closes a report", not auto, [i["case_ref"] for i in auto])
    scores = [i["priority"]["score"] for i in council]
    check("council list sorted by priority", scores == sorted(scores, reverse=True), scores)
    check(
        "priority shape",
        all(
            set(i["priority"]) >= {"score", "level", "reasons"}
            and i["priority"]["level"] in ("urgent", "high", "normal", "low")
            for i in council
        ),
        [(i["case_ref"], i["priority"]["level"], i["priority"]["reasons"]) for i in council[:3]],
    )
    tri = [i for i in council if i.get("triage")]
    check(
        "whose_job.how_we_know",
        all((i["triage"].get("whose_job") or {}).get("how_we_know") for i in tri),
        tri[0]["triage"]["whose_job"]["how_we_know"] if tri else "no triaged incidents",
    )

    before = get(f"/api/incidents/{iid}?view=public").json()
    rc = requests.post(BASE + f"/api/incidents/{iid}/confirm", json={"still_there": True}, timeout=30)
    j = rc.json()
    check(
        "POST confirm still_there",
        rc.ok
        and j["still_there_count"] == before["still_there_count"] + 1
        and j["timeline"][-1]["kind"] == "confirmed"
        and "cost" not in (j.get("triage") or {}),
        f"still={j.get('still_there_count')} last_seen={j.get('last_seen_at')} {j['timeline'][-1]['text']}",
    )
    rg = requests.post(BASE + f"/api/incidents/{iid}/confirm", json={"still_there": False}, timeout=30).json()
    check("POST confirm gone", rg.get("gone_count") == 1, f"gone={rg.get('gone_count')}")
    bad = requests.post(BASE + f"/api/incidents/{iid}/confirm", json={"still_there": "yes"}, timeout=30)
    check("confirm with bad body gives 400", bad.status_code == 400, bad.text[:60])

    target = next((i for i in council if i["status"] not in ("cleared", "not_fly_tip") and i["id"] != iid), None)
    if target:
        ro = requests.post(
            BASE + f"/api/incidents/{target['id']}/actions",
            timeout=30,
            json={
                "action": "override",
                "waste_type": "Asbestos",
                "size": "Small van load",
                "hazards": "broken asbestos sheeting",
                "note": "Officer correction",
            },
        )
        t = ro.json().get("triage") or {}
        check(
            "override Defra fields re-runs rules",
            ro.ok
            and t.get("decision") == "specialist"
            and "waste_type" in t.get("overridden", [])
            and isinstance(t.get("ai_original"), dict),
            f"decision={t.get('decision')} overridden={t.get('overridden')} ai_original={t.get('ai_original')}",
        )
        check(
            "headline_alert is one hazard line",
            t.get("headline_alert") == "Possible asbestos: specialist removal",
            t.get("headline_alert"),
        )
        pub = get(f"/api/incidents/{target['id']}?view=public").json()["triage"]
        check("public view hides ai_original/overridden", "ai_original" not in pub and "overridden" not in pub, "")
        rb = requests.post(
            BASE + f"/api/incidents/{target['id']}/actions", json={"action": "override", "size": "Huge"}, timeout=30
        )
        check("override with a non-Defra size gives 400", rb.status_code == 400, rb.text[:60])

    fwd = next(
        (i for i in council if i["status"] in ("triaged", "held") and i["id"] not in (iid, (target or {}).get("id"))),
        None,
    )
    if fwd:
        rr = requests.post(
            BASE + f"/api/incidents/{fwd['id']}/actions",
            timeout=30,
            json={
                "action": "override",
                "land_type": "Railway",
                "waste_type": "Other household waste",
                "hazards": "none",
                "note": "Next to the railway fence",
            },
        )
        t = rr.json().get("triage") or {}
        check(
            "railway land recommends forwarding",
            rr.ok
            and t.get("forward_to") == "Network Rail"
            and "Network Rail land. Forward to Network Rail." in (t.get("decision_why") or ""),
            f"{t.get('forward_to')}: {t.get('decision_why')}",
        )
        crew_ids = [s["incident_id"] for s in get("/api/routes?team=crew").json()["stops"]]
        check("forward_to incident is not on the crew route", fwd["id"] not in crew_ids, crew_ids)
        rf = requests.post(BASE + f"/api/incidents/{fwd['id']}/actions", json={"action": "forward"}, timeout=30)
        j = rf.json()
        check(
            "action forward",
            rf.ok
            and j["status"] == "forwarded"
            and j["timeline"][-1]["text"] == "Passed to Network Rail"
            and j["public_status"] == "passed_on",
            f"status={j.get('status')} {j['timeline'][-1]['text']}",
        )
        pj = get(f"/api/incidents/{fwd['id']}?view=public").json()
        check(
            "public passed_on text",
            pj["public_status"] == "passed_on"
            and pj["timeline"][-1]["text"] == "Passed to Network Rail, who are responsible for this land",
            pj["timeline"][-1]["text"],
        )
        routes_ids = [
            s["incident_id"] for tm in ("crew", "officer") for s in get(f"/api/routes?team={tm}").json()["stops"]
        ]
        check("forwarded incident leaves the routes", fwd["id"] not in routes_ids, "")
        rs = requests.post(BASE + f"/api/incidents/{fwd['id']}/actions", json={"action": "schedule"}, timeout=30)
        check(
            "action on a forwarded incident gives 409 closed",
            rs.status_code == 409 and rs.json().get("error") == "closed",
            rs.text[:60],
        )
        ro = requests.post(BASE + f"/api/incidents/{fwd['id']}/actions", json={"action": "reopen"}, timeout=30)
        check(
            "reopen a forwarded incident",
            ro.ok and ro.json()["status"] == "triaged" and ro.json()["timeline"][-1]["text"] == "Reopened",
            f"{ro.status_code} {ro.json().get('status')}",
        )
        rn = requests.post(BASE + f"/api/incidents/{iid}/actions", json={"action": "forward"}, timeout=30)
        check("forward with no other body gives 400", rn.status_code == 400, rn.text[:60])

    for team in ("crew", "officer"):
        r = get(f"/api/routes?team={team}").json()
        ok = (
            all(
                k in r
                for k in ("total_drive_min", "total_km", "order_method", "geometry", "google_maps_urls", "qr_url")
            )
            and "duration_min" not in r
            and all(
                "eta_min" not in s
                and {"case_ref", "priority_level", "drive_min_from_prev", "drive_km_from_prev"} <= set(s)
                for s in r["stops"]
            )
        )
        levels = [s["priority_level"] for s in r["stops"]]
        urgent_first = levels == sorted(levels, key=lambda lv: lv != "urgent")
        check(
            f"routes shape ({team})",
            ok and urgent_first and (not r["stops"] or r["google_maps_urls"]),
            f"{r['order_method']} stops={len(r['stops'])} links={len(r['google_maps_urls'])} levels={levels}",
        )
        q = get(r["qr_url"])
        check(f"GET {r['qr_url']} is a PNG", q.ok and q.content[:8] == b"\x89PNG\r\n\x1a\n", f"{len(q.content)}B")
    q = get("/api/qr", params={"text": "https://example.org/x"})
    check("GET /api/qr?text= is a PNG", q.ok and q.content[:4] == b"\x89PNG", f"{len(q.content)}B")

    hs = get("/api/hotspots").json()
    ok = all(
        len(h["weekly_counts"]) == 12
        and isinstance(h["growing"], bool)
        and h["primary_action"]
        and len(h["primary_action"]["title"].split()) <= 8
        and "why" in h["primary_action"]
        and "evidence" in h["primary_action"]
        and isinstance(h["other_actions"], list)
        and not h.get("calendar_flags")
        for h in hs
    )
    check(
        "hotspots shape",
        ok and hs,
        f"{hs[0]['street']}: {hs[0]['weekly_counts']} -> {hs[0]['primary_action']['title']}" if hs else "none",
    )
    red = get("/api/reduce").json()
    check("reduce has no calendar cards", not red.get("calendar"), "")


def run(proc, t0):
    print(f"smoke test: classifier={MODE}, photo={PHOTO.name}, port={PORT}")
    while True:
        try:
            if get("/api/config").ok:
                break
        except requests.ConnectionError:
            pass
        if proc.poll() is not None or time.time() - t0 > 60:
            print(f"server did not start; see {DATA_DIR / 'smoke_server.log'}")
            return 1
        time.sleep(0.3)
    cfg = get("/api/config").json()
    check(
        "GET /api/config",
        cfg.get("city") and "model" in cfg and "quarter" in cfg,
        f"model={cfg['model']['status']} queue={cfg['model']['queue']} quarter={cfg['quarter']['id']}",
    )
    seeded = get("/api/incidents?view=council").json()
    check("seeded demo incidents", isinstance(seeded, list), f"{len(seeded)} incidents after reset")

    # 1. report
    with open(PHOTO, "rb") as f:
        r = requests.post(
            BASE + "/api/reports",
            files={"photo": (PHOTO.name, f, "image/jpeg")},
            data={
                "lat": "53.4084",
                "lon": "-2.9916",
                "loc_source": "device",
                "description": "Tyre at the bus stop",
                "reporter": "Smoke Test",
            },
            timeout=60,
        )
    rep = r.json()
    check("POST /api/reports", r.ok and rep.get("incident_id"), json.dumps(rep))
    iid = rep["incident_id"]

    # 2. poll
    t = time.time()
    inc = None
    while time.time() - t < TIMEOUT:
        inc = get(f"/api/incidents/{iid}?view=council").json()
        if inc.get("status") != "triaging":
            break
        time.sleep(1)
    tri = (inc or {}).get("triage") or {}
    check(
        "triaged",
        inc and inc["status"] != "triaging",
        f"after {time.time() - t:.1f}s: status={inc and inc['status']} decision={tri.get('decision')} "
        f"source={tri.get('source')} seconds={tri.get('seconds')}",
    )
    print(
        "    triage:",
        json.dumps(
            {
                k: tri.get(k)
                for k in (
                    "fly_tip",
                    "confidence",
                    "what_you_see",
                    "size",
                    "waste_type",
                    "land_type",
                    "decision",
                    "decision_why",
                )
            }
        ),
    )
    print("    whose_job:", tri.get("whose_job"), "\n    hotspot:", tri.get("hotspot"))
    check(
        "street and ward",
        True,
        f"street={inc.get('street')} ward={inc.get('ward')} summary={inc.get('public_summary')}",
    )

    # EXIF stripped, resized
    img_bytes = get(inc["photo_url"]).content
    im = Image.open(io.BytesIO(img_bytes))
    check(
        "GET /media/<upload> is EXIF-free and <=1600px",
        len(im.getexif()) == 0 and max(im.size) <= 1600,
        f"{im.size}, exif tags={len(im.getexif())}",
    )

    # 3. merge
    with open(PHOTO, "rb") as f:
        r2 = requests.post(
            BASE + "/api/reports",
            files={"photo": ("again.jpg", f, "image/jpeg")},
            data={"lat": "53.40845", "lon": "-2.99155", "loc_source": "map"},
            timeout=60,
        ).json()
    check(
        "second report within 40 m merges",
        r2.get("merged") and r2.get("incident_id") == iid and r2.get("others_count") == 1,
        json.dumps(r2),
    )

    # 4. no location -> 422
    buf = io.BytesIO()
    Image.new("RGB", (64, 48), (120, 120, 120)).save(buf, "JPEG")
    r3 = requests.post(BASE + "/api/reports", files={"photo": ("x.jpg", buf.getvalue(), "image/jpeg")}, timeout=30)
    check(
        "no location gives 422 no_location",
        r3.status_code == 422 and r3.json().get("error") == "no_location",
        f"{r3.status_code} {r3.text[:80]}",
    )
    r4 = requests.post(
        BASE + "/api/reports",
        files={"photo": ("x.txt", b"not an image", "text/plain")},
        data={"lat": "53.4", "lon": "-2.99"},
        timeout=30,
    )
    check("non-image photo is rejected", r4.status_code == 415, f"{r4.status_code} {r4.text[:80]}")

    # 5. every read endpoint
    for path in (
        "/api/copy",
        "/api/incidents?view=public",
        "/api/incidents?view=council",
        f"/api/incidents/{iid}?view=public",
        "/api/history",
        "/api/routes?team=crew",
        "/api/routes?team=officer",
        "/api/return?quarter=2026-Q2",
        "/api/return.csv",
        "/api/hotspots",
        "/api/reduce",
        "/api/stats",
        "/",
        "/council",
        "/static/shared/api.js",
    ):
        rr = get(path)
        detail = f"{rr.status_code} {len(rr.content)}B"
        if path.startswith("/api/routes"):
            j = rr.json()
            detail += f" stops={len(j['stops'])} km={j['total_km']} min={j['total_drive_min']} via={j['order_method']}"
        if path.startswith("/api/return?"):
            j = rr.json()
            detail += f" total={j['total_incidents']} checks={[c['ok'] for c in j['checks']]}"
        if path == "/api/hotspots":
            j = rr.json()
            detail += f" n={len(j)} states={[h['state'] for h in j][:6]}"
        if path == "/api/history":
            detail += f" points={len(rr.json())}"
        check(f"GET {path}", rr.ok, detail)
    v2_checks(iid)
    missing = get("/api/incidents/999999")
    check("GET unknown incident gives 404", missing.status_code == 404, missing.text[:60])

    # 6. actions
    for body in (
        {"action": "schedule"},
        {"action": "hold", "note": "Check for evidence"},
        {"action": "inspect"},
        {"action": "override", "decision": "clear_now", "note": "No evidence found"},
        {"action": "warning_letter", "note": "Letter to 12 Example St"},
        {"action": "fpn"},
        {"action": "prosecution"},
    ):
        ra = requests.post(BASE + f"/api/incidents/{iid}/actions", json=body, timeout=30)
        j = ra.json()
        check(
            f"action {body['action']}",
            ra.ok and j.get("id") == iid,
            f"status={j.get('status')} decision={(j.get('triage') or {}).get('decision')}",
        )
    bad = requests.post(BASE + f"/api/incidents/{iid}/actions", json={"action": "explode"}, timeout=30)
    check("unknown action gives 400", bad.status_code == 400, bad.text[:60])
    with open(sorted((APP / "seed/photos").glob("*_after.jpg"))[0], "rb") as f:
        rc = requests.post(
            BASE + f"/api/incidents/{iid}/actions",
            data={"action": "clear", "note": "Crew 3"},
            files={"photo": ("after.jpg", f, "image/jpeg")},
            timeout=30,
        )
    j = rc.json()
    check(
        "action clear (multipart photo)",
        rc.ok and j["status"] == "cleared" and j.get("cleared_photo_url"),
        f"cleared_photo_url={j.get('cleared_photo_url')}",
    )
    for body in (
        {"action": "fpn"},
        {"action": "override", "decision": "clear_now"},
        {"action": "override", "size": "Single item"},
        {"action": "schedule"},
    ):
        rx = requests.post(BASE + f"/api/incidents/{iid}/actions", json=body, timeout=30)
        check(
            f"{body['action']} on a cleared incident gives 409 closed",
            rx.status_code == 409 and rx.json().get("error") == "closed",
            f"{rx.status_code} {rx.text[:60]}",
        )
    pub_cleared = get(f"/api/incidents/{iid}?view=public").json()
    pub = pub_cleared
    council = get(f"/api/incidents/{iid}?view=council").json()
    kinds_pub = [e["kind"] for e in pub["timeline"]]
    kinds_cou = [e["kind"] for e in council["timeline"]]
    check(
        "public view hides enforcement, cost, decision_why, context_flags",
        "enforcement" not in kinds_pub
        and "cost" not in pub["triage"]
        and "decision_why" not in pub["triage"]
        and "context_flags" not in pub["triage"]
        and "enforcement" in kinds_cou,
        f"public timeline={kinds_pub}",
    )
    rr = requests.post(
        BASE + f"/api/incidents/{iid}/actions", json={"action": "reopen", "note": "Waste returned"}, timeout=30
    )
    j = rr.json()
    check(
        "reopen a cleared incident",
        rr.ok
        and j["status"] == "triaged"
        and j["cleared_at"] is None
        and j["closed_at"] is None
        and j["timeline"][-1]["kind"] == "reopened"
        and j["timeline"][-1]["text"] == "Reopened",
        f"status={j.get('status')} cleared_at={j.get('cleared_at')} last={j['timeline'][-1]}",
    )
    rr2 = requests.post(BASE + f"/api/incidents/{iid}/actions", json={"action": "reopen"}, timeout=30)
    check(
        "reopen an open incident gives 409 not_closed",
        rr2.status_code == 409 and rr2.json().get("error") == "not_closed",
        rr2.text[:60],
    )
    ra = requests.post(BASE + f"/api/incidents/{iid}/actions", json={"action": "schedule"}, timeout=30)
    check("actions work again after reopen", ra.ok and ra.json()["status"] == "scheduled", ra.json().get("status"))
    others = [
        i
        for i in get("/api/incidents?view=council").json()
        if i["status"] not in ("cleared", "not_fly_tip", "forwarded") and i["id"] != iid
    ]
    if others:
        rn = requests.post(
            BASE + f"/api/incidents/{others[0]['id']}/actions", json={"action": "not_fly_tip"}, timeout=30
        )
        check("action not_fly_tip", rn.ok and rn.json()["status"] == "not_fly_tip", rn.json().get("status"))
        pl = {i["id"]: i for i in get("/api/incidents?view=public").json()["incidents"]}
        ci = pl.get(others[0]["id"]) or {}
        check(
            "council-closed report stays public for 24h as closed",
            ci.get("public_status") == "closed"
            and ci.get("public_label") == "Closed: not fly-tipping"
            and ci.get("closed_at"),
            f"{ci.get('public_status')} {ci.get('closed_at')}",
        )
        ro = requests.post(BASE + f"/api/incidents/{others[0]['id']}/actions", json={"action": "reopen"}, timeout=30)
        check(
            "reopen a not-fly-tipping incident clears closed_at",
            ro.ok and ro.json()["status"] == "triaged" and ro.json()["closed_at"] is None,
            f"{ro.status_code} {ro.json().get('status')} {ro.json().get('closed_at')}",
        )

    csv_checks()
    no_cost_checks()
    trust_checks()
    ret = get("/api/return").json()
    check(
        "return checks all pass",
        all(c["ok"] for c in ret["checks"]),
        f"total={ret['total_incidents']} actions={ret['actions']}",
    )
    st = get("/api/stats").json()
    check("stats", "city" in st and "wards" in st, json.dumps(st["city"]))
    cfg = get("/api/config").json()
    check("model status at end", True, json.dumps(cfg["model"]))

    passed = sum(ok for _, ok, _ in results)
    print(f"\nSUMMARY: {passed}/{len(results)} checks passed in {time.time() - t0:.0f}s (classifier={MODE})")
    for name, ok, detail in results:
        if not ok:
            print(f"  FAILED: {name}: {detail}")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
