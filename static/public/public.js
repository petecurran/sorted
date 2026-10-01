/* Mersey Vale City Council (fictional demo) · Fly-tipping: public portal. Plain ES2020, no build step.
   Talks to the API through window.CH (static/shared/api.js). With ?mock=1 it reads
   /static/public/mock/*.json and simulates POSTs so the whole flow can be clicked through.
   Public status language only: New report, Crew booked, Further inspection, Passed to landowner, Cleared, Closed.
   Never show officer visits or triage internals here. */
(() => {
  "use strict";

  const MOCK = !!(window.CH && window.CH.MOCK);
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const clone = (o) => JSON.parse(JSON.stringify(o));
  const desktop = window.matchMedia("(min-width: 960px)");
  const LIVERPOOL = [53.4084, -2.9916];
  const HOME_COUNCIL = "Mersey Vale City Council";
  const HOME_AUTH = new Set([HOME_COUNCIL]);
  const touch = window.matchMedia("(pointer: coarse)").matches || (navigator.maxTouchPoints || 0) > 0;
  const TZ = "Europe/London";
  const TAP = touch ? "Tap" : "Click";
  const POLL_MS = 3000;
  const STATUS_POLL_MS = 2000;
  const SAME_M = 40;
  // ?stage=1 (remembered for this tab) marks the presenter's phone: its photos jump the model's queue and are sent
  // as they are, so the prepared demo photos are recognised.
  const STAGE = (() => {
    if (/^(localhost|127\.0\.0\.1|\[::1\])$/.test(location.hostname)) return true;  // the presenter's laptop
    try {
      if (new URLSearchParams(location.search).get("stage") === "1") sessionStorage.setItem("ch_stage", "1");
      return sessionStorage.getItem("ch_stage") === "1";
    } catch (e) { return new URLSearchParams(location.search).get("stage") === "1"; }
  })();

  let COPY = {
    privacy_note: "Your photo will be shown on the map, so try not to include faces or number plates. We remove hidden data from the photo before it is shown.",
    thanks_single: "You are the first to report this",
    thanks_multi: "{n} other people have reported this",
  };
  const CHIPS = ["Sofa or furniture", "Bags", "Mattress", "Rubble", "Garden waste", "Something else"];

  // ---------------------------------------------------------------- public status
  // Use the API's public_status when present; otherwise derive it the same way the API does. null = not shown publicly.
  function derivePublic(inc) {
    if (!inc) return "new_report";
    if (inc.public_status) return inc.public_status;
    const d = inc.triage && inc.triage.decision;
    if (inc.status === "cleared") return "cleared";
    if (inc.status === "not_fly_tip" || d === "not_a_fly_tip") return null;
    if (inc.status === "triaging" || !inc.triage) return "new_report";
    if (inc.status === "scheduled") return "crew_booked";
    if (inc.status === "held") return "further_inspection";
    return { clear_now: "crew_booked", hold_for_officer: "further_inspection", specialist: "further_inspection" }[d] || "new_report";
  }
  function normalize(inc) {
    if (!inc) return inc;
    const p = derivePublic(inc);
    inc.public_status = p;
    return inc;
  }
  const pub = (inc) => (inc && inc.public_status) || "new_report";
  // CH.PUBLIC_STATUS plus local fallbacks for states the shared map may not have yet.
  const PUB = { passed_on: ["Passed to landowner", "further_inspection"], closed: ["Closed: not fly-tipping", "not_fly_tip"], ...CH.PUBLIC_STATUS };
  const pubLabel = (inc) => (PUB[pub(inc)] || PUB.new_report)[0];
  const pill = (inc) => { const [label, cls] = PUB[pub(inc)] || PUB.new_report; return `<span class="pill ${cls}">${esc(label)}</span>`; };

  const NEXT = {
    new_report: { title: "The council has received this report", text: "It will be checked soon." },
    crew_booked: { title: "A crew has been booked to clear it", text: "This page will show when it has been cleared." },
    further_inspection: { title: "The council will inspect it before it is cleared", text: "Please do not touch or move it." },
    passed_on: { title: "The council has passed this to the landowner", text: "The council does not own this land, so the landowner is responsible for clearing it." },
    cleared: { title: "This has been cleared", text: "Thank you for reporting it." },
    closed: { title: "This report has been closed", text: "The council checked it and found it is not fly-tipping." },
  };

  const ICON = {
    check: '<svg viewBox="0 0 24 24" width="14" height="14" aria-hidden="true"><path fill="currentColor" d="M9.5 16.2 5.3 12l-1.4 1.4 5.6 5.6L20.1 8.4 18.7 7z"/></svg>',
    back: '<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><path fill="currentColor" d="M20 11H7.8l5.6-5.6L12 4l-8 8 8 8 1.4-1.4L7.8 13H20z"/></svg>',
    close: '<svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true"><path fill="currentColor" d="M6.4 5 5 6.4 10.6 12 5 17.6 6.4 19l5.6-5.6 5.6 5.6 1.4-1.4-5.6-5.6L19 6.4 17.6 5 12 10.6 6.4 5Z"/></svg>',
    people: '<svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true"><path fill="currentColor" d="M9 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8Zm7 0a3 3 0 1 0 0-6 3 3 0 0 0 0 6ZM9 14c-3.3 0-6 1.8-6 4v2h12v-2c0-2.2-2.7-4-6-4Zm7 0c-.5 0-1 0-1.4.1 1.5.9 2.4 2.2 2.4 3.9v2h4v-2c0-2.2-2.2-4-5-4Z"/></svg>',
    pin: '<svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true"><path fill="currentColor" d="M12 2a7 7 0 0 0-7 7c0 5.2 7 13 7 13s7-7.8 7-13a7 7 0 0 0-7-7Zm0 9.5a2.5 2.5 0 1 1 0-5 2.5 2.5 0 0 1 0 5Z"/></svg>',
    photoPin: '<svg viewBox="0 0 24 24" width="24" height="24" aria-hidden="true"><path fill="currentColor" d="M4 5h3l1.5-2h7L17 5h3a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2Zm8 2.5a3.6 3.6 0 0 0-3.6 3.6c0 2.7 3.6 6.4 3.6 6.4s3.6-3.7 3.6-6.4A3.6 3.6 0 0 0 12 7.5Zm0 2.2a1.4 1.4 0 1 1 0 2.8 1.4 1.4 0 0 1 0-2.8Z"/></svg>',
    locate: '<svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true"><path fill="currentColor" d="M11 2v2.1A8 8 0 0 0 4.1 11H2v2h2.1a8 8 0 0 0 6.9 6.9V22h2v-2.1a8 8 0 0 0 6.9-6.9H22v-2h-2.1A8 8 0 0 0 13 4.1V2h-2Zm1 4a6 6 0 1 1 0 12 6 6 0 0 1 0-12Zm0 3a3 3 0 1 0 0 6 3 3 0 0 0 0-6Z"/></svg>',
    tap: '<svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true"><path fill="currentColor" d="M9 11.2V7.5a2.5 2.5 0 0 1 5 0v3.7a4.5 4.5 0 1 0-5 0ZM18.2 16l-4.2-2.1V7.5a1.5 1.5 0 0 0-3 0v10.7l-3.4-.7a1.2 1.2 0 0 0-1.1 2l3.3 3.5h7.5l1.4-5.4a1.6 1.6 0 0 0-.5-1.6Z"/></svg>',
    warn: '<svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true"><path fill="currentColor" d="M1 21h22L12 2 1 21Zm12-3h-2v-2h2v2Zm0-4h-2v-4h2v4Z"/></svg>',
    eye: '<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><path fill="currentColor" d="M12 5C6.5 5 2.7 9.4 1.5 12c1.2 2.6 5 7 10.5 7s9.3-4.4 10.5-7C21.3 9.4 17.5 5 12 5Zm0 11a4 4 0 1 1 0-8 4 4 0 0 1 0 8Zm0-2.2a1.8 1.8 0 1 0 0-3.6 1.8 1.8 0 0 0 0 3.6Z"/></svg>',
    gone: '<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><path fill="currentColor" d="M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20Zm-1.5 14.5L6 12l1.4-1.4 3.1 3.1 6.1-6.1L18 9l-7.5 7.5Z"/></svg>',
  };

  const GLYPH = {
    cleared: ICON.check,
    passed_on: '<svg viewBox="0 0 24 24" width="14" height="14" aria-hidden="true"><path fill="currentColor" d="M12 4 10.6 5.4l5.6 5.6H4v2h12.2l-5.6 5.6L12 20l8-8z"/></svg>',
    closed: '<svg viewBox="0 0 24 24" width="14" height="14" aria-hidden="true"><path fill="currentColor" d="M5 11h14v2H5z"/></svg>',
  };

  // ---------------------------------------------------------------- time helpers
  const dayKey = (t) => new Date(t).toLocaleDateString("en-CA", { timeZone: TZ });
  const hhmm = (t) => new Date(t).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", timeZone: TZ });
  const dmy = (t) => new Date(t).toLocaleDateString("en-GB", { day: "numeric", month: "short", timeZone: TZ });

  function ago(iso) {
    const t = Date.parse(iso);
    if (!t) return "";
    const s = (Date.now() - t) / 1000;
    if (s < 50) return "just now";
    if (s < 3600) return `${Math.max(1, Math.round(s / 60))} min ago`;
    if (dayKey(t) === dayKey(Date.now())) { const h = Math.round(s / 3600); return h <= 1 ? "an hour ago" : `${h} hours ago`; }
    if (dayKey(t) === dayKey(Date.now() - 864e5)) return "yesterday";
    const d = Math.max(2, Math.round(s / 86400));
    if (d < 14) return `${d} days ago`;
    if (d < 60) return `${Math.round(d / 7)} weeks ago`;
    return `on ${dmy(t)}`;
  }
  function stamp(iso) {
    const t = Date.parse(iso);
    if (!t) return "";
    if (dayKey(t) === dayKey(Date.now())) return `Today, ${hhmm(t)}`;
    if (dayKey(t) === dayKey(Date.now() - 864e5)) return `Yesterday, ${hhmm(t)}`;
    return `${dmy(t)}, ${hhmm(t)}`;
  }
  function span(fromIso, toIso) {
    const h = (Date.parse(toIso) - Date.parse(fromIso)) / 36e5;
    if (!isFinite(h) || h < 0) return "";
    if (h < 1) return "under an hour";
    if (h < 36) { const r = Math.round(h); return r === 1 ? "1 hour" : `${r} hours`; }
    return `${Math.round(h / 24)} days`;
  }
  function hoursShort(h) {
    if (h == null || !isFinite(h)) return "–";
    if (h < 1) return "Under 1 hour";
    if (h < 48) return `${Math.round(h)} hours`;
    return `${Math.round(h / 24)} days`;
  }
  const num = (n) => (n == null ? "–" : Number(n).toLocaleString("en-GB"));
  const people = (n) => (n === 1 ? "1 person says it's still there" : `${num(n)} people say it's still there`);

  function metres(aLat, aLon, bLat, bLon) {
    const R = 6371000, toR = Math.PI / 180;
    const dLat = (bLat - aLat) * toR, dLon = (bLon - aLon) * toR;
    const x = Math.sin(dLat / 2) ** 2 + Math.cos(aLat * toR) * Math.cos(bLat * toR) * Math.sin(dLon / 2) ** 2;
    return 2 * R * Math.asin(Math.sqrt(x));
  }
  const isOpen = (inc) => inc && inc.public_status && inc.public_status !== "cleared" && inc.public_status !== "closed";
  function nearestIncident(lat, lon, maxM, pred = () => true) {
    let best = null, bestD = Infinity;
    for (const inc of state.incidents.values()) {
      if (!pred(inc)) continue;
      const d = metres(lat, lon, inc.lat, inc.lon);
      if (d < bestD) { best = inc; bestD = d; }
    }
    return bestD <= maxM ? best : null;
  }

  // Local memory of "still there / gone" taps, so a phone doesn't vote twice. Optional: works without storage.
  const voted = {
    get(id) { try { return localStorage.getItem(`ft-vote-${id}`); } catch { return null; } },
    set(id, v) { try { localStorage.setItem(`ft-vote-${id}`, v); } catch { /* private mode */ } },
  };

  // This phone's own reports: always fetched and kept on the map for the session (and 24 h in storage).
  const mine = (() => {
    const KEY = "ft-mine", TTL = 864e5;
    let ids = new Map();
    try { for (const [id, at] of JSON.parse(localStorage.getItem(KEY) || "[]")) if (Date.now() - at < TTL) ids.set(Number(id), at); } catch { /* no storage */ }
    const save = () => { try { localStorage.setItem(KEY, JSON.stringify([...ids].slice(-12))); } catch { /* private mode */ } };
    return { has: (id) => ids.has(Number(id)), add(id) { if (id != null) { ids.set(Number(id), Date.now()); save(); } }, list: () => [...ids.keys()] };
  })();

  // ---------------------------------------------------------------- state
  const state = {
    incidents: new Map(), markers: new Map(), selected: null, detailSig: "", stats: null,
    showCleared: false, loaded: false, polling: false, voting: false,
    wards: null, wardLayer: null, youLayer: null, area: null,
  };
  let map;

  // ---------------------------------------------------------------- mock layer (only with ?mock=1)
  const Mock = (() => {
    const sims = new Map();
    let nextId = 900;
    function decide(chips, note) {
      const n = (note || "").toLowerCase();
      if (/asbestos|needle|syringe|chemical|oil|drum|gas/.test(n) || chips.has("Rubble")) return "specialist";
      if (chips.has("Bags")) return "hold_for_officer";
      return "clear_now";
    }
    const current = (s) => (Date.now() >= s.readyAt ? s.final : s.checking);
    function overlay(list) {
      const out = list.map((x) => (sims.has(x.id) ? clone(current(sims.get(x.id))) : x));
      for (const [id, s] of sims) if (!list.some((x) => x.id === id)) out.push(clone(current(s)));
      return out;
    }
    async function incident(id) {
      if (sims.has(id)) return clone(current(sims.get(id)));
      try { return await CH.get(`/api/incidents/${id}?view=public`); } catch { return state.incidents.get(id) || null; }
    }
    async function confirm(id, still) {
      await sleep(450);
      const base = sims.has(id) ? clone(current(sims.get(id))) : clone(state.incidents.get(id));
      const now = new Date().toISOString();
      if (still) base.still_there_count = (base.still_there_count || 0) + 1; else base.gone_count = (base.gone_count || 0) + 1;
      base.last_seen_at = now;
      base.timeline = [...(base.timeline || []), { at: now, kind: still ? "still_there" : "gone", text: "" }];
      sims.set(id, { checking: base, final: base, readyAt: 0 });
      return clone(base);
    }
    async function submit({ lat, lon, chips, note, photoUrl }) {
      await sleep(900);
      if (lat == null || lon == null) { const e = new Error("no_location"); e.status = 422; e.data = { error: "no_location" }; throw e; }
      const now = new Date().toISOString();
      const later = new Date(Date.now() + 6000).toISOString();
      const near = nearestIncident(lat, lon, SAME_M, isOpen);
      let checking, final, id;
      if (near) {
        id = near.id;
        final = clone(near);
        final.report_count = (final.report_count || 1) + 1;
        final.updated_at = now;
        final.timeline = [...(final.timeline || []), { at: now, kind: "merged", text: "" }];
        checking = { ...clone(final) };
      } else {
        id = nextId++;
        const street = (nearestIncident(lat, lon, 250) || {}).street || "Your report";
        const ward = wardAt(lat, lon) || (nearestIncident(lat, lon, 3000) || {}).ward || "Mersey Vale";
        const decision = decide(chips, note);
        checking = {
          id, case_ref: `MVCC-FT-${new Date().getFullYear()}-${String(id).padStart(4, "0")}`, lat, lon, street, ward, authority: HOME_COUNCIL,
          created_at: now, updated_at: now, status: "triaging", report_count: 1, still_there_count: 0, gone_count: 0,
          photo_url: photoUrl, cleared_photo_url: null, cleared_at: null,
          public_summary: chips.size ? [...chips].join(", ") : "Rubbish reported by a resident", triage: null,
          timeline: [{ at: now, kind: "reported", text: "" }],
        };
        final = { ...clone(checking), status: "triaged", updated_at: later, triage: { decision, fly_tip: "yes" }, timeline: [...checking.timeline, { at: later, kind: "triaged", text: "" }] };
      }
      delete checking.public_status; delete final.public_status;
      sims.set(id, { checking, final, readyAt: Date.now() + 5200 });
      return { report_id: 5000 + nextId, incident_id: id, merged: !!near, others_count: near ? near.report_count : 0, location: { lat, lon, source: "device" }, status: "triaging" };
    }
    return { overlay, incident, submit, confirm };
  })();

  // ---------------------------------------------------------------- API wrappers
  // The server answers "unchanged" in a few bytes when the list is the version this phone already has.
  let listVersion = null, lastList = [];
  async function fetchIncidents() {
    let list = await CH.get(`/api/incidents?view=public${listVersion ? `&since=${encodeURIComponent(listVersion)}` : ""}`);
    if (list && list.unchanged) list = lastList;
    else {
      if (list && list.version) listVersion = list.version;
      if (!Array.isArray(list)) list = (list && list.incidents) || [];
      lastList = list;
    }
    if (MOCK) list = Mock.overlay(list);
    list = list.map(normalize).filter((x) => x && isFinite(x.lat) && isFinite(x.lon) && (x.public_status || mine.has(x.id)));
    for (const x of list) if (!x.public_status) x.public_status = "closed";
    // Own reports the list left out (closed, filtered, or a lag): fetch each one directly.
    const have = new Set(list.map((x) => x.id));
    const missing = mine.list().filter((id) => !have.has(id));
    const extra = await Promise.all(missing.map((id) => fetchIncident(id).catch(() => null)));
    for (const x of extra) if (x && x.id != null && isFinite(x.lat) && isFinite(x.lon)) list.push(x);
    return list;
  }
  const fetchIncident = async (id) => {
    const inc = normalize(await (MOCK ? Mock.incident(id) : CH.get(`/api/incidents/${id}?view=public`)));
    if (inc && !inc.public_status && mine.has(inc.id)) inc.public_status = "closed";
    return inc;
  };
  async function confirmIncident(id, still) {
    const inc = MOCK ? await Mock.confirm(id, still) : await CH.post(`/api/incidents/${id}/confirm`, { still_there: !!still });
    voted.set(id, still ? "there" : "gone");
    if (inc && inc.id != null) { normalize(inc); state.incidents.set(inc.id, inc); syncMarkers([...state.incidents.values()], true); }
    return inc && inc.id != null ? inc : state.incidents.get(id);
  }

  // Public wording lives here, not in /api/copy, so the reviewed text is what people see.
  function loadCopy() {
    $$("[data-copy]").forEach((el) => { const v = COPY[el.dataset.copy]; if (typeof v === "string" && v.trim()) el.textContent = v; });
  }

  // ---------------------------------------------------------------- map
  function initMap() {
    map = L.map("map", { zoomControl: false, attributionControl: false, zoomSnap: 0.5 }).setView(LIVERPOOL, 13);
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19 }).addTo(map);
    if (desktop.matches) L.control.zoom({ position: "bottomright" }).addTo(map);
    map.on("click", () => { if (state.selected != null) closeDetail(); });
    $("#legend-list").innerHTML = ["new_report", "crew_booked", "further_inspection", "passed_on", "closed"].map((k) =>
      `<li><span class="mk mk--${k} mk--mini"><span class="mk-dot">${GLYPH[k] || ""}</span></span>${esc(PUB[k][0])}</li>`).join("");
    if (desktop.matches) $("#layers").open = true;
  }

  function markerHtml(inc, extra = "") {
    const cls = pub(inc);
    const glyph = GLYPH[cls] || "";
    const count = inc.report_count > 1 ? `<span class="mk-count">${inc.report_count}</span>` : "";
    const sel = state.selected === inc.id ? " is-selected" : "";
    const live = inc.status === "triaging" ? " is-live" : "";
    return `<div class="mk mk--${cls}${sel}${live} ${extra}"><span class="mk-dot">${glyph}</span>${count}</div>`;
  }
  const iconFor = (inc, extra) => L.divIcon({ className: "mk-wrap", html: markerHtml(inc, extra), iconSize: [32, 32], iconAnchor: [16, 16] });
  const sig = (inc) => [pub(inc), inc.status, inc.report_count, inc.cleared_photo_url, inc.cleared_at, inc.updated_at, inc.still_there_count, inc.gone_count, inc.last_seen_at, (inc.timeline || []).map((e) => e && e.kind).join(",")].join("|");
  const markerLabel = (inc) => `${inc.street || "Report"}: ${pubLabel(inc)}${inc.report_count > 1 ? `, ${inc.report_count} reports` : ""}`;
  const zFor = (inc) => (pub(inc) === "cleared" || pub(inc) === "closed" ? -200 : pub(inc) === "new_report" ? 400 : 200) + (mine.has(inc.id) ? 600 : 0) + (state.selected === inc.id ? 1000 : 0);
  const visible = (inc) => pub(inc) !== "cleared" || state.showCleared || state.selected === inc.id || !!inc._flash || mine.has(inc.id);

  // partial = true: list is a local merge, never a reason to drop markers.
  function syncMarkers(list, partial = false) {
    const seen = new Set();
    for (const inc of list) {
      seen.add(inc.id);
      const prev = state.incidents.get(inc.id);
      if (prev && prev._flash) inc._flash = prev._flash;
      state.incidents.set(inc.id, inc);
      let m = state.markers.get(inc.id);
      if (!m) {
        m = L.marker([inc.lat, inc.lon], { icon: iconFor(inc, state.loaded ? "is-new" : ""), title: markerLabel(inc), alt: markerLabel(inc), riseOnHover: true, keyboard: true });
        m.on("click", (e) => { L.DomEvent.stopPropagation(e); openDetail(inc.id); });
        m._sig = sig(inc);
        state.markers.set(inc.id, m);
      } else if (m._sig !== sig(inc)) {
        const justCleared = state.loaded && prev && pub(prev) !== "cleared" && pub(inc) === "cleared";
        if (justCleared) { inc._flash = Date.now(); setTimeout(() => { delete inc._flash; applyVisibility(); }, 3500); }
        m.setIcon(iconFor(inc, justCleared ? "is-cleared-now" : "is-changed"));
        m.setLatLng([inc.lat, inc.lon]);
        const el = m.getElement();
        if (el) { el.title = markerLabel(inc); el.setAttribute("alt", markerLabel(inc)); }
        m._sig = sig(inc);
        if (justCleared) celebrateCleared(inc);
      }
      m.setZIndexOffset(zFor(inc));
    }
    for (const [id, m] of state.markers) {
      if (!seen.has(id) && !partial && !mine.has(id)) { map.removeLayer(m); state.markers.delete(id); state.incidents.delete(id); }
    }
    applyVisibility();
  }
  function applyVisibility() {
    for (const [id, m] of state.markers) {
      const inc = state.incidents.get(id);
      const want = inc && visible(inc);
      const has = map.hasLayer(m);
      if (want && !has) m.addTo(map);
      else if (!want && has) map.removeLayer(m);
    }
  }
  function markSelected(id, on) {
    const m = state.markers.get(id);
    const el = m && m.getElement();
    if (el && el.firstElementChild) el.firstElementChild.classList.toggle("is-selected", on);
    const inc = state.incidents.get(id);
    if (m && inc) m.setZIndexOffset(zFor(inc));
  }
  function setShowCleared(on) {
    state.showCleared = on;
    $("#show-cleared").setAttribute("aria-pressed", String(on));
    applyVisibility();
  }

  // The part of the map not covered by floating UI, in container pixels.
  function freeRect() {
    const mc = map.getContainer().getBoundingClientRect();
    const top = ($(".top-row").getBoundingClientRect().bottom || mc.top) - mc.top + 8;
    let bottom = $("#dock").getBoundingClientRect().top - mc.top - 8;
    let left = 12;
    const d = $("#detail");
    if (state.selected != null && !d.hidden) {
      const r = d.getBoundingClientRect();
      if (desktop.matches) left = r.right - mc.left + 16;
      else bottom = window.innerHeight - d.offsetHeight - mc.top - 8;
    }
    return { top: Math.max(8, top), bottom: Math.max(top + 60, bottom), left, right: mc.width - 12, w: mc.width, h: mc.height };
  }
  function fitTo(bounds, maxZoom = 15) {
    const f = freeRect();
    map.fitBounds(bounds, { paddingTopLeft: [f.left + 12, f.top + 12], paddingBottomRight: [f.w - f.right + 12, f.h - f.bottom + 12], maxZoom });
  }
  function focusOn(latlng, zoom = 16) {
    const z = Math.max(map.getZoom(), zoom);
    const f = freeRect();
    const dx = f.w / 2 - (f.left + f.right) / 2;
    const dy = f.h / 2 - (f.top + f.bottom) / 2;
    const p = map.project(latlng, z).add([dx, dy]);
    map.setView(map.unproject(p, z), z, { animate: true });
  }
  function fitToIncidents() {
    const pts = [...state.incidents.values()].filter(visible).map((i) => [i.lat, i.lon]);
    if (pts.length) fitTo(L.latLngBounds(pts), 15);
  }

  // ---------------------------------------------------------------- polling + stats
  async function refresh() {
    if (state.polling) return;
    state.polling = true;
    try {
      syncMarkers(await fetchIncidents());
      if (!state.loaded) { state.loaded = true; fitToIncidents(); }
      if (state.selected != null) {
        // The open panel gets a fresh copy every poll, so other people's taps and status changes show up.
        const id = state.selected;
        const fresh = await fetchIncident(id).catch(() => null);
        if (fresh && fresh.id === id && fresh.public_status) { const prev = state.incidents.get(id); if (prev && prev._flash) fresh._flash = prev._flash; syncMarkers([fresh], true); }
        const inc = state.incidents.get(id);
        if (state.selected === id && inc && !state.voting && sig(inc) !== state.detailSig) {
          const box = $("#detail-inner"), top = box.scrollTop;
          renderDetail(inc);
          box.scrollTop = top;
        }
      }
      $("#live-dot").classList.remove("is-off");
    } catch (e) {
      if (/^410\b/.test(String(e && e.message))) { closeRoom(); return; }
      console.warn("incidents:", e);
      $("#live-dot").classList.add("is-off");
    } finally { state.polling = false; }
  }
  async function loadStats() {
    try {
      state.stats = await CH.get("/api/stats");
      const c = state.stats.city || {};
      const set = (k, v) => { const el = $(`[data-stat="${k}"]`); if (el && el.textContent !== v) { el.textContent = v; el.classList.remove("tick"); void el.offsetWidth; el.classList.add("tick"); } };
      set("reports", num(c.reports));
      set("cleared", num(c.cleared));
      set("median", hoursShort(c.median_hours_to_clear));
      if (state.area && state.area.ward) renderAreaCard();
    } catch (e) { console.warn("stats:", e); }
  }

  // ---------------------------------------------------------------- wards: find my area
  async function loadWards() {
    if (state.wards) return state.wards;
    try {
      const r = await fetch("/static/public/wards.geojson");
      const gj = await r.json();
      state.wards = (gj.features || []).filter((f) => f.geometry && f.properties && f.properties.ward);
    } catch (e) { console.warn("wards:", e); state.wards = []; }
    return state.wards;
  }
  function inRing(lat, lon, ring) {
    let inside = false;
    for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
      const [xi, yi] = ring[i], [xj, yj] = ring[j];
      if ((yi > lat) !== (yj > lat) && lon < ((xj - xi) * (lat - yi)) / (yj - yi) + xi) inside = !inside;
    }
    return inside;
  }
  function inGeom(lat, lon, g) {
    const polys = g.type === "Polygon" ? [g.coordinates] : g.type === "MultiPolygon" ? g.coordinates : [];
    return polys.some((p) => inRing(lat, lon, p[0]) && !p.slice(1).some((h) => inRing(lat, lon, h)));
  }
  function wardAt(lat, lon) {
    const f = (state.wards || []).find((w) => inGeom(lat, lon, w.geometry));
    return f ? f.properties.ward : null;
  }
  // Best effort for points just outside the city boundary (the API's `authority` wins when it has one).
  function neighbourAuthority(lat, lon) {
    if (metres(lat, lon, LIVERPOOL[0], LIVERPOOL[1]) > 40000) return null;
    if (lat < 53.455 && lon < -3.0) return "Wirral Council";
    if (lat < 53.345 || (lat < 53.36 && lon > -2.83)) return "Halton Borough Council";
    if (lon > -2.87 || (lat > 53.45 && lon > -2.92)) return "Knowsley Council";
    return "Sefton Council";
  }
  const wardStats = (name) => ((state.stats && state.stats.wards) || []).find((w) => w.ward === name) || null;

  async function openArea() {
    await loadWards();
    renderWardList("");
    $("#ward-q").value = "";
    $("#area-msg").hidden = true;
    openSheet("#area");
  }
  function closeArea() { closeSheet("#area"); }
  function renderWardList(q) {
    const s = q.trim().toLowerCase();
    const names = (state.wards || []).map((w) => w.properties.ward).filter((n) => !s || n.toLowerCase().includes(s)).sort((a, b) => a.localeCompare(b));
    $("#ward-list").innerHTML = names.length
      ? names.map((n) => { const w = wardStats(n); return `<li><button type="button" class="ward-btn" data-ward="${esc(n)}"><span>${esc(n)}</span>${w ? `<span class="ward-n">${num(w.reports)} reported</span>` : ""}</button></li>`; }).join("")
      : `<li class="ward-none">No wards match “${esc(q)}”.</li>`;
  }
  function showWard(name, you) {
    const f = (state.wards || []).find((w) => w.properties.ward === name);
    if (!f) return;
    if (state.wardLayer) map.removeLayer(state.wardLayer);
    state.wardLayer = L.geoJSON(f, { interactive: false, style: { color: "#4E2681", weight: 3, opacity: 0.9, fillColor: "#4E2681", fillOpacity: 0.07, dashArray: "1 0" } }).addTo(map);
    setYou(you);
    state.area = { ward: name };
    renderAreaCard();
    closeArea();
    requestAnimationFrame(() => fitTo(state.wardLayer.getBounds(), 16));
  }
  function setYou(latlng) {
    if (state.youLayer) { map.removeLayer(state.youLayer); state.youLayer = null; }
    if (latlng) state.youLayer = L.marker(latlng, { interactive: false, keyboard: false, icon: L.divIcon({ className: "you-wrap", html: '<span class="you"></span>', iconSize: [22, 22], iconAnchor: [11, 11] }) }).addTo(map);
  }
  function renderAreaCard() {
    const card = $("#area-card");
    const a = state.area;
    if (!a) { card.hidden = true; return; }
    let body;
    if (a.ward) {
      const w = wardStats(a.ward) || { reports: 0, cleared: 0 };
      body = `<div class="ac-text"><span class="ac-k">Your area</span><strong>${esc(a.ward)}</strong></div>
        <div class="ac-nums"><span><b>${num(w.reports)}</b> reported</span><span><b class="ok">${num(w.cleared)}</b> cleared</span></div>`;
    } else {
      body = `<div class="ac-text"><span class="ac-k">Outside Mersey Vale</span><strong>This area is covered by ${esc(a.authority)}</strong><span class="ac-sub">Report fly-tipping here to ${esc(a.authority)}.</span></div>`;
    }
    card.innerHTML = `${body}<button type="button" class="ac-x icon-btn" aria-label="Hide area">${ICON.close}</button>`;
    card.classList.toggle("is-out", !a.ward);
    card.hidden = false;
    $(".ac-x", card).addEventListener("click", clearArea);
    measureDock();
  }
  function clearArea() {
    state.area = null;
    if (state.wardLayer) { map.removeLayer(state.wardLayer); state.wardLayer = null; }
    setYou(null);
    renderAreaCard();
    measureDock();
  }
  function areaMsg(text) { const m = $("#area-msg"); m.textContent = text; m.hidden = !text; }
  async function locateArea() {
    if (!navigator.geolocation) { areaMsg("Your browser cannot share your location. Choose your ward from the list."); return; }
    const btn = $("#area-locate");
    btn.disabled = true;
    areaMsg("Finding your location. You may be asked for permission.");
    await loadWards();
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        btn.disabled = false;
        const lat = pos.coords.latitude, lon = pos.coords.longitude;
        const ward = wardAt(lat, lon);
        if (ward) { areaMsg(""); showWard(ward, [lat, lon]); return; }
        const authority = neighbourAuthority(lat, lon);
        if (!authority) { areaMsg("This service only covers Mersey Vale. Choose a ward from the list."); return; }
        if (state.wardLayer) { map.removeLayer(state.wardLayer); state.wardLayer = null; }
        state.area = { authority };
        setYou([lat, lon]);
        renderAreaCard();
        closeArea();
        requestAnimationFrame(() => focusOn([lat, lon], 14));
      },
      () => { btn.disabled = false; areaMsg("We could not find your location. Choose your ward from the list."); },
      { enableHighAccuracy: false, timeout: 10000, maximumAge: 10000 }
    );
  }

  // ---------------------------------------------------------------- incident detail
  // Public timeline: fixed, plain wording per event kind; anything else (notes, enforcement) is never shown.
  const TL_PUBLIC = {
    reported: "Reported with a photo",
    merged: "Reported by another resident",
    triaged: "Checked by the council",
    scheduled: "Crew booked",
    held: "Marked for inspection",
    inspected: "Inspected by the council",
    still_there: "Reported as still there",
    confirmed: "Reported as still there",
    gone: "Reported as gone",
    cleared: "Cleared",
  };
  // New public states: the backend writes public-safe text ("Passed to Network Rail…"), so use it.
  const TL_TEXT = { passed_on: "Passed to the landowner", forwarded: "Passed to the landowner", closed: "Closed: not fly-tipping", not_fly_tip: "Closed: not fly-tipping" };
  function tlText(e) {
    if (e.kind === "confirm" || e.kind === "confirmed" || e.kind === "seen") return /gone|not there/i.test(e.text || "") ? TL_PUBLIC.gone : TL_PUBLIC.still_there;
    if (TL_TEXT[e.kind]) return (e.text && e.text.trim()) || TL_TEXT[e.kind];
    return TL_PUBLIC[e.kind] || null;
  }
  function timelineHtml(inc) {
    const items = (inc.timeline || []).filter((e) => e && tlText(e)).slice().sort((a, b) => Date.parse(a.at) - Date.parse(b.at));
    // Collapse runs of the same public line (e.g. several merges) into one with a count.
    const rows = [];
    for (const e of items) {
      const t = tlText(e), last = rows[rows.length - 1];
      if (last && last.t === t && e.kind !== "reported") { last.n++; last.at = e.at; } else rows.push({ t, at: e.at, kind: e.kind, n: 1 });
    }
    if (!rows.length) return "";
    return `<ol class="tl">${rows.map((r) => `<li class="tl-${esc(r.kind)}"><span class="tl-dot" aria-hidden="true"></span><span class="tl-text">${esc(r.t)}${r.n > 1 ? ` <span class="tl-n">×${r.n}</span>` : ""}</span><time datetime="${esc(r.at)}">${esc(stamp(r.at))}</time></li>`).join("")}</ol>`;
  }
  function wazeLine(inc) {
    const bits = [`Reported ${ago(inc.created_at)}`];
    if (typeof inc.still_there_count === "number" && inc.still_there_count > 0 && pub(inc) !== "cleared") bits.push(people(inc.still_there_count));
    return bits.join(" · ");
  }
  function stillThereHtml(inc) {
    if (pub(inc) === "cleared" || pub(inc) === "closed") return "";
    const v = voted.get(inc.id);
    if (v) {
      return `<div class="still done-vote" role="status">${v === "there" ? ICON.eye : ICON.gone}<span><strong>Thank you.</strong> ${v === "there" ? "You said it is still there." : "You said it has gone."}</span></div>`;
    }
    return `<div class="still" id="still">
        <p class="still-q">Is it still there?</p>
        <div class="still-btns">
          <button type="button" class="btn btn-still" data-vote="there">${ICON.eye}Still there</button>
          <button type="button" class="btn btn-gone" data-vote="gone">${ICON.gone}It's gone</button>
        </div>
        <p class="rf-error" id="still-err" role="alert" hidden></p>
      </div>`;
  }
  function renderDetail(inc) {
    state.detailSig = sig(inc);
    const key = pub(inc);
    const cleared = key === "cleared";
    const nx = NEXT[key] || NEXT.new_report;
    const photo = cleared
      ? `<div class="d-ba">
           <figure><img src="${esc(inc.photo_url)}" alt="Before: ${esc(inc.public_summary || "reported rubbish")}" onerror="this.parentNode.classList.add('img-missing')"><figcaption>Before</figcaption></figure>
           <figure class="after">${inc.cleared_photo_url ? `<img src="${esc(inc.cleared_photo_url)}" alt="After: the same spot, cleared" onerror="this.parentNode.classList.add('img-missing')">` : `<span class="ba-clean">${ICON.check}</span>`}<figcaption>${ICON.check} After</figcaption></figure>
         </div>`
      : `<figure class="d-photo"><img src="${esc(inc.photo_url)}" alt="Photo of ${esc(inc.public_summary || "the reported rubbish")}" onerror="this.parentNode.classList.add('img-missing')"></figure>`;
    const reports = inc.report_count > 1 ? `${inc.report_count} reports` : "1 report";
    const outside = inc.authority && !HOME_AUTH.has(inc.authority) ? `<p class="d-auth">${ICON.warn}<span>This area is covered by ${esc(inc.authority)}.</span></p>` : "";
    $("#detail-inner").innerHTML = `
      <div class="d-bar">
        <span class="d-grab" aria-hidden="true"></span>
        <button type="button" class="d-close icon-btn" aria-label="Close details">${ICON.close}</button>
      </div>
      ${photo}
      <div class="d-body">
        <div class="d-status">${pill(inc)}<span class="d-count">${ICON.people}${esc(reports)}</span></div>
        <h2 id="d-title">${esc(inc.street || "Reported fly-tipping")}</h2>
        <p class="d-meta">${esc(inc.ward || "Mersey Vale")}${inc.case_ref ? ` · <span class="mono">${esc(inc.case_ref)}</span>` : ""}</p>
        <p class="d-waze" id="d-waze">${esc(wazeLine(inc))}</p>
        ${outside}
        ${inc.public_summary ? `<p class="d-summary">${esc(inc.public_summary)}</p>` : ""}
        ${cleared && inc.cleared_at ? `<p class="d-cleared">${ICON.check} Cleared ${esc(ago(inc.cleared_at))}, ${esc(span(inc.created_at, inc.cleared_at))} after the first report.</p>` : ""}
        ${stillThereHtml(inc)}
        <div class="next next--${esc(key)}">
          <p class="next-k">${key === "cleared" || key === "closed" ? "Outcome" : "What happens next"}</p>
          <p class="next-t">${esc(nx.title)}.</p>
          <p class="next-s">${esc(nx.text)}</p>
        </div>
        <h3 class="h-small">Updates</h3>
        ${timelineHtml(inc)}
        ${cleared ? `<button type="button" class="btn btn-ghost btn-block" data-report-here>${ICON.photoPin}<span>Report new fly-tipping here</span></button>` : ""}
      </div>`;
    const d = $("#detail");
    $(".d-close", d).addEventListener("click", () => closeDetail());
    const rh = $("[data-report-here]", d);
    if (rh) rh.addEventListener("click", () => openReport(inc));
    $$("[data-vote]", d).forEach((b) => b.addEventListener("click", () => vote(inc.id, b.dataset.vote === "there", b)));
  }
  async function vote(id, still, btn) {
    const box = $("#still");
    $$("[data-vote]", box).forEach((b) => (b.disabled = true));
    btn.classList.add("is-busy");
    state.voting = true;
    try {
      const inc = await confirmIncident(id, still);
      state.voting = false;
      if (state.selected === id && inc) renderDetail(inc);
      toast(`<span class="toast-ok">${ICON.check}</span><span><strong>Thank you</strong><span>${still ? "The council has been told it is still there." : "The council has been told it has gone."}</span></span>`, 3500);
    } catch (e) {
      console.warn("confirm:", e);
      state.voting = false;
      $$("[data-vote]", box).forEach((b) => (b.disabled = false));
      btn.classList.remove("is-busy");
      const err = $("#still-err");
      err.textContent = "Sorry, that did not send. Try again.";
      err.hidden = false;
    }
  }

  function openDetail(id) {
    const inc = state.incidents.get(id);
    if (!inc) return;
    const prev = state.selected;
    state.selected = id;
    if (prev != null && prev !== id) markSelected(prev, false);
    applyVisibility();
    markSelected(id, true);
    renderDetail(inc);
    const el = $("#detail");
    const wasOpen = !el.hidden && el.classList.contains("is-open");
    el.hidden = false;
    document.body.classList.add("detail-open");
    requestAnimationFrame(() => {
      el.classList.add("is-open");
      $("#detail-inner").scrollTop = 0;
      setTimeout(() => focusOn([inc.lat, inc.lon], 16), wasOpen ? 0 : 60);
      const btn = $(".d-close", el);
      if (btn) btn.focus({ preventScroll: true });
    });
  }
  function closeDetail() {
    const el = $("#detail");
    const id = state.selected;
    state.selected = null;
    if (id != null) markSelected(id, false);
    applyVisibility();
    el.classList.remove("is-open");
    document.body.classList.remove("detail-open");
    setTimeout(() => { if (state.selected == null) el.hidden = true; }, 280);
    const m = id != null && state.markers.get(id);
    const mel = m && m.getElement();
    if (mel && document.activeElement && el.contains(document.activeElement)) mel.focus({ preventScroll: true });
  }

  // ---------------------------------------------------------------- toast + cleared moment
  let toastTimer;
  function toast(html, ms = 5200, onClick) {
    const t = $("#toast");
    t.innerHTML = html;
    t.hidden = false;
    t.onclick = onClick || null;
    t.classList.toggle("is-clickable", !!onClick);
    requestAnimationFrame(() => t.classList.add("is-in"));
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { t.classList.remove("is-in"); setTimeout(() => (t.hidden = true), 300); }, ms);
  }
  function celebrateCleared(inc) {
    toast(`${inc.cleared_photo_url ? `<img src="${esc(inc.cleared_photo_url)}" alt="">` : `<span class="toast-ok">${ICON.check}</span>`}
      <span><strong>Cleared: ${esc(inc.street || "a report")}</strong><span>${inc.cleared_photo_url ? "View the before and after photos." : "View the report."}</span></span>`, 6500, () => openDetail(inc.id));
  }

  // ---------------------------------------------------------------- the room closed
  // The presenter can close the demo to the room (scripts/room.sh off): the server then answers 410, and the page
  // stops polling and says so, which gives the venue wifi back.
  let roomClosed = false;
  function closeRoom() {
    if (roomClosed) return;
    roomClosed = true;
    $("#live-dot").classList.add("is-off");
    const b = document.createElement("div");
    b.setAttribute("role", "status");
    b.style.cssText = "position:fixed;left:16px;right:16px;top:72px;z-index:3000;padding:14px 16px;border-radius:12px;" +
      "background:var(--panel,#fff);color:var(--ink,#202427);box-shadow:0 6px 20px rgba(21,32,28,.18);font:600 16px/1.4 var(--font-body,system-ui)";
    b.textContent = "The live demonstration has finished. Thank you for taking part.";
    document.body.appendChild(b);
  }

  // ---------------------------------------------------------------- smaller uploads
  // Phone photos are often 3 to 5 MB. The location is already read from the original (readExifGps), so send a
  // 1600 px JPEG instead: the server keeps no more than that anyway. Any failure sends the original.
  async function shrinkPhoto(file) {
    try {
      if (!file || file.size < 700000 || !window.createImageBitmap) return file;
      const bmp = await createImageBitmap(file, { imageOrientation: "from-image" });
      const k = Math.min(1, 1600 / Math.max(bmp.width, bmp.height));
      const c = document.createElement("canvas");
      c.width = Math.round(bmp.width * k); c.height = Math.round(bmp.height * k);
      c.getContext("2d").drawImage(bmp, 0, 0, c.width, c.height);
      if (bmp.close) bmp.close();
      const blob = await new Promise((r) => c.toBlob(r, "image/jpeg", 0.82));
      return blob && blob.size < file.size ? blob : file;
    } catch (e) { console.warn("shrink:", e); return file; }
  }

  // ---------------------------------------------------------------- EXIF GPS (hand-written JPEG parser)
  // Reads the APP1 Exif segment, follows IFD0 -> GPS IFD (tag 0x8825) and converts
  // GPSLatitude/GPSLongitude (3 rationals: deg, min, sec) with their N/S, E/W refs.
  async function readExifGps(file) {
    try {
      const buf = await file.slice(0, 512 * 1024).arrayBuffer();
      const v = new DataView(buf);
      if (v.byteLength < 4 || v.getUint16(0) !== 0xffd8) return null;
      let off = 2;
      while (off + 4 <= v.byteLength) {
        if (v.getUint8(off) !== 0xff) return null;
        const marker = v.getUint8(off + 1);
        if (marker === 0xda || marker === 0xd9) return null; // start of image data: no EXIF before it
        const len = v.getUint16(off + 2);
        if (marker === 0xe1 && off + 10 <= v.byteLength && v.getUint32(off + 4) === 0x45786966 && v.getUint16(off + 8) === 0) {
          return parseTiffGps(v, off + 10, Math.min(v.byteLength, off + 2 + len));
        }
        off += 2 + len;
      }
    } catch (e) { console.warn("exif:", e); }
    return null;
  }
  function parseTiffGps(v, t, end) {
    const le = v.getUint16(t) === 0x4949;
    const u16 = (o) => v.getUint16(t + o, le);
    const u32 = (o) => v.getUint32(t + o, le);
    const i32 = (o) => v.getInt32(t + o, le);
    if (u16(2) !== 42) return null;
    const ifd0 = u32(4);
    const n0 = u16(ifd0);
    let gps = 0;
    for (let i = 0; i < n0; i++) { const e = ifd0 + 2 + i * 12; if (u16(e) === 0x8825) gps = u32(e + 8); }
    if (!gps || t + gps + 2 > end) return null;
    const g = {};
    const n = u16(gps);
    for (let i = 0; i < n; i++) {
      const e = gps + 2 + i * 12;
      const tag = u16(e), type = u16(e + 2), count = u32(e + 4);
      if ((tag === 1 || tag === 3) && type === 2) g[tag] = String.fromCharCode(v.getUint8(t + e + 8));
      if ((tag === 2 || tag === 4) && (type === 5 || type === 10) && count >= 3) {
        const at = u32(e + 8);
        const rd = type === 5 ? u32 : i32;
        const parts = [0, 1, 2].map((k) => { const d = rd(at + k * 8 + 4); return d ? rd(at + k * 8) / d : 0; });
        g[tag] = parts[0] + parts[1] / 60 + parts[2] / 3600;
      }
    }
    if (g[2] == null || g[4] == null) return null;
    const lat = (g[1] === "S" ? -1 : 1) * g[2];
    const lon = (g[3] === "W" ? -1 : 1) * g[4];
    if (!isFinite(lat) || !isFinite(lon) || Math.abs(lat) > 90 || Math.abs(lon) > 180 || (lat === 0 && lon === 0)) return null;
    return { lat, lon };
  }

  // ---------------------------------------------------------------- sheets (report flow + find my area)
  let sheetOpener = null;
  function openSheet(sel) {
    const el = $(sel);
    sheetOpener = document.activeElement;
    el.hidden = false;
    document.documentElement.classList.add("rf-lock");
    requestAnimationFrame(() => el.classList.add("is-open"));
  }
  function closeSheet(sel) {
    const el = $(sel);
    el.classList.remove("is-open");
    if ($$(".rf.is-open").length === 0) document.documentElement.classList.remove("rf-lock");
    setTimeout(() => { if (!el.classList.contains("is-open")) el.hidden = true; }, 280);
    if (sheetOpener && document.contains(sheetOpener) && sheetOpener.offsetParent) sheetOpener.focus({ preventScroll: true });
  }

  // ---------------------------------------------------------------- report flow
  const RF = { step: null, file: null, url: null, lat: null, lon: null, src: null, prefill: null, chips: new Set(), result: null, poll: null, shownAt: 0, lastKey: null, sending: false, same: null, sameSkipped: null };
  const STEP_LABEL = { photo: "Photo", place: "Location", same: "Location", details: "Details" };
  let mini = null, miniPin = null;

  function openReport(prefill) {
    if (RF.poll) clearTimeout(RF.poll);
    Object.assign(RF, { step: null, file: null, lat: null, lon: null, src: null, prefill: null, result: null, poll: null, lastKey: null, sending: false, same: null, sameSkipped: null });
    RF.chips = new Set();
    if (RF.url) { URL.revokeObjectURL(RF.url); RF.url = null; }
    if (prefill) { RF.prefill = prefill; RF.lat = prefill.lat; RF.lon = prefill.lon; RF.src = "prefill"; }
    $("#rf-camera").value = ""; $("#rf-library").value = "";
    $("#rf-preview").hidden = true; $("#rf-shoot").hidden = false; $("#rf-preview-flag").hidden = true;
    $("#rf-photo-error").hidden = true; $("#rf-send-error").hidden = true; $("#rf-same-error").hidden = true;
    $("#rf-note").value = "";
    $("#rf-title").textContent = prefill ? "Report new fly-tipping here" : "Report fly-tipping";
    $("#rf-chips").innerHTML = CHIPS.map((c) => `<button type="button" class="chip" aria-pressed="false" data-chip="${esc(c)}"><span class="chip-tick" aria-hidden="true">${ICON.check}</span>${esc(c)}</button>`).join("");
    openSheet("#report");
    go("photo");
  }
  function closeReport() {
    if (RF.poll) { clearTimeout(RF.poll); RF.poll = null; }
    closeSheet("#report");
  }

  function go(step) {
    RF.step = step;
    $$("#report [data-step]").forEach((s) => (s.hidden = s.dataset.step !== step));
    const idx = ["photo", "place", "details"].indexOf(step === "same" ? "place" : step);
    $("#rf-progress").hidden = step === "done";
    $$("#rf-progress .rf-bars li").forEach((li, i) => { li.classList.toggle("on", i <= idx); li.classList.toggle("now", i === idx); });
    if (idx >= 0) $("#rf-steplabel").textContent = `Step ${idx + 1} of 3 · ${STEP_LABEL[step]}`;
    $("#rf-main").scrollTop = 0;
    updateFoot();
    if (step === "place") enterPlace();
    if (step === "same") renderSame();
    if (step === "details") renderRecap();
    const h = $(`#report [data-step="${step}"] .rf-h, #report [data-step="${step}"] .done-h`);
    if (h) setTimeout(() => h.focus({ preventScroll: true }), 60);
  }
  function updateFoot() {
    const back = $("#rf-back"), next = $("#rf-next");
    next.className = "btn btn-primary";
    back.hidden = false; next.hidden = false;
    if (RF.step === "photo") { back.textContent = "Cancel"; next.textContent = "Next"; next.disabled = !RF.file; }
    if (RF.step === "place") { back.textContent = "Back"; next.textContent = "Next"; next.disabled = RF.lat == null; }
    if (RF.step === "same") { back.textContent = "Back"; next.hidden = true; }
    if (RF.step === "details") { back.textContent = "Back"; next.className = "btn btn-tape"; next.innerHTML = RF.sending ? '<span class="spin" aria-hidden="true"></span>Sending…' : "Send report"; next.disabled = RF.sending; }
    if (RF.step === "done") { back.textContent = "Done"; next.textContent = "View on map"; next.disabled = !RF.result; }
  }
  function onBack() {
    if (RF.step === "photo" || RF.step === "done") return closeReport();
    if (RF.step === "place") return go("photo");
    if (RF.step === "same") return go("place");
    if (RF.step === "details") return go("place");
  }
  function onNext() {
    if (RF.step === "photo" && RF.file) return go("place");
    if (RF.step === "place" && RF.lat != null) {
      // Before a new report: is there an open report within ~40 m? Ask if it's the same pile.
      const near = RF.prefill ? null : nearestIncident(RF.lat, RF.lon, SAME_M, isOpen);
      if (near && RF.sameSkipped !== near.id) { RF.same = near; return go("same"); }
      return go("details");
    }
    if (RF.step === "details") return submit();
    if (RF.step === "done" && RF.result) {
      const id = RF.result.incident_id;
      closeReport();
      refresh().then(() => openDetail(id));
    }
  }

  // Step 1: photo. Phones get camera wording; mouse-and-keyboard devices get "Upload a photo" and drag-and-drop.
  function setPhotoWording() {
    $$("#report [data-touch]").forEach((el) => { el.textContent = touch ? el.dataset.touch : el.dataset.desk; });
    if (touch) return;
    $("#rf-camera").removeAttribute("capture");
    $("#rf-library-link").hidden = true;
    const dz = $("#rf-dropzone");
    ["dragenter", "dragover"].forEach((t) => dz.addEventListener(t, (e) => { e.preventDefault(); dz.classList.add("is-drag"); }));
    ["dragleave", "drop"].forEach((t) => dz.addEventListener(t, () => dz.classList.remove("is-drag")));
    dz.addEventListener("drop", (e) => { e.preventDefault(); const f = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0]; if (f) onFile({ files: [f] }); });
  }
  async function onFile(input) {
    const file = input.files && input.files[0];
    if (!file) return;
    const err = $("#rf-photo-error");
    if (file.type && !file.type.startsWith("image/")) { err.textContent = "The file must be a photo."; err.hidden = false; return; }
    err.hidden = true;
    RF.file = file;
    if (RF.url) URL.revokeObjectURL(RF.url);
    RF.url = URL.createObjectURL(file);
    $("#rf-preview-img").src = RF.url;
    $("#rf-preview").hidden = false;
    $("#rf-shoot").hidden = true;
    $("#rf-preview-flag").hidden = true;
    if (RF.src === "photo") { RF.src = RF.prefill ? "prefill" : null; RF.lat = RF.prefill ? RF.prefill.lat : null; RF.lon = RF.prefill ? RF.prefill.lon : null; }
    const gps = await readExifGps(file);
    if (RF.file !== file) return;
    if (gps) { RF.lat = gps.lat; RF.lon = gps.lon; RF.src = "photo"; $("#rf-preview-flag").hidden = false; }
    updateFoot();
    setTimeout(() => { if (RF.step === "photo" && RF.file === file) go("place"); }, gps ? 1100 : 700);
  }

  // Step 2: place
  function ensureMini() {
    if (mini) return;
    mini = L.map("minimap", { zoomControl: false, attributionControl: false }).setView(LIVERPOOL, 15);
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19 }).addTo(mini);
    L.control.zoom({ position: "topright" }).addTo(mini);
    mini.on("click", (e) => { setPin(e.latlng.lat, e.latlng.lng, "map"); banner("moved"); });
  }
  function pinIcon(drop) {
    return L.divIcon({ className: "rf-pin-wrap", html: `<div class="rf-pin${drop ? " drop" : ""}"><svg viewBox="0 0 36 46" width="36" height="46" aria-hidden="true"><path d="M18 1C8.6 1 1 8.4 1 17.6 1 30 18 45 18 45s17-15 17-27.4C35 8.4 27.4 1 18 1Z" fill="var(--brand)" stroke="#fff" stroke-width="2"/><circle cx="18" cy="17.5" r="6.5" fill="var(--tape)"/></svg><span class="rf-pin-ring"></span></div>`, iconSize: [36, 46], iconAnchor: [18, 45] });
  }
  function setPin(lat, lon, src, { drop = false, zoom } = {}) {
    RF.lat = lat; RF.lon = lon; RF.src = src;
    if (!miniPin) {
      miniPin = L.marker([lat, lon], { icon: pinIcon(drop), draggable: true, keyboard: true, title: "Location of the rubbish. Drag to move", alt: "Location pin" }).addTo(mini);
      miniPin.on("dragend", () => { const p = miniPin.getLatLng(); RF.lat = p.lat; RF.lon = p.lng; RF.src = "map"; banner("moved"); });
    } else {
      miniPin.setLatLng([lat, lon]);
      if (drop) miniPin.setIcon(pinIcon(true));
    }
    if (zoom) mini.setView([lat, lon], zoom, { animate: false }); else mini.panTo([lat, lon]);
    updateFoot();
  }
  function placeText(lat, lon) {
    const near = nearestIncident(lat, lon, 220);
    const ward = wardAt(lat, lon);
    return [near && near.street ? `Near ${near.street}` : "", ward || ""].filter(Boolean).join(", ");
  }
  function banner(kind, msg) {
    const b = $("#rf-loc");
    let sub = RF.lat != null ? esc(placeText(RF.lat, RF.lon)) : "";
    if (RF.lat != null && state.wards && state.wards.length && !wardAt(RF.lat, RF.lon)) {
      const a = neighbourAuthority(RF.lat, RF.lon);
      if (a) sub = `This location may be covered by ${esc(a)}, not Mersey Vale.`;
    }
    const views = {
      photo: [ICON.photoPin, "Location found in your photo", sub || "Drag the pin if it is not right."],
      prefill: [ICON.pin, `Same place as the report on ${RF.prefill ? esc(RF.prefill.street || "this street") : "this street"}`, "Drag the pin if it is somewhere else."],
      gps: [ICON.locate, "Using your current location", sub],
      finding: ['<span class="spin dark" aria-hidden="true"></span>', "Finding your location", "You may be asked for permission."],
      manual: [ICON.tap, `${TAP} the map where the rubbish is`, "Your photo does not include a location."],
      moved: [ICON.pin, "Pin placed", sub || "Drag the pin to adjust it."],
      error: [ICON.warn, "Show where the rubbish is", msg || `${TAP} the map to place a pin.`],
    };
    const [icon, title, text] = views[kind] || views.manual;
    b.className = `locbanner is-${kind}`;
    b.innerHTML = `<span class="lb-icon">${icon}</span><span class="lb-text"><strong>${title}</strong>${text ? `<span>${text}</span>` : ""}</span>`;
  }
  function enterPlace() {
    ensureMini();
    loadWards();
    requestAnimationFrame(() => {
      mini.invalidateSize();
      if (RF.lat != null) {
        setPin(RF.lat, RF.lon, RF.src, { drop: RF.src === "photo", zoom: 17 });
        banner(RF.src === "photo" ? "photo" : RF.src === "prefill" ? "prefill" : RF.src === "device" ? "gps" : "moved");
      } else {
        mini.setView(map ? map.getCenter() : L.latLng(LIVERPOOL), 15, { animate: false });
        locate(true);
      }
    });
  }
  function locate(auto) {
    if (!navigator.geolocation) { if (RF.lat == null) banner("manual"); return; }
    if (!auto || RF.lat == null) banner("finding");
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        if (RF.step !== "place") return;
        if (auto && (RF.src === "photo" || RF.src === "map")) return;
        setPin(pos.coords.latitude, pos.coords.longitude, "device", { drop: true, zoom: 17 });
        banner("gps");
      },
      () => { if (RF.step === "place") banner(RF.lat == null ? "manual" : "moved"); },
      { enableHighAccuracy: true, timeout: 9000, maximumAge: 60000 }
    );
  }

  // Step 2b: same pile?
  function renderSame() {
    const inc = RF.same;
    if (!inc) return go("details");
    const d = Math.round(metres(RF.lat, RF.lon, inc.lat, inc.lon));
    $("#rf-same-error").hidden = true;
    $("#rf-same").innerHTML = `
      <div class="same-card">
        <div class="same-photos">
          <figure><img src="${esc(inc.photo_url)}" alt="Photo from the earlier report" onerror="this.parentNode.classList.add('img-missing')"><figcaption>Already reported</figcaption></figure>
          <figure><img src="${esc(RF.url || "")}" alt="Your photo"><figcaption>Your photo</figcaption></figure>
        </div>
        <div class="same-body">
          <div class="d-status">${pill(inc)}<span class="d-count">${ICON.people}${inc.report_count > 1 ? `${inc.report_count} reports` : "1 report"}</span></div>
          <p class="same-street"><strong>${esc(inc.street || "Nearby")}</strong> · ${d < 5 ? "same place" : `${d} m away`}</p>
          ${inc.public_summary ? `<p class="same-sum">${esc(inc.public_summary)}</p>` : ""}
          <p class="d-waze">${esc(wazeLine(inc))}</p>
        </div>
      </div>
      <button type="button" class="btn btn-tape btn-block btn-big" id="same-yes">${ICON.eye}Yes, it is the same</button>
      <button type="button" class="btn btn-ghost btn-block btn-big" id="same-no">No, it is different</button>
      <p class="fine">If you choose yes, the council will be told it is still there. Your photo will not be sent.</p>`;
    $("#same-yes").addEventListener("click", sameYes);
    $("#same-no").addEventListener("click", () => { RF.sameSkipped = inc.id; go("details"); });
  }
  async function sameYes() {
    const inc = RF.same;
    const btn = $("#same-yes");
    btn.disabled = true; $("#same-no").disabled = true;
    btn.innerHTML = '<span class="spin" aria-hidden="true"></span>Sending…';
    try {
      const upd = await confirmIncident(inc.id, true);
      RF.result = { incident_id: inc.id, confirmed: true };
      mine.add(inc.id);
      renderDoneConfirm(upd || inc);
      go("done");
    } catch (e) {
      console.warn("confirm:", e);
      btn.disabled = false; $("#same-no").disabled = false;
      btn.innerHTML = `${ICON.eye}Yes, it is the same`;
      const err = $("#rf-same-error");
      err.textContent = "Sorry, that did not send. Check your connection and try again.";
      err.hidden = false;
    }
  }
  function renderDoneConfirm(inc) {
    const n = inc.still_there_count;
    $("#rf-done").innerHTML = `
      <div class="done-hero">
        <span class="done-badge" aria-hidden="true">${ICON.eye}</span>
        <div>
          <h3 class="done-h" tabindex="-1">Thank you</h3>
          <p class="done-count">${typeof n === "number" && n > 0 ? esc(people(n)) : "The council has been told it is still there."}</p>
        </div>
      </div>
      <div class="live">
        <div class="live-photo"><img src="${esc(inc.photo_url)}" alt="" onerror="this.parentNode.classList.add('img-missing')"></div>
        <div class="live-body">
          <p class="live-k">Status</p>
          <div class="live-pill">${pill(inc)}</div>
          <p class="live-where">${esc([inc.street, inc.ward].filter(Boolean).join(" · "))}</p>
        </div>
      </div>
      <div class="done-tl">${timelineHtml(inc)}</div>`;
  }

  // Step 3: details
  function renderRecap() {
    const where = RF.lat != null ? (placeText(RF.lat, RF.lon) || `${RF.lat.toFixed(5)}, ${RF.lon.toFixed(5)}`) : "";
    const how = { photo: "Location from your photo", device: "Your current location", map: "Location set on the map", prefill: "Same place as the earlier report" }[RF.src] || "";
    $("#rf-recap").innerHTML = RF.url ? `<img src="${RF.url}" alt=""><span><strong>${esc(where)}</strong><span>${esc(how)}</span></span>` : "";
  }

  async function submit() {
    if (RF.sending) return;
    const err = $("#rf-send-error");
    err.hidden = true;
    if (!RF.file) return go("photo");
    RF.sending = true;
    updateFoot();
    const note = $("#rf-note").value.trim();
    const desc = [[...RF.chips].join(", "), note].filter(Boolean).join(". ");
    try {
      let res;
      if (MOCK) res = await Mock.submit({ lat: RF.lat, lon: RF.lon, chips: RF.chips, note, photoUrl: RF.url });
      else {
        const fd = new FormData();
        const photo = STAGE ? RF.file : await shrinkPhoto(RF.file);
        fd.append("photo", photo, RF.file.name || "photo.jpg");
        if (STAGE) fd.append("stage", "1");
        if (RF.lat != null) { fd.append("lat", String(RF.lat)); fd.append("lon", String(RF.lon)); }
        fd.append("loc_source", RF.src === "map" || RF.src === "prefill" ? "map" : "device");
        fd.append("description", desc);
        res = await CH.post("/api/reports", fd);
      }
      RF.sending = false;
      RF.result = res;
      mine.add(res && res.incident_id);
      renderDone(res);
      go("done");
      RF.shownAt = Date.now();
      RF.poll = setTimeout(pollStatus, 1200);
      refresh();
      loadStats();
    } catch (e) {
      RF.sending = false;
      if (e && e.status === 422 && e.data && e.data.error === "no_location") {
        go("place");
        banner("error", `We could not find a location in your photo. ${TAP} the map to place a pin.`);
        return;
      }
      console.warn("report:", e);
      err.textContent = "Sorry, your report did not send. Check your connection and try again.";
      err.hidden = false;
      updateFoot();
    }
  }

  function renderDone() {
    $("#rf-done").innerHTML = `
      <div class="done-hero">
        <span class="done-badge" aria-hidden="true">${ICON.check}</span>
        <div>
          <h3 class="done-h" tabindex="-1">Report sent</h3>
          <p class="done-count">Thank you. The council will check it soon.</p>
        </div>
      </div>
      <div class="live" id="rf-live">
        <div class="live-photo"><img src="${esc(RF.url || "")}" alt="Your photo"></div>
        <div class="live-body">
          <p class="live-k">Status</p>
          <div class="live-pill" id="rf-live-pill">${pill({ public_status: "new_report" })}</div>
          <p class="live-where" id="rf-live-where"></p>
          <p class="live-ref mono" id="rf-live-ref"></p>
        </div>
      </div>
      <div class="done-tl" id="rf-live-tl">${timelineHtml({ timeline: [{ at: new Date().toISOString(), kind: "reported" }] })}</div>`;
    RF.lastKey = "new_report";
  }
  async function pollStatus() {
    if (RF.step !== "done" || !RF.result || RF.result.confirmed) return;
    try { const inc = await fetchIncident(RF.result.incident_id); if (inc) updateLive(inc); } catch (e) { console.warn("status:", e); }
    if (RF.step === "done") RF.poll = setTimeout(pollStatus, STATUS_POLL_MS);
  }
  function updateLive(inc) {
    const key = inc.public_status || "new_report";
    if (key !== "new_report" && Date.now() - RF.shownAt < 2200) return; // let "New report" register before the answer lands
    $("#rf-live-where").textContent = [inc.street, inc.ward].filter(Boolean).join(" · ");
    if (inc.case_ref) $("#rf-live-ref").textContent = `Reference: ${inc.case_ref}`;
    const tl = $("#rf-live-tl");
    if (tl && (inc.timeline || []).length) { const h = timelineHtml(inc); if (h && tl.innerHTML !== h) tl.innerHTML = h; }
    if (key !== RF.lastKey) {
      RF.lastKey = key;
      const box = $("#rf-live-pill");
      box.innerHTML = pill({ public_status: key });
      box.classList.remove("pop"); void box.offsetWidth; box.classList.add("pop");
    }
  }

  // Keep keyboard focus inside an open sheet.
  function trapFocus(e) {
    if (e.key !== "Tab") return;
    const open = $$(".rf.is-open").pop();
    if (!open) return;
    const f = $$('button:not([disabled]), [href], input:not(.vh-input), textarea, label[for], [tabindex="0"]', open).filter((el) => el.offsetParent !== null && !el.hidden);
    if (!f.length) return;
    const first = f[0], last = f[f.length - 1];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  }

  function measureDock() {
    const h = $("#dock").offsetHeight;
    document.documentElement.style.setProperty("--dock-h", `${h}px`);
  }

  // ---------------------------------------------------------------- wiring
  function wire() {
    document.addEventListener("click", (e) => {
      if (e.target.closest("[data-open-report]")) { e.preventDefault(); openReport(null); return; }
      if (e.target.closest("[data-rf-close]")) { closeReport(); return; }
      if (e.target.closest("[data-area-close]")) { closeArea(); return; }
      const wb = e.target.closest("[data-ward]");
      if (wb) { showWard(wb.dataset.ward, null); return; }
      const chip = e.target.closest("[data-chip]");
      if (chip) {
        const c = chip.dataset.chip;
        if (RF.chips.has(c)) RF.chips.delete(c); else RF.chips.add(c);
        chip.setAttribute("aria-pressed", String(RF.chips.has(c)));
      }
      const lay = $("#layers");
      if (lay.open && !desktop.matches && !e.target.closest("#layers")) lay.open = false;
    });
    $("#rf-back").addEventListener("click", onBack);
    $("#rf-next").addEventListener("click", onNext);
    $("#rf-camera").addEventListener("change", (e) => onFile(e.target));
    $("#rf-library").addEventListener("change", (e) => onFile(e.target));
    $("#rf-locate").addEventListener("click", () => locate(false));
    $("#show-cleared").addEventListener("click", () => setShowCleared(!state.showCleared));
    $("#find-area").addEventListener("click", openArea);
    $("#area-locate").addEventListener("click", locateArea);
    $("#ward-q").addEventListener("input", (e) => renderWardList(e.target.value));
    $$("label.dropzone, label.linkish, label.preview-change").forEach((l) => {
      l.tabIndex = 0;
      l.setAttribute("role", "button");
      l.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); l.click(); } });
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") {
        if (!$("#report").hidden) closeReport();
        else if (!$("#area").hidden) closeArea();
        else if (state.selected != null) closeDetail();
      }
      trapFocus(e);
    });
    desktop.addEventListener("change", () => { setTimeout(() => map.invalidateSize(), 50); if (state.selected != null) renderDetail(state.incidents.get(state.selected)); });
    const setHdr = () => { document.documentElement.style.setProperty("--hdr", `${$(".ch-header").offsetHeight}px`); measureDock(); };
    setHdr();
    window.addEventListener("resize", setHdr);
  }

  // ---------------------------------------------------------------- hosted copy
  // A hosted copy (decision 6) belongs to one visitor, who may have no photo of fly-tipping to hand, so it offers the
  // demo kit (seed/live_demo, by its numbers). Each kit photo is under 700 KB, so it is sent byte for byte: its GPS
  // drops the pin and its reading comes from the cache.
  const KIT_LABELS = { 1: "Black bags", 2: "A fridge", 3: "Paint tins", 4: "A mattress", 5: "Near an earlier report" };
  async function loadHosted() {
    if (MOCK) return;
    let c;
    try { c = await CH.get("/api/config"); } catch (e) { return; }
    if (!c || !c.hosted) return;
    COPY.privacy_note = "This copy of the demo is yours alone. Your photo is seen only by you, has its hidden data removed, and is read by an AI model on Cloudflare. It is deleted when your session ends.";
    loadCopy();
    if (!(c.kit || []).length) return;
    const box = document.createElement("div");
    box.className = "kit";
    box.innerHTML = `<p class="kit-h">No photo to hand? Try one of ours.</p><div class="kit-row">${c.kit.map((n) =>
      `<button type="button" class="kit-pick" data-kit="${esc(n)}"><img src="/media/kit/${encodeURIComponent(n)}" alt="" loading="lazy"><span>${esc(KIT_LABELS[parseInt(n, 10)] || "")}</span></button>`).join("")}</div>`;
    $("#rf-shoot").appendChild(box);
    box.addEventListener("click", async (e) => {
      const b = e.target.closest("[data-kit]");
      if (!b) return;
      try {
        const r = await fetch(`/media/kit/${encodeURIComponent(b.dataset.kit)}`);
        if (!r.ok) throw new Error(`${r.status}`);
        onFile({ files: [new File([await r.blob()], b.dataset.kit, { type: "image/jpeg" })] });
      } catch (err) {
        const el = $("#rf-photo-error");
        el.textContent = "Could not load that photo. Try again.";
        el.hidden = false;
      }
    });
  }

  function start() {
    if (!window.L || !window.CH) { console.error("Leaflet or CH missing"); return; }
    wire();
    setPhotoWording();
    initMap();
    loadCopy();
    loadHosted();
    loadWards();
    loadStats();
    refresh();
    setInterval(() => { if (!document.hidden && !roomClosed) refresh(); }, POLL_MS);  // no polling from a locked phone
    document.addEventListener("visibilitychange", () => { if (!document.hidden && !roomClosed) refresh(); });
    setInterval(() => { if (!roomClosed) loadStats(); }, 15000);
    setInterval(() => { if (state.selected != null) { const inc = state.incidents.get(state.selected); const el = $("#d-waze"); if (inc && el) el.textContent = wazeLine(inc); } }, 30000);
    if (MOCK) document.body.classList.add("is-mock");
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})();
