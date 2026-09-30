"""Crew and officer routes: OSRM trip optimisation from the depot, urgent stops first, straight-line fallback.

Order: if any stops are urgent, an OSRM trip over depot + urgent stops fixes their order, then a second trip runs
from the last urgent stop through the rest and back to the depot. One OSRM route call over the final sequence gives
the legs and road geometry. If OSRM is down: nearest-neighbour + 2-opt on straight-line distance, same urgent rule.
No clock ETAs and no on-site minutes.
"""
from __future__ import annotations

import os
import threading
import time

import requests

import db
import priority
from common import case_ref, config, haversine_m, log, parse_dt
from datetime import datetime, timezone

# The public OSRM demo server allows light, non-commercial use only (1 request a second). Run your own for real use.
OSRM_BASE = os.environ.get("FT_OSRM_URL", "https://router.project-osrm.org").rstrip("/")
TRIP = OSRM_BASE + "/trip/v1/driving/{coords}?{params}&overview=full&geometries=geojson&annotations=false"
ROUTE = OSRM_BASE + "/route/v1/driving/{coords}?overview=full&geometries=geojson"
OSRM_TIMEOUT_S = 6
FALLBACK_KMH = 18.0          # city driving incl. junctions, for the straight-line fallback
ROAD_FACTOR = 1.35           # straight line -> road distance, for the fallback
CACHE_S = 60
GMAPS_MAX_WAYPOINTS = 9

# order_method is shown to officers, so it is plain words (the UI matches "straight" for the fallback).
METHOD_OSRM = "Optimised for road distance"
METHOD_FALLBACK = "Optimised for straight-line distance (road data unavailable)"
URGENT_FIRST = ", urgent jobs first"

OSRM_BACKOFF_S = 120         # after a failure, use straight lines for a while instead of waiting each time
_osrm_down_until = 0.0
_cache: dict[tuple, tuple[float, dict]] = {}
_lock = threading.Lock()
_STARTED = datetime.now(timezone.utc)  # routes show only work booked or held since this server started


def team_filter(team: str, inc: dict) -> bool:
    """Routes hold only jobs an officer has acted on today: booked for the crew, or held for inspection.
    So both routes start the day empty and fill as the officer works the queue."""
    st = inc["status"]
    acted = parse_dt(inc.get("updated_at"))
    if not acted or acted < _STARTED:
        return False
    if team == "crew":
        return st == "scheduled"
    return st == "held"


# ---- OSRM ---------------------------------------------------------------------------------------

def _get(url: str) -> dict:
    global _osrm_down_until
    if time.time() < _osrm_down_until:
        raise RuntimeError("backing off after a recent OSRM failure")
    try:
        r = requests.get(url, timeout=OSRM_TIMEOUT_S, headers={"User-Agent": "sorted (https://github.com/petecurran/sorted)"})
        r.raise_for_status()
        j = r.json()
        if j.get("code") != "Ok":
            raise RuntimeError(j.get("code", "no route"))
        return j
    except Exception:
        _osrm_down_until = time.time() + OSRM_BACKOFF_S
        raise


def _coords(points) -> str:
    return ";".join(f"{lon:.6f},{lat:.6f}" for lat, lon in points)


def _trip_order(points, params: str) -> list[int]:
    """Indices of `points` in OSRM trip visiting order."""
    j = _get(TRIP.format(coords=_coords(points), params=params))
    wps = j["waypoints"]
    return sorted(range(len(points)), key=lambda k: wps[k]["waypoint_index"])


def _route(points):
    j = _get(ROUTE.format(coords=_coords(points)))
    route = j["routes"][0]
    legs = [(leg["distance"], leg["duration"]) for leg in route["legs"]]
    geom = [[lat, lon] for lon, lat in route["geometry"]["coordinates"]]
    return legs, geom


def _osrm_plan(depot, urgent, rest):
    """(ordered stops, legs incl. return to depot, geometry) via OSRM."""
    d = (depot["lat"], depot["lon"])
    if not urgent:
        pts = [d] + [(i["lat"], i["lon"]) for i in rest]
        j = _get(TRIP.format(coords=_coords(pts), params="source=first&roundtrip=true"))
        wps, trip = j["waypoints"], j["trips"][0]
        order = sorted(range(1, len(pts)), key=lambda k: wps[k]["waypoint_index"])
        legs = [(leg["distance"], leg["duration"]) for leg in trip["legs"]]
        geom = [[lat, lon] for lon, lat in trip["geometry"]["coordinates"]]
        return [rest[k - 1] for k in order], legs, geom
    upts = [d] + [(i["lat"], i["lon"]) for i in urgent]
    uorder = [urgent[k - 1] for k in _trip_order(upts, "source=first&roundtrip=true") if k != 0]
    ordered = list(uorder)
    if rest:
        last = uorder[-1]
        rpts = [(last["lat"], last["lon"])] + [(i["lat"], i["lon"]) for i in rest] + [d]
        rorder = _trip_order(rpts, "source=first&destination=last&roundtrip=false")
        ordered += [rest[k - 1] for k in rorder if 0 < k < len(rpts) - 1]
    legs, geom = _route([d] + [(i["lat"], i["lon"]) for i in ordered] + [d])
    return ordered, legs, geom


# ---- straight-line fallback ---------------------------------------------------------------------

def _dist(a, b) -> float:
    return haversine_m(a["lat"], a["lon"], b["lat"], b["lon"])


def _path_len(start, seq, end) -> float:
    pts = [start] + seq + ([end] if end is not None else [])
    return sum(_dist(a, b) for a, b in zip(pts, pts[1:]))


def _nn(start, incs):
    left, out, cur = list(incs), [], start
    while left:
        nxt = min(left, key=lambda i: _dist(cur, i))
        left.remove(nxt)
        out.append(nxt)
        cur = nxt
    return out


def _two_opt(start, seq, end):
    best, best_len = list(seq), _path_len(start, seq, end)
    improved = True
    while improved and len(best) > 2:
        improved = False
        for i in range(len(best) - 1):
            for j in range(i + 1, len(best)):
                cand = best[:i] + best[i:j + 1][::-1] + best[j + 1:]
                L = _path_len(start, cand, end)
                if L < best_len - 0.5:
                    best, best_len, improved = cand, L, True
    return best


def _fallback_plan(depot, urgent, rest):
    d = {"lat": depot["lat"], "lon": depot["lon"]}
    u = _two_opt(d, _nn(d, urgent), None if rest else d) if urgent else []
    start = u[-1] if u else d
    r = _two_opt(start, _nn(start, rest), d) if rest else []
    ordered = u + r
    pts = [d] + ordered + [d]
    legs = []
    for a, b in zip(pts, pts[1:]):
        m = _dist(a, b) * ROAD_FACTOR
        legs.append((m, m / (FALLBACK_KMH * 1000 / 3600)))
    return ordered, legs, [[p["lat"], p["lon"]] for p in pts]


# ---- Google Maps --------------------------------------------------------------------------------

def google_maps_urls(depot, stops) -> list[str]:
    """Driving directions depot -> stops -> depot, split so each link has at most 9 waypoints."""
    if not stops:
        return []
    pts = [(depot["lat"], depot["lon"])] + [(s["lat"], s["lon"]) for s in stops] + [(depot["lat"], depot["lon"])]
    ll = lambda p: f"{p[0]:.6f},{p[1]:.6f}"
    urls, i = [], 0
    while i < len(pts) - 1:
        seg = pts[i:i + GMAPS_MAX_WAYPOINTS + 2]
        url = f"https://www.google.com/maps/dir/?api=1&origin={ll(seg[0])}&destination={ll(seg[-1])}"
        if len(seg) > 2:
            url += "&waypoints=" + "|".join(ll(p) for p in seg[1:-1])
        urls.append(url + "&travelmode=driving")
        i += len(seg) - 1
    return urls


# ---- main ---------------------------------------------------------------------------------------

def plan(team: str, incidents: list[dict]) -> dict:
    team = "officer" if team == "officer" else "crew"
    depot = config()["depot"]
    incs = [i for i in incidents if team_filter(team, i)]
    ctx = priority.Context(incidents, db.all_reports(), db.all_confirmations())
    level = {i["id"]: priority.compute(i, ctx)["priority"]["level"] for i in incs}
    incs.sort(key=lambda i: i["id"])
    urgent = [i for i in incs if level[i["id"]] == "urgent"]
    rest = [i for i in incs if level[i["id"]] != "urgent"]
    key = (team, tuple((i["id"], round(i["lat"], 6), round(i["lon"], 6), level[i["id"]]) for i in incs),
           round(depot["lat"], 6), round(depot["lon"], 6))
    with _lock:
        hit = _cache.get(key)
        if hit and time.time() - hit[0] < CACHE_S:
            return hit[1]

    if not incs:
        ordered, legs, geom, method = [], [], [[depot["lat"], depot["lon"]]], METHOD_OSRM
    else:
        try:
            ordered, legs, geom = _osrm_plan(depot, urgent, rest)
            method = METHOD_OSRM
        except Exception as e:
            log.info("OSRM unavailable (%s); using nearest-neighbour + 2-opt on straight lines", e)
            ordered, legs, geom = _fallback_plan(depot, urgent, rest)
            method = METHOD_FALLBACK

    stops = []
    for n, (inc, (dm, ds)) in enumerate(zip(ordered, legs), start=1):
        t = inc.get("triage") or {}
        what = inc.get("public_summary") or t.get("waste_type") or "Fly-tipping"
        stops.append({
            "incident_id": inc["id"], "case_ref": case_ref(inc["id"]), "order": n,
            "lat": inc["lat"], "lon": inc["lon"], "street": inc.get("street"), "ward": inc.get("ward"),
            "label": f"{inc.get('street') or 'Unnamed street'}: {what}",
            "decision": t.get("decision"), "priority_level": level[inc["id"]],
            "drive_min_from_prev": round(ds / 60, 1), "drive_km_from_prev": round(dm / 1000, 2),
        })
    back = legs[len(ordered)] if len(legs) > len(ordered) else (0.0, 0.0)
    total_s = sum(s for _, s in legs)
    total_m = sum(m for m, _ in legs)
    out = {
        "team": team, "depot": depot, "stops": stops,
        "return_to_depot": {"drive_min": round(back[1] / 60, 1), "drive_km": round(back[0] / 1000, 2)},
        "total_drive_min": int(round(total_s / 60)), "total_km": round(total_m / 1000, 1),
        "distance_km": round(total_m / 1000, 1),  # kept for older UI code; same as total_km
        "urgent_first": bool(urgent),
        "order_method": method.replace(" (", URGENT_FIRST + " (", 1) if urgent and "(" in method
        else method + (URGENT_FIRST if urgent else ""),
        "geometry": geom,
        "google_maps_urls": google_maps_urls(depot, stops),
        "qr_url": f"/api/routes/qr?team={team}",
    }
    with _lock:
        _cache[key] = (time.time(), out)
    return out
