"""Sorted: FastAPI app. Run: uv run uvicorn server:app --host 0.0.0.0 --port 8800  (one worker).

Env vars:
  FT_CLASSIFIER=gemma|cache|off   gemma (default) loads Gemma 4 12B at startup; cache/off never load it.
  FT_DATA_DIR=<dir>               where runtime data lives (app.db, uploads/). Default data/ in the repo.
  FT_RESET=1                      delete app.db and uploads/ in FT_DATA_DIR before starting (re-seeds the demo;
                                  scripts/run.sh and start_server.sh also rebuild the seed for today first).
  FT_CACHE_DELAY=<seconds>        optional pause before a model-cache hit lands (so "Checking…" shows). Default 0.
  FT_MODEL=<hf id>                override the model id (default mlx-community/gemma-4-12B-it-4bit).
  FT_WARMUP=0                     skip the one-off warm-up generation after the model loads.
  FT_TODAY=YYYY-MM-DD             fix the demo date, if content/config.json has no "today" (default: the real date).
  FT_OSRM_URL=<url>               OSRM server for the Routes tab (default: the public demo server, light use only).
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import statistics
import time
from contextlib import asynccontextmanager

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

from common import APP, COUNCIL_NAME, DB_PATH, SEED, STATIC, UPLOADS, brand, brand_script, config, content, log, parse_dt, rebrand, seed  # noqa: E402


def _reset():
    for p in (DB_PATH, DB_PATH.with_name(DB_PATH.name + "-wal"), DB_PATH.with_name(DB_PATH.name + "-shm")):
        p.unlink(missing_ok=True)
    if UPLOADS.exists():
        shutil.rmtree(UPLOADS)
    log.info("FT_RESET=1: removed database and uploads")


if os.environ.get("FT_RESET") == "1":
    _reset()
UPLOADS.mkdir(parents=True, exist_ok=True)

from fastapi import FastAPI, File, Form, Request, UploadFile  # noqa: E402
from fastapi.concurrency import run_in_threadpool  # noqa: E402
from fastapi.exceptions import RequestValidationError  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.middleware.gzip import GZipMiddleware  # noqa: E402
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from starlette.exceptions import HTTPException as StarletteHTTPException  # noqa: E402

import db  # noqa: E402
import hotspots  # noqa: E402
import incidents  # noqa: E402
import photos  # noqa: E402
import routes  # noqa: E402
import wdf_return  # noqa: E402
from classifier import classifier  # noqa: E402


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.conn()
    if db.count_incidents() == 0:
        try:
            incidents.seed_demo()
        except Exception:
            log.exception("seeding failed; continuing with what was loaded")
    classifier.start()
    yield
    db.close()


app = FastAPI(title="Sorted", lifespan=lifespan)
app.add_middleware(GZipMiddleware, minimum_size=2000)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


LOOPBACK = {"127.0.0.1", "::1", "localhost"}
PROXY_HEADERS = ("cf-ray", "cf-connecting-ip", "x-forwarded-for", "x-real-ip", "forwarded")


def _remote(request: Request) -> bool:
    """False only for a request made on this machine with no proxy in between (the presenter's laptop). Phones
    through the tunnel, and anyone reaching a hosted copy, are remote: they get the public site, and the council
    console needs its password."""
    host = request.client.host if request.client else ""
    return host not in LOOPBACK or any(h in request.headers for h in PROXY_HEADERS)


# Through the tunnel, phones get the public site. The council console needs its password there (the sign-in on this
# laptop still accepts anything); the password is in data/council_password.txt (scripts/room.sh password).
TUNNEL_PREFIXES = ("/static/public/", "/static/shared/", "/static/vendor/", "/media/")
TUNNEL_API = {"/api/config", "/api/copy", "/api/brand.js", "/api/stats", "/api/health", "/api/dev/version"}
_INCIDENT_PATH = re.compile(r"^/api/incidents(/\d+)?$")
_CONFIRM_PATH = re.compile(r"^/api/incidents/\d+/confirm$")
ROOM_CLOSED = """<!doctype html><html lang="en-GB"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Report fly-tipping</title>
<style>body{margin:0;font:16px/1.5 system-ui,sans-serif;color:#202427;background:#F4F4F5;display:grid;place-items:center;
min-height:100vh;padding:24px;box-sizing:border-box}main{max-width:420px;background:#fff;border-radius:12px;padding:24px}</style>
</head><body><main><h1>Thank you</h1><p>The live demonstration has finished. Thank you for taking part.</p></main></body></html>"""
PASSWORD_FILE = APP / "data" / "council_password.txt"
COUNCIL_COOKIE = "ch_council"


def council_password() -> str:
    """The council console's password for phones, made on first use. data/ is not in git."""
    if not PASSWORD_FILE.exists():
        import secrets
        words = ["ferry", "dock", "pier", "liver", "mersey", "albert", "sefton", "wirral", "anfield", "canal"]
        PASSWORD_FILE.parent.mkdir(parents=True, exist_ok=True)
        PASSWORD_FILE.write_text(f"{secrets.choice(words)}-{secrets.choice(words)}-{secrets.randbelow(90) + 10}\n")
    return PASSWORD_FILE.read_text().strip()


def _council_token() -> str:
    return hashlib.sha256(f"sorted council:{council_password()}".encode()).hexdigest()


def _council_ok(request: Request) -> bool:
    """This laptop, or a phone that has signed in with the password."""
    if not _remote(request):
        return True
    import hmac
    return hmac.compare_digest(request.cookies.get(COUNCIL_COOKIE, ""), _council_token())


def _council_sign_in_path(request: Request) -> bool:
    """What a phone needs to reach the sign-in screen and sign in."""
    path = request.url.path
    return (path in ("/council", "/council/") or path.startswith("/static/council/")
            or path in ("/api/council/login", "/api/council/session"))


def _tunnel_allowed(request: Request) -> bool:
    path, method = request.url.path, request.method
    if method in ("GET", "HEAD"):
        if path == "/" or path.startswith(TUNNEL_PREFIXES) or path in TUNNEL_API:
            return True
        if _INCIDENT_PATH.match(path):
            return request.query_params.get("view", "public") != "council"
        return False
    if method == "POST":
        return path == "/api/reports" or bool(_CONFIRM_PATH.match(path))
    return method == "OPTIONS"


_room: dict = {"seen": {}, "hits": []}  # phones by address, and request times, for /api/room


@app.middleware("http")
async def public_only_through_tunnel(request: Request, call_next):
    if _remote(request):
        now = time.monotonic()
        _room["seen"][request.headers.get("cf-connecting-ip", "?")] = now
        _room["hits"].append(now)
        if len(_room["hits"]) > 5000:
            _room["hits"] = [t for t in _room["hits"] if now - t < 60]
        if str(config().get("audience_access", "on")).strip().lower() == "off":
            # The room is closed: new visitors see a thank-you page; open pages get 410 and stop polling.
            if request.method == "GET" and request.url.path == "/":
                return HTMLResponse(ROOM_CLOSED)
            return JSONResponse({"error": "room_closed"}, status_code=410)
        if not (_tunnel_allowed(request) or _council_sign_in_path(request) or _council_ok(request)):
            return JSONResponse({"error": "sign_in"}, status_code=401)
    return await call_next(request)


@app.middleware("http")
async def no_store_api(request: Request, call_next):
    resp = await call_next(request)
    path = request.url.path
    if path.startswith("/api") and request.method != "GET":
        _public_list["body"] = None  # a report, action or vote: the next public poll sees it
    if path.startswith("/api"):
        resp.headers["Cache-Control"] = "no-store"
    elif path.startswith("/media/") or path.startswith("/static/vendor/"):
        # Photos (fixed names) and the map library: fetched once per phone, and cacheable by Cloudflare.
        resp.headers["Cache-Control"] = "public, max-age=3600"
    elif path.startswith("/static"):
        resp.headers["Cache-Control"] = "no-cache"  # always revalidate, so edits show on the next reload
    return resp


def err(code: str, status: int = 400, **extra) -> JSONResponse:
    return JSONResponse({"error": code, **extra}, status_code=status)


@app.exception_handler(StarletteHTTPException)
async def http_err(request: Request, exc: StarletteHTTPException):
    if request.url.path.startswith("/api"):
        return err({404: "not_found", 405: "method_not_allowed"}.get(exc.status_code, str(exc.detail)),
                   exc.status_code)
    return HTMLResponse(f"<h1>{exc.status_code}</h1>", status_code=exc.status_code)


@app.exception_handler(RequestValidationError)
async def validation_err(request: Request, exc: RequestValidationError):
    return err("bad_request", 400, detail=[{"loc": e.get("loc"), "msg": e.get("msg")} for e in exc.errors()])


@app.exception_handler(incidents.ActionError)
async def action_err(request: Request, exc: incidents.ActionError):
    return err(exc.code, exc.status)


@app.exception_handler(photos.BadImage)
async def bad_image(request: Request, exc: photos.BadImage):
    return err("unreadable_photo", 415, detail=str(exc))


def _view(view: str | None) -> str:
    return "council" if view == "council" else "public"


# ---- API ----------------------------------------------------------------------------------------

@app.get("/api/config")
def api_config():
    c = config()
    q = c["quarter"]
    return {
        "city": c["city"], "authority": COUNCIL_NAME, "today": c["today"],
        "quarter": {"id": q["id"], "label": q.get("label"), "deadline": q.get("deadline"), "name": q.get("name"),
                    "start": q.get("start"), "end": q.get("end")},
        "depot": c["depot"],
        "model": classifier.info(),
        "context": {"collection_day_wards": c.get("collection_day_wards", []),
                    "bulky_bookings": c.get("bulky_bookings", [])},
    }


@app.get("/api/copy")
def api_copy():
    return content("copy.json", {}) or {}


@app.post("/api/council/login")
async def api_council_login(request: Request):
    """Sign in to the council console. On this laptop any password works; phones need the real one."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    if _remote(request):
        import hmac
        if not hmac.compare_digest(str(body.get("password") or "").strip(), council_password()):
            return err("wrong_password", 401)
    resp = JSONResponse({"ok": True})
    resp.set_cookie(COUNCIL_COOKIE, _council_token(), max_age=12 * 3600, httponly=True, samesite="lax",
                    secure=_remote(request))
    return resp


@app.get("/api/council/session")
def api_council_session(request: Request):
    return {"ok": True} if _council_ok(request) else err("sign_in", 401)


@app.get("/api/room")
def api_room():
    """The room at a glance (this laptop only; the tunnel refuses it): phones seen, requests, switches and the queue."""
    now = time.monotonic()
    c = config()
    return {
        "phones_last_minute": sum(1 for t in _room["seen"].values() if now - t < 60),
        "phones_last_10_minutes": sum(1 for t in _room["seen"].values() if now - t < 600),
        "requests_last_minute": sum(1 for t in _room["hits"] if now - t < 60),
        "audience_access": c.get("audience_access", "on"), "audience_uploads": c.get("audience_uploads", "on"),
        "audience_ai": c.get("audience_ai", "on"), "model": classifier.info(),
    }


@app.get("/api/brand.js", include_in_schema=False)
def api_brand_js():
    """content/brand.json as a script, loaded in each page's head before static/shared/brand.js applies it."""
    return Response(brand_script(brand()), media_type="text/javascript; charset=utf-8")


# The public list is rebuilt at most every 2 s however many phones are polling it; any write clears it.
PUBLIC_LIST_TTL = 2.0
_public_list: dict = {"at": 0.0, "body": None}


@app.get("/api/incidents")
def api_incidents(view: str = "public", since: str | None = None):
    if _view(view) != "public":
        return incidents.list_all(_view(view))
    now = time.monotonic()
    if _public_list["body"] is None or now - _public_list["at"] > PUBLIC_LIST_TTL:
        # The map needs only the decision from the AI's reading (public.js); the rest stays on the council side.
        slim = [{**i, "triage": {"decision": i["triage"].get("decision")}} if isinstance(i.get("triage"), dict) else i
                for i in incidents.list_all("public")]
        items = JSONResponse(slim).body
        version = hashlib.sha1(items).hexdigest()[:12]
        body = b'{"version":"' + version.encode() + b'","incidents":' + items + b"}"
        _public_list.update(at=now, body=body, version=version)
    if since and since == _public_list.get("version"):
        # Phones send the version they already have: when nothing has changed, the reply is a few bytes.
        return Response(b'{"version":"' + since.encode() + b'","unchanged":true}', media_type="application/json")
    return Response(_public_list["body"], media_type="application/json")


@app.get("/api/incidents/{iid}")
def api_incident(iid: int, view: str = "public"):
    inc = incidents.get(iid, _view(view))
    return inc if inc else err("not_found", 404)


@app.post("/api/reports")
def api_report(request: Request, photo: UploadFile = File(...), lat: str | None = Form(None),
               lon: str | None = Form(None), loc_source: str | None = Form(None),
               description: str | None = Form(None), reporter: str | None = Form(None),
               stage: str | None = Form(None)):
    remote = _remote(request)
    if remote and str(config().get("audience_uploads", "on")).strip().lower() == "off":
        return err("reporting_closed", 403)  # content/config.json "audience_uploads": "off" closes remote reporting
    data = photo.file.read()
    # The presenter's photos jump the model's queue: anything from this machine, or from a page opened with ?stage=1.
    return incidents.submit_report(data, lat=lat, lon=lon, loc_source=loc_source, description=description,
                                   reporter=reporter, stage=stage == "1" or not remote)


@app.post("/api/incidents/{iid}/actions")
async def api_action(iid: int, request: Request):
    ctype = request.headers.get("content-type", "")
    photo_bytes = None
    if ctype.startswith("multipart/") or ctype.startswith("application/x-www-form-urlencoded"):
        form = await request.form()
        body = {k: form.get(k) for k in ("action", "note", "decision", *incidents.OVERRIDE_FIELDS)}
        up = form.get("photo")
        if up is not None and hasattr(up, "read"):
            photo_bytes = await up.read() or None
    else:
        try:
            body = await request.json()
        except Exception:
            return err("bad_json")
        if not isinstance(body, dict):
            return err("bad_json")
    fields = {k: body.get(k) for k in incidents.OVERRIDE_FIELDS if body.get(k) not in (None, "")}
    return await run_in_threadpool(incidents.apply_action, iid, str(body.get("action") or ""),
                                   body.get("note"), body.get("decision"), photo_bytes, fields=fields)


@app.post("/api/incidents/{iid}/confirm")
async def api_confirm(iid: int, request: Request):
    try:
        body = await request.json()
    except Exception:
        return err("bad_json")
    if not isinstance(body, dict) or not isinstance(body.get("still_there"), bool):
        return err("bad_request", detail="send {\"still_there\": true|false}")
    return await run_in_threadpool(incidents.confirm, iid, body["still_there"])


@app.get("/api/history")
def api_history():
    pts = seed("history.json", []) or []
    return [{"lat": p.get("lat"), "lon": p.get("lon"), "date": p.get("date"), "ward": p.get("ward"),
             "street": p.get("street")} for p in pts if isinstance(p, dict) and p.get("lat") is not None]


@app.get("/api/routes")
def api_routes(team: str = "crew"):
    return routes.plan(team, db.list_incidents())


def _qr_png(text: str) -> Response:
    import io

    import qrcode
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=8, border=2)
    qr.add_data(text)
    qr.make(fit=True)
    buf = io.BytesIO()
    qr.make_image(fill_color="black", back_color="white").save(buf, format="PNG")
    return Response(buf.getvalue(), media_type="image/png", headers={"Cache-Control": "no-store"})


@app.get("/api/routes/qr")
def api_routes_qr(team: str = "crew"):
    r = routes.plan(team, db.list_incidents())
    urls = r.get("google_maps_urls") or []
    d = r["depot"]
    return _qr_png(urls[0] if urls else f"https://www.google.com/maps/search/?api=1&query={d['lat']},{d['lon']}")


@app.get("/api/qr")
def api_qr(text: str = ""):
    if not text or len(text) > 2000:
        return err("bad_request", detail="text is required (at most 2000 characters)")
    return _qr_png(text)


@app.get("/api/return")
def api_return(quarter: str | None = None):
    return wdf_return.build(db.list_incidents(), db.all_actions(), quarter)


@app.get("/api/return.csv")
def api_return_csv(quarter: str | None = None):
    r = wdf_return.build(db.list_incidents(), db.all_actions(), quarter)
    # UTF-8 with a BOM so Excel shows the £ sign correctly
    return Response(("\ufeff" + rebrand(wdf_return.to_csv(r))).encode("utf-8"), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{rebrand(wdf_return.csv_filename(r))}"'})


@app.get("/api/hotspots")
def api_hotspots():
    return hotspots.build(db.list_incidents(), db.all_reports())


@app.get("/api/reduce")
def api_reduce():
    return hotspots.reduce_view(db.list_incidents(), db.all_reports())


@app.get("/api/stats")
def api_stats():
    incs = db.list_incidents()
    acts = db.all_actions()
    ward_of = {i["id"]: i.get("ward") or "Unknown ward" for i in incs}
    hours = []
    for i in incs:
        if i["status"] == "cleared" and i.get("cleared_at"):
            a, b = parse_dt(i["created_at"]), parse_dt(i["cleared_at"])
            if a and b and b >= a:
                hours.append((b - a).total_seconds() / 3600)
    wards: dict[str, dict] = {}
    for i in incs:
        w = wards.setdefault(ward_of[i["id"]], {"ward": ward_of[i["id"]], "reports": 0, "incidents": 0, "cleared": 0,
                                                 "open": 0, "fines": 0, "warnings": 0, "prosecutions": 0})
        w["reports"] += int(i["report_count"] or 1)
        w["incidents"] += 1
        w["cleared"] += i["status"] == "cleared"
        w["open"] += i["status"] not in ("cleared", "not_fly_tip")
    key = {"fpn": "fines", "warning_letter": "warnings", "prosecution": "prosecutions"}
    for a in acts:
        if a["action"] in key and a["incident_id"] in ward_of:
            wards[ward_of[a["incident_id"]]][key[a["action"]]] += 1
    rows = sorted(wards.values(), key=lambda w: (-w["reports"], w["ward"]))
    return {
        "city": {"reports": sum(int(i["report_count"] or 1) for i in incs), "incidents": len(incs),
                 "cleared": sum(i["status"] == "cleared" for i in incs),
                 "median_hours_to_clear": round(statistics.median(hours), 1) if hours else None,
                 "open": sum(i["status"] not in ("cleared", "not_fly_tip") for i in incs),
                 "fines": sum(w["fines"] for w in rows), "warnings": sum(w["warnings"] for w in rows),
                 "prosecutions": sum(w["prosecutions"] for w in rows)},
        "wards": rows,
    }


@app.get("/api/dev/version")
def api_dev_version():
    """Live reload: a fingerprint of the newest front-end or content file. Pages opened with ?live=1 poll this."""
    newest = 0.0
    for root in (STATIC, APP / "content"):
        for dirpath, _dirs, files in os.walk(root):
            if "/mock" in dirpath:
                continue
            for f in files:
                try:
                    newest = max(newest, os.stat(os.path.join(dirpath, f)).st_mtime)
                except OSError:
                    pass
    return {"v": f"{newest:.3f}"}


@app.get("/api/health")
def api_health():
    return {"ok": True, "incidents": db.count_incidents(), "model": classifier.info(),
            "load_error": classifier.load_error}


# ---- pages and files ----------------------------------------------------------------------------

def _page(rel: str, title: str):
    p = STATIC / rel
    if p.exists():
        return FileResponse(p, headers={"Cache-Control": "no-cache"})
    return HTMLResponse(f"<!doctype html><title>{title}</title><p>{title} page not built yet "
                        f"(expected static/{rel}). API is up at <a href='/api/config'>/api/config</a>.</p>")


@app.get("/", include_in_schema=False)
def page_public():
    return _page("public/index.html", "Public portal")


@app.get("/council", include_in_schema=False)
@app.get("/council/", include_in_schema=False)
def page_council():
    return _page("council/index.html", "Council console")


(SEED / "photos").mkdir(parents=True, exist_ok=True)
@app.get("/media/seed/{name}", include_in_schema=False)
def seed_photo(name: str, request: Request):
    """Seed photos: phones (through the tunnel) get the smaller copy in seed/photos_web, the stage screens full size."""
    if "/" in name or name.startswith("."):
        return err("not_found", 404)
    small = SEED / "photos_web" / name
    p = small if _remote(request) and small.is_file() else SEED / "photos" / name
    if not p.is_file():
        return err("not_found", 404)
    return FileResponse(p)


app.mount("/media/seed", StaticFiles(directory=SEED / "photos", check_dir=False), name="seed_media")
app.mount("/media", StaticFiles(directory=UPLOADS, check_dir=False), name="media")
app.mount("/static", StaticFiles(directory=STATIC, check_dir=False), name="static")
(APP / "data" / "brand_check").mkdir(parents=True, exist_ok=True)
app.mount("/dev/brand-check", StaticFiles(directory=APP / "data" / "brand_check", html=True), name="brand_check")
