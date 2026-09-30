// Council console. Plain ES2020, no build step.
// Reads the API through window.CH (static/shared/api.js). Add ?mock=1 to run on static/council/mock/.
// Routes, Return and Reduce are separate modules: window.CHViews = { routes, ret, reduce }.
(() => {
  "use strict";

  const CH = window.CH;
  const STATUS = Object.assign({}, CH.STATUS, { triaging: ["Processing", "triaging"] });
  const MOCK = CH.MOCK;
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const TZ = "Europe/London";
  const tFmt = new Intl.DateTimeFormat("en-GB", { timeZone: TZ, hour: "2-digit", minute: "2-digit" });
  const dFmt = new Intl.DateTimeFormat("en-GB", { timeZone: TZ, weekday: "short", day: "numeric", month: "short" });
  const wkFmt = new Intl.DateTimeFormat("en-GB", { timeZone: TZ, weekday: "short" });
  const num = (n) => Number(n || 0).toLocaleString("en-GB");
  const clock = (d) => tFmt.format(d instanceof Date ? d : new Date(d));
  const dayKey = (d) => new Intl.DateTimeFormat("en-CA", { timeZone: TZ }).format(d);
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const phone = window.matchMedia("(max-width: 760px)");

  function ago(iso) {
    const d = new Date(iso);
    const mins = Math.round((Date.now() - d) / 60000);
    if (mins < 1) return "just now";
    if (mins < 60) return `${mins} min ago`;
    if (dayKey(d) === dayKey(new Date())) return `${Math.floor(mins / 60)} h ago`;
    const days = Math.round((new Date(dayKey(new Date())) - new Date(dayKey(d))) / 86400000);
    return days === 1 ? "yesterday" : days < 7 ? `${days} days ago` : dFmt.format(d);
  }
  function whenShort(iso) {
    const d = new Date(iso);
    if (dayKey(d) === dayKey(new Date())) return clock(d);
    const days = Math.round((new Date(dayKey(new Date())) - new Date(dayKey(d))) / 86400000);
    return days < 7 ? `${wkFmt.format(d)} ${clock(d)}` : `${dFmt.format(d)} ${clock(d)}`;
  }

  // ---------- DEFRA lists (the exact WasteDataFlow strings) ----------
  const SIZES = ["Single black bag", "Single item", "Car boot or less", "Small van load", "Transit van load", "Tipper lorry load", "Significant/multiple loads"];
  const WASTE = ["Animal carcasses", "Green", "Vehicle parts", "White goods", "Other electrical", "Tyres", "Asbestos", "Clinical", "Construction/demolition/excavation", "Black bags - commercial", "Black bags - household", "Chemical drums, oil or fuel", "Other household waste", "Other commercial waste", "Other (unidentified)"];
  const LAND = ["Highway", "Footpath/bridleway", "Back alleyway", "Railway", "Council land", "Agricultural", "Private/residential", "Commercial/industrial", "Watercourse/bank", "Other (unidentified)"];
  const FIELD_LABEL = { size: "Size", waste_type: "Waste type", land_type: "Land type", hazards: "Hazards", decision: "Decision" };

  // ---------- Icons ----------
  const I = {
    calendar: '<svg viewBox="0 0 24 24"><rect x="3.5" y="5" width="17" height="15" rx="2"/><path d="M3.5 10h17M8 3v4M16 3v4"/></svg>',
    sofa: '<svg viewBox="0 0 24 24"><path d="M4 11V8a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v3"/><path d="M2.5 12.5a1.5 1.5 0 0 1 3 0V14h13v-1.5a1.5 1.5 0 0 1 3 0V18h-19z"/><path d="M5 18v2M19 18v2"/></svg>',
    hazard: '<svg viewBox="0 0 24 24"><path d="M12 3.5 2.5 20h19z"/><path d="M12 10v4.5M12 17.2v.3"/></svg>',
    eye: '<svg viewBox="0 0 24 24"><path d="M2 12s3.5-6.5 10-6.5S22 12 22 12s-3.5 6.5-10 6.5S2 12 2 12z"/><circle cx="12" cy="12" r="3"/></svg>',
    truck: '<svg viewBox="0 0 24 24"><path d="M2.5 6h11v10h-11zM13.5 9.5h4l3 3.5V16h-7"/><circle cx="6.5" cy="17.5" r="1.8"/><circle cx="17" cy="17.5" r="1.8"/></svg>',
    camera: '<svg viewBox="0 0 24 24"><path d="M3 8h4l2-2.5h6L17 8h4v11H3z"/><circle cx="12" cy="13" r="3.5"/></svg>',
    chev: '<svg class="chev" viewBox="0 0 24 24"><path d="M6 9l6 6 6-6"/></svg>',
    back: '<svg viewBox="0 0 24 24"><path d="M15 5l-7 7 7 7"/></svg>',
    filter: '<svg viewBox="0 0 24 24"><path d="M4 6h16M7 12h10M10 18h4"/></svg>',
    people: '<svg viewBox="0 0 24 24"><circle cx="9" cy="8.5" r="3.2"/><path d="M3 19.5c.6-3.3 3-5.2 6-5.2s5.4 1.9 6 5.2"/><circle cx="16.8" cy="9.3" r="2.5"/><path d="M16.3 14.4c2.4.1 4.2 1.7 4.7 4.6"/></svg>',
    reopen: '<svg viewBox="0 0 24 24"><path d="M4.5 12a7.5 7.5 0 1 0 2.2-5.3"/><path d="M4.5 4.5v4h4"/></svg>',
    officer: '<svg viewBox="0 0 24 24"><circle cx="12" cy="8" r="3.5"/><path d="M5 20c.8-4 3.5-6 7-6s6.2 2 7 6"/></svg>',
    more: '<svg viewBox="0 0 24 24"><circle cx="5" cy="12" r="1.3"/><circle cx="12" cy="12" r="1.3"/><circle cx="19" cy="12" r="1.3"/></svg>',
    pin: '<svg viewBox="0 0 24 24"><path d="M12 21s-7-6.2-7-11.5A7 7 0 0 1 19 9.5C19 14.8 12 21 12 21z"/><circle cx="12" cy="9.5" r="2.5"/></svg>',
    ring: (n) => `<svg viewBox="0 0 12 12">${n >= 3 ? '<circle cx="6" cy="6" r="5"/>' : ""}${n >= 2 ? '<circle cx="6" cy="6" r="3"/>' : ""}<circle cx="6" cy="6" r="1" fill="currentColor"/></svg>`,
  };

  const HS = {
    new_site: { label: "New site", rings: 1, rule: "No reports within 100 m in 12 months" },
    emerging: { label: "Emerging", rings: 2, rule: "Second report within 100 m in 28 days" },
    repeat: { label: "Repeat", rings: 3, rule: "3+ reports within 100 m in 90 days" },
  };
  const hsTag = (state) => (HS[state] ? `<span class="hs ${state}" title="${esc(HS[state].rule)}">${I.ring(HS[state].rings)}${HS[state].label}</span>` : "");
  const decisionPill = (key) => {
    const [label, cls] = STATUS[key] || STATUS.review;
    return `<span class="pill ${cls}">${label}</span>`;
  };
  const DECISIONS = ["clear_now", "review", "hold_for_officer", "specialist", "not_a_fly_tip"];
  const DEC_KEYS = ["triaging", ...DECISIONS];
  // One line per decision. Used in the card tooltip and the map legend.
  const DEC_HELP = {
    clear_now: "No evidence or hazard seen. Can be cleared now.",
    review: "Low confidence or conflicting information, such as a collection day or bulky booking. An officer decides before a crew is sent.",
    hold_for_officer: "May contain evidence, such as addressed post. An officer inspects before clearance.",
    specialist: "Hazardous waste, such as asbestos. Requires a licensed contractor.",
    not_a_fly_tip: "Likely not fly-tipping, for example waste awaiting collection or a booked bulky item.",
  };
  const MAP_KEYS = ["triaging", "clear_now", "scheduled", "hold_for_officer", "specialist", "review", "not_fly_tip", "forwarded", "cleared"];
  const STATUS_HEX = { triaging: "--st-triaging", clear_now: "--st-clear", hold_for_officer: "--st-hold", specialist: "--st-specialist", review: "--st-hold", not_fly_tip: "--st-muted", cleared: "--st-cleared" };
  const cssVar = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
  const mapKey = (inc) => { const k = stKey(inc); if (k === "closed") return "cleared"; return k === "held" ? "hold_for_officer" : k === "not_a_fly_tip" ? "not_fly_tip" : k; };
  const CLOSED = ["cleared", "not_fly_tip", "closed", "forwarded"];
  const isOpen = (inc) => !CLOSED.includes(inc.status);
  // Fictional branding: the backend may still say Liverpool; show Mersey Vale everywhere.
  const brand = (s) => String(s ?? "");
  const LOCAL_STATUS = { forwarded: STATUS.forwarded || ["Passed on", "further_inspection"], closed: ["Closed", "cleared"] };
  const stKey = (inc) => (inc && LOCAL_STATUS[inc.status] ? inc.status : CH.statusKey(inc));
  const stLabel = (k) => (LOCAL_STATUS[k] || STATUS[k] || STATUS.review);
  const pill = (inc) => { const [label, cls] = stLabel(stKey(inc)); return `<span class="pill ${cls}">${label}</span>`; };
  const decKey = (inc) => (inc.status === "triaging" || !inc.triage ? "triaging" : inc.triage.decision || "review");
  const caseRef = (inc) => inc.case_ref || `MVCC-FT-${new Date().getFullYear()}-${String(inc.id).padStart(4, "0")}`;
  const overriddenList = (t) => (t && Array.isArray(t.overridden) ? t.overridden : []);

  // Queue buckets: Needs action (incl. Needs review) · Booked · Closed (incl. Passed on)
  function bucket(inc) {
    if (CLOSED.includes(inc.status)) return "done";
    if (inc.status === "scheduled" || inc.status === "held") return "booked";
    return "action";
  }

  // Priority: use the API's, or derive a rough one so the queue still sorts sensibly on an older backend.
  const PRI_RANK = { urgent: 3, high: 2, normal: 1, low: 0 };
  function prio(inc) {
    if (inc.priority && inc.priority.level) return inc.priority;
    const t = inc.triage || {};
    const reasons = [];
    let score = 20;
    if (t.decision === "specialist" || (t.hazards && !/^none/i.test(t.hazards))) { score += 45; reasons.push("Possible hazard"); }
    if ((inc.report_count || 1) >= 3) { score += 20; reasons.push(`${inc.report_count} reports`); }
    const days = Math.floor((Date.now() - new Date(inc.created_at)) / 86400000);
    if (days >= 3) { score += 10; reasons.push(`Open ${days} days`); }
    return { score, level: score >= 80 ? "urgent" : score >= 55 ? "high" : "normal", reasons };
  }
  function priBadge(inc, withReasons = false) {
    if (bucket(inc) === "done") return "";
    const p = prio(inc);
    if (!["urgent", "high"].includes(p.level)) return "";
    const label = p.level === "urgent" ? "Urgent" : "High";
    const why = (p.reasons || []).join(" · ");
    return `<span class="pri ${p.level}" title="${esc(why ? `${label} priority: ${why}` : `${label} priority`)}">${label}${withReasons && why ? `<span class="pri-why">${esc(why)}</span>` : ""}</span>`;
  }
  const growBadge = (inc) => (inc.growing && isOpen(inc) ? `<span class="grow" title="Further reports received at this location">Growing</span>` : "");
  const reportsTag = (inc) => (inc.report_count > 1 ? `<span class="rc" title="${inc.report_count} reports from residents">${I.people}${inc.report_count} reports</span>` : "");
  const stillTag = (inc) => (inc.still_there_count > 0 && isOpen(inc) ? `<span class="still" title="Residents have confirmed the waste is still present">Still present ×${inc.still_there_count}</span>` : "");
  const authorityTag = (inc) => (inc.authority && !/liverpool|mersey vale/i.test(inc.authority) ? `<span class="auth" title="Outside the Mersey Vale boundary">${esc(inc.authority)}</span>` : "");

  // ---------- State ----------
  const S = {
    incidents: [], known: new Set(), fresh: new Map(), selected: null, tab: "queue",
    qtab: "action", sort: "priority", f: { dec: new Set(), ward: "", pri: "", growing: false }, fOpen: !phone.matches,
    history: null, hotspots: null, pending: new Set(), listSig: "", cardSig: "", cardOpen: false,
    lastCard: { id: null, triaging: false }, justCleared: null, mapFilter: new Set(MAP_KEYS), layers: { history: true, rings: true },
    loaded: false, offline: false, defraDirty: null, car: new Map(),
  };

  // ---------- Toasts and modal ----------
  function toast(html, { live = false, action = null, ms = 4200 } = {}) {
    const t = document.createElement("div");
    t.className = "toast" + (live ? " is-live" : "");
    t.innerHTML = `<span>${html}</span>`;
    if (action) {
      const b = document.createElement("button");
      b.className = "btn";
      b.textContent = action.label;
      b.onclick = () => { action.run(); close(); };
      t.appendChild(b);
    }
    $("#cc-toasts").appendChild(t);
    function close() { t.classList.add("out"); setTimeout(() => t.remove(), 260); }
    setTimeout(close, ms);
  }
  function openModal(html, onMount) {
    const m = $("#cc-modal");
    m.innerHTML = html;
    m.hidden = false;
    const closeIt = () => { m.hidden = true; m.innerHTML = ""; document.removeEventListener("keydown", onKey); };
    const onKey = (e) => { if (e.key === "Escape") closeIt(); };
    document.addEventListener("keydown", onKey);
    m.onclick = (e) => { if (e.target === m || e.target.closest("[data-close]")) closeIt(); };
    if (onMount) onMount(m, closeIt);
    const f = m.querySelector("button, [tabindex], input");
    if (f) f.focus();
    return closeIt;
  }

  // ---------- Data ----------
  function mergeIncidents(list, initial = false) {
    const local = new Map(S.incidents.map((i) => [i.id, i]));
    const next = list.map((i) => (S.pending.has(i.id) && local.has(i.id) ? local.get(i.id) : i));
    for (const inc of next) {
      if (!initial && S.loaded && !S.known.has(inc.id)) {
        S.fresh.set(inc.id, Date.now());
        toast(`<b>New report</b> · ${esc(inc.street || "Unknown street")}, ${esc(inc.ward || "")}`, {
          live: true, action: { label: "View", run: () => openIncident(inc.id) },
        });
      } else if (!initial && local.has(inc.id) && (inc.report_count || 0) > (local.get(inc.id).report_count || 0)) {
        S.fresh.set(inc.id, Date.now());
        toast(`<b>Further report</b> · ${esc(inc.street || "")}, ${inc.report_count} in total`, {
          live: true, action: { label: "View", run: () => openIncident(inc.id) },
        });
      }
      S.known.add(inc.id);
    }
    S.incidents = next;
    if (S.selected == null || !S.incidents.some((i) => i.id === S.selected)) {
      const first = visibleIncidents()[0];
      S.selected = first ? first.id : null;
    }
    S.loaded = true;
    renderQueue();
    if (maps.main) renderMapIncidents();
  }

  let polling = false;
  async function poll() {
    if (polling || MOCK) return;
    polling = true;
    try {
      const list = await CH.get("/api/incidents?view=council");
      S.offline = false;
      mergeIncidents(list);
    } catch (e) {
      S.offline = true;
    } finally {
      polling = false;
    }
  }

  // Mock mode: the "Checking…" report arrives a few seconds after load, then gets classified.
  function mockSimulate(all) {
    const later = all.filter((i) => i.status === "triaging");
    mergeIncidents(all.filter((i) => i.status !== "triaging"), true);
    if (!later.length) return;
    setTimeout(() => {
      later.forEach((i) => { i.created_at = i.updated_at = new Date().toISOString(); (i.timeline || []).forEach((t) => (t.at = i.created_at)); });
      mergeIncidents([...later, ...S.incidents]);
      setTimeout(() => {
        later.forEach((i) => {
          if (i.status !== "triaging" || !i._mock_triage) return;
          i.triage = i._mock_triage;
          i.status = "triaged";
          i.updated_at = new Date().toISOString();
          i.timeline.push({ at: i.updated_at, kind: "triaged", text: `Classified: ${i.triage.size}, ${i.triage.waste_type}` });
        });
        mergeIncidents(S.incidents.slice());
      }, 9000);
    }, 3500);
  }

  // ---------- Queue ----------
  function filtered(ignoreDec = false) {
    const f = S.f;
    return S.incidents.filter((inc) => {
      if (bucket(inc) !== S.qtab) return false;
      if (!ignoreDec && f.dec.size && !f.dec.has(decKey(inc))) return false;
      if (f.ward && inc.ward !== f.ward) return false;
      if (f.pri) {
        const r = PRI_RANK[prio(inc).level] || 0;
        if (f.pri === "urgent" ? r < 3 : r < 2) return false;
      }
      if (f.growing && !inc.growing) return false;
      return true;
    });
  }
  function sortList(list) {
    const newest = (a, b) => new Date(b.created_at) - new Date(a.created_at);
    if (S.sort === "newest" || S.qtab === "done") return list.slice().sort(newest);
    return list.slice().sort((a, b) => {
      const ta = a.status === "triaging" ? 1 : 0, tb = b.status === "triaging" ? 1 : 0;
      if (ta !== tb) return tb - ta; // just-arrived reports stay on top while they're checked
      return (prio(b).score || 0) - (prio(a).score || 0) || newest(a, b);
    });
  }
  const visibleIncidents = () => sortList(filtered());
  const activeFilterCount = () => S.f.dec.size + (S.f.ward ? 1 : 0) + (S.f.pri ? 1 : 0) + (S.f.growing ? 1 : 0);

  function incSig(i) {
    const p = i.priority || {};
    return [i.id, i.status, i.updated_at, i.report_count, i.triage && i.triage.decision, i.cleared_photo_url, (i.timeline || []).length, p.level, i.growing, i.still_there_count, overriddenList(i.triage).join()].join("|");
  }

  function renderQueue(force = false) {
    const list = visibleIncidents();
    const counts = { action: 0, booked: 0, done: 0 };
    S.incidents.forEach((i) => counts[bucket(i)]++);
    $$("#q-tabs [data-qt]").forEach((b) => {
      b.setAttribute("aria-selected", String(b.dataset.qt === S.qtab));
      b.querySelector("b").textContent = counts[b.dataset.qt];
    });
    $("#nav-count-queue").textContent = counts.action || "";
    const sig = [S.qtab, S.sort, [...S.f.dec].join(), S.f.ward, S.f.pri, S.f.growing, S.fOpen, S.selected, list.map(incSig).join(";"), Math.floor(Date.now() / 60000)].join("#");
    if (force || sig !== S.listSig) {
      S.listSig = sig;
      renderFilters();
      const ol = $("#q-list");
      const scroll = ol.scrollTop;
      const n = activeFilterCount();
      const empty = n
        ? `<li class="q-empty">No incidents match these filters. <button class="linkbtn" data-clear-filters>Clear filters</button></li>`
        : `<li class="q-empty">${{ action: "No incidents need action.", booked: "No incidents booked.", done: "No closed incidents." }[S.qtab]}</li>`;
      ol.innerHTML = list.length ? list.map(queueItem).join("") : empty;
      ol.scrollTop = scroll;
      $("#q-shown").textContent = n ? `${list.length} shown` : "";
    }
    renderCard();
  }

  function renderFilters() {
    const base = filtered(true);
    const counts = {};
    base.forEach((i) => { const k = decKey(i); counts[k] = (counts[k] || 0) + 1; });
    const keys = DEC_KEYS.filter((k) => counts[k] || S.f.dec.has(k));
    const wards = [...new Set(S.incidents.map((i) => i.ward).filter(Boolean))].sort();
    const n = activeFilterCount();
    $("#q-filter-btn").setAttribute("aria-expanded", String(S.fOpen));
    $("#q-filter-n").textContent = n || "";
    $("#q-clear").hidden = !n;
    $$("#q-sort [data-sort]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.sort === S.sort)));
    const panel = $("#q-filters");
    panel.hidden = !S.fOpen;
    if (!S.fOpen) return;
    panel.innerHTML = `
      <div class="chips" role="group" aria-label="Filter by decision">${keys.map((k) => {
        const [label, cls] = STATUS[k] || STATUS.review;
        return `<button type="button" class="chip" data-dec="${k}" aria-pressed="${S.f.dec.has(k)}"><i class="dot-${cls}"></i>${label} <b>${counts[k] || 0}</b></button>`;
      }).join("") || `<span class="muted">No incidents in this list.</span>`}</div>
      <div class="f-row">
        <label class="f-sel"><span class="sr">Ward</span><select id="f-ward"><option value="">All wards</option>${wards.map((w) => `<option ${w === S.f.ward ? "selected" : ""}>${esc(w)}</option>`).join("")}</select></label>
        <label class="f-sel"><span class="sr">Priority</span><select id="f-pri">
          <option value="">Any priority</option><option value="high" ${S.f.pri === "high" ? "selected" : ""}>High and urgent</option><option value="urgent" ${S.f.pri === "urgent" ? "selected" : ""}>Urgent only</option></select></label>
        <label class="toggle"><input type="checkbox" id="f-grow" ${S.f.growing ? "checked" : ""}> Growing only</label>
      </div>`;
  }

  function queueItem(inc) {
    const key = stKey(inc);
    const fresh = S.fresh.get(inc.id);
    const isNew = fresh && Date.now() - fresh < 4000;
    const cls = ["q-item", key === "triaging" ? "is-triaging" : "", isNew ? "is-new" : ""].join(" ");
    return `<li class="${cls}" role="option" tabindex="0" data-id="${inc.id}" aria-selected="${inc.id === S.selected}">
      <img class="q-thumb" src="${esc(inc.photo_url)}" alt="" loading="lazy">
      <div class="q-main">
        <div class="q-top"><span class="q-street">${esc(inc.street || "Location pending")}</span><span class="q-time" title="${esc(inc.created_at)}">${esc(ago(inc.created_at))}</span></div>
        <div class="q-ward"><span>${esc(inc.ward || "")}</span><span class="q-ref">${esc(caseRef(inc))}</span></div>
        <div class="q-tags">${pill(inc)}${priBadge(inc)}${growBadge(inc)}${reportsTag(inc)}${stillTag(inc)}${authorityTag(inc)}</div>
      </div>
    </li>`;
  }

  function select(id, { open = true } = {}) {
    S.selected = id;
    $$("#q-list .q-item").forEach((li) => li.setAttribute("aria-selected", String(+li.dataset.id === id)));
    S.cardSig = "";
    S.defraDirty = null;
    if (open && phone.matches) setCardOpen(true);
    renderCard();
    const li = $(`#q-list .q-item[data-id="${id}"]`);
    if (li) li.scrollIntoView({ block: "nearest" });
    if (phone.matches) { const b = $("#q-card .tc-body"); if (b) b.scrollTop = 0; }
  }
  function setCardOpen(on) {
    S.cardOpen = on;
    document.body.classList.toggle("card-open", on);
    if (on) setTimeout(refreshCardMap, 260);
  }

  // One small Leaflet map for the triage card, reused across incidents (its element moves between renders).
  let cmap = null;
  function mountCardMap(pane, inc) {
    const slot = pane.querySelector("[data-cmap]");
    if (!slot || !window.L) return;
    const ll = [inc.lat, inc.lon];
    if (!cmap) {
      const el = document.createElement("div");
      el.className = "cmap";
      slot.appendChild(el);
      const m = L.map(el, { zoomControl: true, attributionControl: true, scrollWheelZoom: false, keyboard: false }).setView(ll, 16);
      m.attributionControl.setPrefix(false);
      L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom: 19, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
      }).addTo(m);
      cmap = { m, el, id: null, ll, marker: L.marker(ll, { icon: incIcon(inc), keyboard: false, interactive: false }).addTo(m) };
    } else {
      slot.appendChild(cmap.el);
    }
    cmap.ll = ll;
    cmap.marker.setLatLng(ll).setIcon(incIcon(inc));
    phone.matches ? cmap.m.dragging.disable() : cmap.m.dragging.enable();
    const moved = cmap.id !== inc.id;
    cmap.id = inc.id;
    requestAnimationFrame(() => { if (!cmap) return; cmap.m.invalidateSize(); if (moved) cmap.m.setView(ll, 16, { animate: false }); });
  }
  function refreshCardMap() {
    if (!cmap || !cmap.el.isConnected) return;
    cmap.m.invalidateSize();
    cmap.m.setView(cmap.ll, 16, { animate: false });
  }
  function openIncident(id) {
    switchTab("queue");
    const inc = S.incidents.find((i) => i.id === id);
    if (inc && bucket(inc) !== S.qtab) { S.qtab = bucket(inc); renderQueue(true); }
    select(id);
  }

  const current = () => S.incidents.find((i) => i.id === S.selected);

  function renderCard() {
    const pane = $("#q-card");
    const inc = current();
    const sig = inc ? incSig(inc) + (S.justCleared === inc.id ? "c" : "") : "none";
    if (sig === S.cardSig) return;
    const sameId = S.cardSig.split("|")[0] === String(inc && inc.id);
    // Don't yank a menu or a half-edited form from under the user
    if (sameId && (pane.querySelector("details[open]") || S.defraDirty === inc.id || (pane.contains(document.activeElement) && document.activeElement.matches("select, input")))) return;
    S.cardSig = sig;
    if (!inc) {
      pane.innerHTML = `<div class="tc-empty"><h3>No incident selected</h3><p>Select an incident from the queue.</p></div>`;
      return;
    }
    const key = stKey(inc);
    const reveal = S.lastCard.id === inc.id && S.lastCard.triaging && key !== "triaging";
    S.lastCard = { id: inc.id, triaging: key === "triaging" };
    const body = key === "triaging" ? triagingBody(inc) : triageBody(inc, reveal);
    const scroll = sameId ? (pane.querySelector(".tc-body") || {}).scrollTop || 0 : 0;
    pane.innerHTML = `<article class="tc" aria-label="Triage card for ${esc(caseRef(inc))}">
      ${cardHead(inc)}
      ${actionsBar(inc, key)}
      <div class="tc-body">${body}</div>
    </article>`;
    pane.querySelector(".tc-body").scrollTop = scroll;
    bindCard(pane, inc);
    mountCardMap(pane, inc);
    if (S.justCleared === inc.id) setTimeout(() => { S.justCleared = null; }, 1200);
  }

  function cardHead(inc) {
    const n = reportList(inc).length;
    const rc = n > 1 ? `<button type="button" class="rc rc-btn" data-goto-reports title="View photos from each report">${I.people}${n} reports</button>` : reportsTag(inc);
    return `<header class="tc-head">
      <button class="btn btn-ghost tc-back" data-back aria-label="Back to the queue">${I.back}<span>Queue</span></button>
      <div class="tc-title">
        <h2>${esc(inc.street || "Location pending")}</h2>
        <div class="tc-sub"><span class="mono">${esc(caseRef(inc))}</span><span class="dot">·</span><span>${esc(inc.ward || "")}</span><span class="dot">·</span><span>Reported ${esc(whenShort(inc.created_at))}</span>${rc ? `<span class="dot">·</span>${rc}` : ""}${stillTag(inc)}</div>
      </div>
      <div class="tc-head-tags">${authorityTag(inc)}${growBadge(inc)}</div>
    </header>`;
  }

  // All merged reports with a photo; falls back to the incident's own photo on an older backend.
  function reportList(inc) {
    const r = Array.isArray(inc.reports) ? inc.reports.filter((x) => x && x.photo_url) : [];
    return r.length ? r : [{ photo_url: inc.photo_url, created_at: inc.created_at }];
  }

  function photoBlock(inc) {
    if (inc.status === "cleared" && inc.cleared_photo_url) {
      return `<div class="tc-photos-2">
        <figure class="tc-photo" data-zoom="${esc(inc.photo_url)}"><img src="${esc(inc.photo_url)}" alt="Before: ${esc(inc.public_summary)}"><figcaption>Before · ${esc(whenShort(inc.created_at))}</figcaption></figure>
        <figure class="tc-photo is-after" data-zoom="${esc(inc.cleared_photo_url)}"><img src="${esc(inc.cleared_photo_url)}" alt="After: site cleared"><figcaption>After · ${esc(whenShort(inc.cleared_at || inc.updated_at))}</figcaption>
          <span class="stamp ${S.justCleared === inc.id && !reduceMotion ? "animate" : ""}">CLEARED</span></figure>
      </div>`;
    }
    const reps = reportList(inc);
    const stamp = inc.status === "cleared" ? `<span class="stamp">CLEARED</span>` : "";
    if (reps.length < 2) {
      return `<figure class="tc-photo" data-zoom="${esc(inc.photo_url)}"><img src="${esc(inc.photo_url)}" alt="${esc(inc.public_summary || "Reported photo")}"><figcaption>Resident's photo · ${esc(whenShort(inc.created_at))}</figcaption>${stamp}</figure>`;
    }
    const i = Math.min(S.car.get(inc.id) || 0, reps.length - 1);
    const r = reps[i];
    return `<div class="car" data-car tabindex="-1" aria-roledescription="carousel" aria-label="Photos from ${reps.length} merged reports">
      <figure class="tc-photo" data-zoom="${esc(r.photo_url)}"><img src="${esc(r.photo_url)}" alt="Photo from report ${i + 1} of ${reps.length}" draggable="false">${stamp}
        <button type="button" class="car-btn prev" data-car-step="-1" aria-label="Previous report photo">‹</button>
        <button type="button" class="car-btn next" data-car-step="1" aria-label="Next report photo">›</button></figure>
      <div class="car-cap" aria-live="polite"><span>Report ${i + 1} of ${reps.length} · ${esc(whenShort(r.created_at || inc.created_at))}</span><span class="car-dots">${reps.map((_, k) => `<i class="${k === i ? "on" : ""}"></i>`).join("")}</span></div>
    </div>`;
  }

  function triagingBody(inc) {
    return `<div class="tc-grid">
      <div class="tc-col"><figure class="tc-photo"><img src="${esc(inc.photo_url)}" alt="${esc(inc.public_summary || "Reported photo")}"><span class="scan"></span><figcaption>Resident's photo · ${esc(whenShort(inc.created_at))}</figcaption></figure></div>
      <div class="tc-col">
        <div class="box"><div class="checking-note"><span class="pill triaging">Processing</span><span class="tick" data-since="${esc(inc.created_at)}"></span></div>
          <p class="muted" style="margin:10px 0 0">Classifying the photo. The image is processed locally and not shared.</p>
          <div class="skel" style="width:92%"></div><div class="skel" style="width:78%"></div><div class="skel" style="width:60%"></div></div>
      </div>
    </div>`;
  }

  const FLAG = {
    collection_day: { icon: I.calendar, k: "Collection day" },
    bulky_booking: { icon: I.sofa, k: "Bulky collection booked" },
    hazard_rule: { icon: I.hazard, k: "Hazard rule" },
  };

  // What the recommendation means as an action. act = the button it maps to.
  const REC = {
    clear_now: { label: "Book crew", act: "schedule" },
    specialist: { label: "Book a specialist contractor", act: "schedule" },
    hold_for_officer: { label: "Hold for an officer to inspect", act: "hold" },
    review: { label: "Officer review", act: null },
    not_a_fly_tip: { label: "Close: not fly-tipping", act: "not_fly_tip" },
  };

  function decisionLegend() {
    return `<details class="tip"><summary aria-label="Decision key">?</summary><div class="tip-pop" role="note">
      <div class="tip-h">Decisions</div>
      ${DECISIONS.map((d) => `<div class="tip-row">${decisionPill(d)}<span>${esc(DEC_HELP[d])}</span></div>`).join("")}
    </div></details>`;
  }

  // The single alert line: the backend's headline, else the top context flag. Shown once, nowhere else.
  function alertLine(inc, reveal) {
    const t = inc.triage || {};
    const f = (t.context_flags || [])[0];
    const text = t.headline_alert || (f && f.text);
    if (!text) return "";
    const F = (f && FLAG[f.kind]) || (/hazard|asbestos|chemical|clinical|needle/i.test(text) ? FLAG.hazard_rule : { icon: I.eye });
    return `<div class="alert ${f ? esc(f.kind) : ""} ${reveal ? "is-reveal" : ""}" role="note"><span class="alert-ico">${F.icon}</span><span class="alert-t">${esc(brand(text))}</span></div>`;
  }

  // The reason after the recommendation. The backend's decision_why ends by restating the action
  // ("... Book a crew."), which the label already says, so only its first sentence is kept.
  const WHY_FIX = [
    [/^No evidence expected$/i, "No evidence or hazard seen"],
    [/^AI reading:\s*possibly not fly-tipping$/i, "May not be fly-tipping"],
    [/^AI not confident$/i, "Low AI confidence"],
    [/^Model offline$/i, "Automatic check unavailable"],
    [/^Model reply unreadable$/i, "Automatic check failed"],
  ];
  const firstSentence = (s) => String(s || "").trim().split(/(?<=\.)\s+/)[0].replace(/\.$/, "").trim();
  function recReason(t, fwd, ov) {
    let why = brand(t.decision_why || "").replace(/^Rule:\s*/i, "").replace(/^Officer corrections applied\.\s*/i, "");
    if (ov) why = why.replace(/^Decision changed by (an )?officer\.?\s*/i, "").replace(/^Note:\s*/i, "");
    // Referrals: say why it is someone else's job (e.g. "Within 20 m of railway land"), not "Forward to X" again.
    why = fwd ? firstSentence(brand((t.whose_job || {}).note)) : firstSentence(why);
    for (const [re, to] of WHY_FIX) why = why.replace(re, to);
    // Skip it when the alert line above already says the same thing (bin day, bulky booking).
    const alertText = brand(t.headline_alert || ((t.context_flags || [])[0] || {}).text || "");
    if (why && alertText.toLowerCase().startsWith(why.toLowerCase())) why = "";
    return why ? why[0].toUpperCase() + why.slice(1) : "";
  }

  // Compact, neutral "AI recommends" line. The human still chooses from the buttons above.
  function recLine(inc) {
    const t = inc.triage || {};
    const d = t.decision || "review";
    const rec = REC[d] || REC.review;
    const ov = overriddenList(t).includes("decision") || (t.overridden && !Array.isArray(t.overridden));
    const orig = t.ai_original && t.ai_original.decision ? t.ai_original.decision : t.model_decision;
    const fwd = t.forward_to && d !== "specialist";
    const label = fwd ? `Refer to ${t.forward_to}` : rec.label;
    const whyS = recReason(t, fwd, ov);
    return `<div class="rec" role="note" aria-label="Recommendation"><span class="rec-k">${ov ? "Officer decision:" : "AI recommendation:"}</span> <b>${esc(label)}</b>.${whyS ? ` ${esc(whyS)}.` : ""}${ov && orig ? ` <span class="rec-note">(AI recommendation: ${esc((STATUS[orig] || [orig])[0])})</span>` : ""} ${decisionLegend()}</div>`;
  }

  function defraForm(inc) {
    const t = inc.triage || {};
    const ov = overriddenList(t);
    const orig = t.ai_original || {};
    const conf = Number(t.confidence || 0);
    const hz = t.hazards && !/^none/i.test(t.hazards);
    const opts = (list, v) => (list.includes(v) || !v ? list : [v, ...list]).map((o) => `<option ${o === v ? "selected" : ""}>${esc(o)}</option>`).join("");
    const note = (f) => (ov.includes(f) && orig[f] != null ? `<div class="df-ai">AI classification: ${esc(orig[f] || "none")}</div>` : "");
    const row = (f, label, control) => `<div class="df-row ${ov.includes(f) ? "is-ov" : ""}"><label for="df-${f}">${label}</label><div>${control}${note(f)}</div></div>`;
    const confRow = `<div class="df-conf"><label>AI confidence</label><div class="bar ${conf < 70 ? "low" : ""}" role="meter" aria-label="AI confidence" aria-valuenow="${conf}" aria-valuemin="0" aria-valuemax="100"><i style="width:${conf}%"></i></div><b>${conf}%</b></div>`;
    if (!isOpen(inc)) {
      const ro = (f, label, v) => `<div class="df-row ${ov.includes(f) ? "is-ov" : ""}"><span class="df-l">${label}</span><div><span class="df-val ${f === "hazards" && hz ? "is-hazard" : ""}">${esc(v ? v[0].toUpperCase() + v.slice(1) : "None")}</span>${note(f)}</div></div>`;
      return `<section class="defra is-ro" aria-label="DEFRA classification">
        <div class="defra-h">DEFRA classification<span class="r">Fly-tip: ${esc(t.fly_tip || "?")}</span></div>
        <div class="defra-rows">${ro("size", "Size", t.size)}${ro("waste_type", "Waste type", t.waste_type)}${ro("land_type", "Land type", t.land_type)}${ro("hazards", "Hazards", t.hazards)}${confRow}</div>
      </section>`;
    }
    return `<form class="defra" data-defra aria-label="DEFRA classification">
      <div class="defra-h">DEFRA classification<span class="r">Fly-tip: ${esc(t.fly_tip || "?")}</span></div>
      <div class="defra-rows">
        ${row("size", "Size", `<select id="df-size" name="size">${opts(SIZES, t.size)}</select>`)}
        ${row("waste_type", "Waste type", `<select id="df-waste_type" name="waste_type">${opts(WASTE, t.waste_type)}</select>`)}
        ${row("land_type", "Land type", `<select id="df-land_type" name="land_type">${opts(LAND, t.land_type)}</select>`)}
        ${row("hazards", "Hazards", `<input id="df-hazards" name="hazards" type="text" value="${esc(t.hazards || "")}" placeholder="None visible" class="${hz ? "is-hazard" : ""}">`)}
        ${confRow}
        <div class="df-save"><span class="df-msg" aria-live="polite">${ov.filter((f) => f !== "decision").length ? "Corrected by an officer" : ""}</span><button type="button" class="btn btn-sm" data-df-reset hidden>Cancel</button><button type="submit" class="btn btn-sm btn-primary" disabled>Save</button></div>
      </div>
    </form>`;
  }

  // Timeline wording is stored by the backend; tidy it here so older rows read the same as new ones.
  function tlText(e) {
    let s = brand(e.text || "").trim()
      .replace(/ The council will forward the report\.$/, "")
      .replace(/^Case passed for prosecution/, "Referred for prosecution");
    if (e.kind === "triaged") s = s.replace(/^Checked\.\s*/, "Checked by AI. ");
    return s && !/[.!?)]$/.test(s) ? s + "." : s;
  }

  function triageBody(inc, reveal) {
    const t = inc.triage || {};
    const j = t.whose_job || {};
    const h = t.hotspot || {};
    const tl = (inc.timeline || []).slice().reverse();
    const body = brand(j.body || inc.authority || "Mersey Vale City Council");
    return `
      ${alertLine(inc, reveal)}
      <div class="tc-grid">
        <div class="tc-col">${photoBlock(inc)}</div>
        <div class="tc-col">${defraForm(inc)}</div>
      </div>
      <section class="tc-where" aria-label="Location">
        ${inc.lat != null && inc.lon != null ? `<div class="cmap-slot" data-cmap aria-label="Map of ${esc(inc.street || "the incident")}"></div>` : ""}
        <div class="job"><span class="job-k">Responsible body</span><b class="job-body">${esc(body)}</b>${j.how_we_know ? `<span class="job-how" title="${esc(brand(j.how_we_know))}">${esc(brand(j.how_we_know))}</span>` : ""}</div>
      </section>
      <section class="box hs-box">
        <div class="box-h">Hotspot<a class="r link" href="#reduce" data-goto="reduce">View in Reduce</a></div>
        <div class="hs-row"><div class="hs-state">${hsTag(h.state) || '<span class="muted">No hotspot data</span>'}<span class="hs-rule">${esc(h.state === "new_site" && h.nearby_12m > 0 ? "No other reports within 100 m in 28 days" : (HS[h.state] || {}).rule || "")}</span></div>
        <div class="hs-counts"><div><b>${num(h.nearby_28d)}</b><span>28 days</span></div><div><b>${num(h.nearby_90d)}</b><span>90 days</span></div><div><b>${num(h.nearby_12m)}</b><span>12 months</span></div></div></div>
      </section>
      <section class="box">
        <div class="box-h">Timeline</div>
        <ol class="tl">${tl.map((e) => `<li class="k-${esc(e.kind)}"><time>${esc(whenShort(e.at))}</time><span class="tl-dot"></span><span class="tl-t">${esc(tlText(e))}${e.kind === "enforcement" ? `<span class="tl-lock">Not public</span>` : ""}</span></li>`).join("")}</ol>
      </section>`;
  }

  function actionsBar(inc, key) {
    const t = inc.triage || {};
    const d = t.decision;
    const busy = key === "triaging";
    const closed = !isOpen(inc);
    const scheduled = inc.status === "scheduled";
    const held = inc.status === "held";
    // The one highlighted button: the AI's recommendation, or the obvious next step once booked. Neutral colours only.
    let primary = busy || closed ? null : (REC[d] || {}).act || null;
    if (!busy && !closed && t.forward_to && d !== "specialist") primary = "forward";
    if (scheduled) primary = "clear";
    if (held && primary === "hold") primary = null;
    const cls = (act) => (act === primary ? "btn btn-rec" : "btn");
    if (closed && !busy) {
      return `<div class="tc-top"><div class="tc-actions is-closed" role="group" aria-label="Actions">
        <button class="btn btn-rec" data-act="reopen">${I.reopen}Reopen</button>
        <span class="tc-closed">${pill(inc)}<span>Reopen to make changes.</span></span>
      </div></div>`;
    }
    const book = scheduled
      ? `<button class="btn btn-done" disabled>${I.truck}${d === "specialist" ? "Contractor booked" : "Crew booked"} ✓</button>`
      : `<button class="${cls("schedule")}" data-act="schedule" ${busy || closed ? "disabled" : ""}>${I.truck}${d === "specialist" ? "Book contractor" : "Book crew"}</button>`;
    const hold = held
      ? `<button class="btn btn-done" disabled>${I.officer}Held for officer ✓</button>`
      : `<button class="${cls("hold")}" data-act="hold" ${busy || closed ? "disabled" : ""}>${I.officer}Hold for officer</button>`;
    const fwd = t.forward_to
      ? (inc.status === "forwarded"
        ? `<button class="btn btn-done" disabled>Referred to ${esc(t.forward_to)}</button>`
        : `<button class="${cls("forward")}" data-act="forward" ${busy || closed ? "disabled" : ""}>Refer to ${esc(t.forward_to)}</button>`)
      : "";
    const overrideItems = DECISIONS.filter((x) => x !== d).map((x) => `<button type="button" role="menuitem" data-override="${x}">${decisionPill(x)}</button>`).join("");
    return `<div class="tc-top">
      <div class="tc-actions" role="group" aria-label="Actions">
        ${book}${hold}
        <button class="${cls("clear")}" data-act="clear" ${busy || inc.status === "cleared" ? "disabled" : ""}>${I.camera}Mark cleared</button>
        <button class="${cls("not_fly_tip")}" data-act="not_fly_tip" ${busy || closed ? "disabled" : ""}>Not fly-tipping</button>
        ${fwd}
        <details class="menu"><summary class="btn" aria-label="More actions" ${busy ? 'aria-disabled="true"' : ""}>${I.more}<span class="more-l">More</span></summary>
          <div class="menu-pop" role="menu">
            <div class="menu-h">Change decision</div>${overrideItems}
            <div class="menu-h">Enforcement</div>
            <button type="button" role="menuitem" data-act="inspect">Log officer inspection<small>Recorded as an investigation in the DEFRA return</small></button>
            <button type="button" role="menuitem" data-act="warning_letter">Warning letter<small>Duty of care or EPA s.33</small></button>
            <button type="button" role="menuitem" data-act="fpn">Fixed penalty notice<small>EPA s.33ZA, up to £1,000</small></button>
            <button type="button" role="menuitem" data-act="prosecution">Prosecution<small>Refer to Legal Services</small></button>
          </div></details>
      </div>
      ${busy ? "" : recLine(inc)}
    </div>`;
  }

  function bindCard(pane, inc) {
    pane.querySelectorAll("[data-act]").forEach((b) => b.addEventListener("click", () => {
      const act = b.dataset.act;
      b.closest("details") && b.closest("details").removeAttribute("open");
      if (act === "clear") return clearModal(inc);
      doAction(inc.id, act);
    }));
    pane.querySelectorAll("[data-override]").forEach((b) => b.addEventListener("click", () => {
      b.closest("details").removeAttribute("open");
      doAction(inc.id, "override", { decision: b.dataset.override });
    }));
    pane.querySelectorAll("[data-zoom]").forEach((f) => !f.closest("[data-car]") && f.addEventListener("click", () => {
      openModal(`<img class="lightbox" src="${esc(f.dataset.zoom)}" alt="Photo, enlarged" data-close tabindex="0">`);
    }));
    pane.querySelectorAll("[data-goto]").forEach((a) => a.addEventListener("click", (e) => { e.preventDefault(); switchTab(a.dataset.goto); }));
    // Merged-report carousel: arrows, keyboard, swipe. Re-renders only the photo block.
    const car = pane.querySelector("[data-car]");
    if (car) {
      const n = reportList(inc).length;
      const step = (dir) => {
        S.car.set(inc.id, ((S.car.get(inc.id) || 0) + dir + n) % n);
        const tmp = document.createElement("div");
        tmp.innerHTML = photoBlock(inc);
        const fresh = tmp.firstElementChild;
        car.replaceWith(fresh);
        bindCard.car(pane, inc);
      };
      bindCard.car = (pn, ic) => {
        const c = pn.querySelector("[data-car]");
        if (!c) return;
        c.querySelectorAll("[data-car-step]").forEach((btn) => btn.addEventListener("click", (e) => { e.stopPropagation(); stepNow(+btn.dataset.carStep); }));
        const f = c.querySelector("[data-zoom]");
        f.addEventListener("click", () => { if (Date.now() - swiped < 400) return; openModal(`<img class="lightbox" src="${esc(f.dataset.zoom)}" alt="Photo, enlarged" data-close tabindex="0">`); });
        c.addEventListener("keydown", (e) => { if (e.key === "ArrowLeft" || e.key === "ArrowRight") { e.preventDefault(); e.stopPropagation(); stepNow(e.key === "ArrowLeft" ? -1 : 1); } });
        let x0 = null, y0 = 0;
        c.addEventListener("touchstart", (e) => { x0 = e.touches[0].clientX; y0 = e.touches[0].clientY; }, { passive: true });
        c.addEventListener("touchend", (e) => {
          if (x0 == null) return;
          const dx = e.changedTouches[0].clientX - x0, dy = e.changedTouches[0].clientY - y0;
          x0 = null;
          if (Math.abs(dx) > 40 && Math.abs(dx) > Math.abs(dy)) { swiped = Date.now(); stepNow(dx < 0 ? 1 : -1); }
        });
      };
      let swiped = 0;
      const stepNow = (dir) => { const had = pane.contains(document.activeElement) && document.activeElement.closest("[data-car]"); step(dir); if (had) { const c = pane.querySelector("[data-car]"); c && c.focus({ preventScroll: true }); } };
      bindCard.car(pane, inc);
    }
    pane.querySelectorAll("[data-goto-reports]").forEach((b) => b.addEventListener("click", () => {
      const c = pane.querySelector("[data-car]");
      if (!c) return;
      c.scrollIntoView({ block: "center", behavior: reduceMotion ? "auto" : "smooth" });
      c.classList.remove("is-flash"); void c.offsetWidth; c.classList.add("is-flash");
      c.focus({ preventScroll: true });
    }));
    pane.querySelectorAll("[data-back]").forEach((b) => b.addEventListener("click", () => setCardOpen(false)));
    pane.querySelectorAll("details.menu, details.tip").forEach((d) => d.addEventListener("toggle", () => {
      if (d.open) pane.querySelectorAll("details.menu, details.tip").forEach((o) => o !== d && o.removeAttribute("open"));
      else S.cardSig = S.cardSig + "~"; // allow the card to refresh after the menu closes
    }));
    const form = pane.querySelector("[data-defra]");
    if (form) {
      const t = inc.triage || {};
      const orig = { size: t.size || "", waste_type: t.waste_type || "", land_type: t.land_type || "", hazards: t.hazards || "" };
      const changes = () => {
        const out = {};
        for (const k of Object.keys(orig)) { const v = form.elements[k].value.trim(); if (v !== orig[k]) out[k] = v; }
        return out;
      };
      const save = form.querySelector('[type="submit"]');
      const reset = form.querySelector("[data-df-reset]");
      const msg = form.querySelector(".df-msg");
      const update = () => {
        const c = changes();
        const n = Object.keys(c).length;
        save.disabled = !n;
        reset.hidden = !n;
        S.defraDirty = n ? inc.id : null;
        Object.keys(orig).forEach((k) => form.elements[k].closest(".df-row").classList.toggle("is-dirty", k in c));
        if (n) msg.textContent = `${n} unsaved change${n > 1 ? "s" : ""}`;
      };
      form.addEventListener("input", update);
      form.addEventListener("change", update);
      reset.addEventListener("click", () => { S.defraDirty = null; S.cardSig = ""; renderCard(); });
      form.addEventListener("submit", (e) => {
        e.preventDefault();
        const c = changes();
        if (!Object.keys(c).length) return;
        S.defraDirty = null;
        doAction(inc.id, "override", { fields: c });
      });
    }
  }

  // ---------- Actions ----------
  const ACT_TEXT = {
    schedule: (inc) => (inc.triage && inc.triage.decision === "specialist" ? "Licensed contractor booked" : "Crew booked"),
    hold: () => "Held for officer inspection",
    forward: (inc) => `Referred to ${(inc.triage && inc.triage.forward_to) || "the responsible body"}`,
    inspect: () => "Inspection recorded",
    clear: () => "Marked cleared",
    not_fly_tip: () => "Closed as not fly-tipping",
    reopen: () => "Reopened",
    warning_letter: () => "Warning letter sent",
    fpn: () => "Fixed penalty notice issued",
    prosecution: () => "Referred for prosecution",
  };
  const ACT_KIND = { schedule: "scheduled", hold: "held", forward: "note", inspect: "inspected", clear: "cleared", not_fly_tip: "note", override: "note", warning_letter: "enforcement", fpn: "enforcement", prosecution: "enforcement", reopen: "note" };

  function markOverridden(t, fields) {
    const orig = Object.assign({}, t.ai_original || {});
    const ov = new Set(overriddenList(t));
    for (const [k, v] of Object.entries(fields)) {
      if (!(k in orig)) orig[k] = t[k];
      t[k] = v;
      if (orig[k] === v) { ov.delete(k); delete orig[k]; } else ov.add(k);
    }
    t.overridden = [...ov];
    t.ai_original = orig;
  }

  function applyLocal(inc, action, extra = {}) {
    const now = new Date().toISOString();
    let text = ACT_TEXT[action] ? ACT_TEXT[action](inc) : action;
    if (action === "schedule") inc.status = "scheduled";
    if (action === "hold") inc.status = "held";
    if (action === "not_fly_tip") inc.status = "not_fly_tip";
    if (action === "forward") inc.status = "forwarded";
    if (action === "reopen") inc.status = "triaged";
    if (action === "clear") {
      inc.status = "cleared";
      inc.cleared_at = now;
      if (extra.photoUrl) inc.cleared_photo_url = extra.photoUrl;
    }
    if (action === "override" && inc.triage && extra.fields) {
      inc.triage = Object.assign({}, inc.triage);
      markOverridden(inc.triage, extra.fields);
      text = `Classification corrected: ${Object.keys(extra.fields).map((k) => FIELD_LABEL[k] || k).join(", ")}`;
    }
    if (action === "override" && inc.triage && extra.decision) {
      const label = (STATUS[extra.decision] || [extra.decision])[0];
      inc.triage = Object.assign({}, inc.triage);
      markOverridden(inc.triage, { decision: extra.decision });
      inc.triage.decision_why = "Decision changed by an officer";
      if (extra.decision === "not_a_fly_tip") inc.status = "not_fly_tip";
      else if (["triaging", "not_fly_tip"].includes(inc.status) || (extra.decision === "clear_now" && inc.status === "held")) inc.status = "triaged";
      else if (["hold_for_officer", "specialist", "review"].includes(extra.decision) && inc.status === "scheduled") inc.status = "triaged";
      text = `Decision changed to ${label}`;
    }
    if (extra.note) text += ` (${extra.note})`;
    inc.updated_at = now;
    inc.timeline = (inc.timeline || []).concat([{ at: now, kind: ACT_KIND[action] || "note", text }]);
    return text;
  }

  async function doAction(id, action, extra = {}) {
    const inc = S.incidents.find((i) => i.id === id);
    if (!inc) return;
    const before = JSON.parse(JSON.stringify(inc));
    const text = applyLocal(inc, action, extra);
    if (action === "clear") S.justCleared = id;
    if (action === "reopen") S.qtab = bucket(inc);
    S.pending.add(id);
    S.cardSig = "";
    renderQueue(true);
    const where = esc(inc.street || caseRef(inc));
    if (MOCK) {
      S.pending.delete(id);
      toast(`${esc(text)} · ${where}`);
      if (maps.main) renderMapIncidents();
      return;
    }
    try {
      let body;
      if (action === "clear" && extra.file) {
        body = new FormData();
        body.append("action", "clear");
        body.append("photo", extra.file);
        if (extra.note) body.append("note", extra.note);
      } else {
        body = { action };
        if (extra.decision) body.decision = extra.decision;
        if (extra.fields) Object.assign(body, extra.fields);
        if (extra.note) body.note = extra.note;
      }
      const updated = await CH.post(`/api/incidents/${id}/actions`, body);
      S.pending.delete(id);
      if (updated && updated.id != null) {
        const i = S.incidents.findIndex((x) => x.id === id);
        if (i >= 0) S.incidents[i] = updated;
      }
      toast(`${esc(text)} · ${where}`);
      S.cardSig = "";
      renderQueue(true);
    } catch (e) {
      S.pending.delete(id);
      const i = S.incidents.findIndex((x) => x.id === id);
      if (i >= 0) S.incidents[i] = before;
      S.cardSig = "";
      renderQueue(true);
      const code = (e.data && e.data.error) || e.message;
      if (e.status === 409 && code === "closed") { toast("This incident is closed. Reopen it to make changes."); poll(); }
      else if (e.status === 409 && code === "not_closed") { toast("This incident is already open."); poll(); }
      else toast(`Could not save (${esc(e.message)}). No changes were made.`);
    }
    if (maps.main) renderMapIncidents();
  }

  function clearModal(inc) {
    openModal(`<div class="modal" role="dialog" aria-modal="true" aria-labelledby="clr-h">
      <h3 id="clr-h">Mark cleared: ${esc(inc.street)}</h3>
      <p>Attach a photo of the cleared site. It will be shown on the public map.</p>
      <label class="drop" id="clr-drop" tabindex="0">${I.camera}<span><b>Choose a photo</b> or drag it here</span><input type="file" accept="image/*" id="clr-file" hidden></label>
      <textarea id="clr-note" placeholder="Note (optional)" aria-label="Note"></textarea>
      <div class="modal-actions"><button class="btn btn-ghost" data-close>Cancel</button><button class="btn btn-primary" id="clr-go" disabled>Mark cleared</button></div>
    </div>`, (m, closeIt) => {
      let file = null;
      const drop = $("#clr-drop", m), input = $("#clr-file", m), go = $("#clr-go", m);
      const setFile = (f) => {
        if (!f) return;
        file = f;
        drop.innerHTML = `<img src="${URL.createObjectURL(f)}" alt="After photo preview"><span>${esc(f.name)}</span>`;
        drop.appendChild(input);
        go.disabled = false;
      };
      input.addEventListener("change", () => setFile(input.files[0]));
      drop.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); input.click(); } });
      drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("is-over"); });
      drop.addEventListener("dragleave", () => drop.classList.remove("is-over"));
      drop.addEventListener("drop", (e) => { e.preventDefault(); drop.classList.remove("is-over"); setFile(e.dataTransfer.files[0]); });
      go.addEventListener("click", () => {
        const note = $("#clr-note", m).value.trim();
        closeIt();
        doAction(inc.id, "clear", { file, note, photoUrl: file ? URL.createObjectURL(file) : null });
      });
    });
  }

  // ---------- Map ----------
  const maps = {};
  const LIVERPOOL = [53.4084, -2.9916];
  function baseMap(el) {
    const m = L.map(el, { zoomControl: true, attributionControl: true }).setView(LIVERPOOL, 13);
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    }).addTo(m);
    m.zoomControl.setPosition("bottomright");
    return m;
  }
  function incIcon(inc) {
    const cls = stLabel(mapKey(inc))[1];
    return L.divIcon({
      className: "cc-divicon", iconSize: [22, 22], iconAnchor: [11, 11], popupAnchor: [0, -12],
      html: `<div class="mk ${cls}">${inc.report_count > 1 ? `<span class="mk-n">${inc.report_count}</span>` : ""}</div>`,
    });
  }
  function incPopup(inc) {
    return `<div class="pop"><img src="${esc(inc.photo_url)}" alt=""><div><h4>${esc(inc.street)}</h4><p><span class="mono">${esc(caseRef(inc))}</span><br>${esc(inc.ward)} · ${esc(ago(inc.created_at))}${inc.report_count > 1 ? ` · ${inc.report_count} reports` : ""}</p>${pill(inc)} ${priBadge(inc)}<br><button class="btn" data-open="${inc.id}">Open</button></div></div>`;
  }

  async function initMap() {
    if (maps.main) { maps.main.invalidateSize(); return; }
    const m = baseMap("map-main");
    maps.main = m;
    maps.mainLayers = { inc: L.layerGroup().addTo(m), hist: L.layerGroup().addTo(m), rings: L.layerGroup().addTo(m) };
    m.on("popupopen", (e) => {
      const b = e.popup.getElement().querySelector("[data-open]");
      if (b) b.onclick = () => openIncident(+b.dataset.open);
    });
    renderMapIncidents(true);
    fitIncidents();
    try {
      const [hist, hot] = await Promise.all([S.history || CH.get("/api/history"), S.hotspots || CH.get("/api/hotspots")]);
      S.history = hist; S.hotspots = hot;
      const r = L.canvas({ padding: 0.3 });
      const ink = cssVar("--ink-2") || "#3E4141";
      hist.forEach((p) => L.circleMarker([p.lat, p.lon], { renderer: r, radius: 4, stroke: false, fillColor: ink, fillOpacity: 0.16, interactive: false }).addTo(maps.mainLayers.hist));
      hot.forEach((h) => {
        const rep = h.state === "repeat";
        L.circleMarker([h.lat, h.lon], { radius: rep ? 21 : 16, color: cssVar("--brand"), weight: rep ? 2.5 : 1.8, dashArray: rep ? null : "4 4", fill: true, fillColor: cssVar("--brand"), fillOpacity: rep ? 0.08 : 0.03, interactive: true })
          .bindTooltip(`${esc(h.street)} · ${HS[h.state] ? HS[h.state].label : h.state} · ${h.reports_90d} in 90 days`, { className: "hs-label", direction: "top" })
          .addTo(maps.mainLayers.rings);
      });
      maps.mainLayers.inc.eachLayer((l) => l.bringToFront && l.bringToFront());
      renderMapPanel();
    } catch (e) {
      toast("Could not load map layers.");
    }
  }

  function fitIncidents() {
    const pts = S.incidents.filter((i) => i.lat != null).map((i) => [i.lat, i.lon]);
    const pad = phone.matches ? { padding: [24, 24] } : { paddingTopLeft: [340, 40], paddingBottomRight: [40, 40] };
    if (pts.length > 1) maps.main.fitBounds(pts, Object.assign(pad, { maxZoom: 15 }));
    maps.fitted = pts.length > 1;
  }

  function renderMapIncidents(force = false) {
    const sig = [...S.mapFilter].join() + S.incidents.map(incSig).join(";");
    if (!force && sig === maps.sig) return;
    maps.sig = sig;
    const g = maps.mainLayers.inc;
    g.clearLayers();
    if (!maps.fitted) fitIncidents();
    S.incidents.forEach((inc) => {
      if (!S.mapFilter.has(mapKey(inc)) || inc.lat == null) return;
      L.marker([inc.lat, inc.lon], { icon: incIcon(inc), riseOnHover: true, zIndexOffset: isOpen(inc) ? 500 : 0, title: `${inc.street}: ${stLabel(mapKey(inc))[0]}` })
        .bindPopup(incPopup(inc)).addTo(g);
    });
    renderMapPanel();
  }

  function renderMapPanel() {
    const counts = {};
    S.incidents.forEach((i) => { const k = mapKey(i); counts[k] = (counts[k] || 0) + 1; });
    const help = { clear_now: DEC_HELP.clear_now, review: DEC_HELP.review, hold_for_officer: DEC_HELP.hold_for_officer, specialist: DEC_HELP.specialist, not_fly_tip: DEC_HELP.not_a_fly_tip, triaging: "Photo being classified.", scheduled: "Crew or contractor booked.", cleared: "Site cleared.", forwarded: "Referred to the responsible body, such as a landowner." };
    const panel = $("#map-panel");
    const wasOpen = panel.querySelector("details.map-more") && panel.querySelector("details.map-more").open;
    panel.innerHTML = `
      <div class="map-panel-h"><h2>Incidents</h2><span class="muted">${S.incidents.filter(isOpen).length} open · ${S.incidents.length} total</span></div>
      <div class="chips" role="group" aria-label="Show or hide by status">${MAP_KEYS.map((k) => {
        const [lbl, cls] = stLabel(k);
        return `<button type="button" class="chip" data-k="${k}" aria-pressed="${S.mapFilter.has(k)}" title="${esc(help[k] || "")}"><i class="dot-${cls}"></i>${lbl} <b>${counts[k] || 0}</b></button>`;
      }).join("")}</div>
      <details class="map-more" ${wasOpen || !phone.matches ? "open" : ""}><summary>Layers and key</summary>
        <label class="toggle"><input type="checkbox" data-layer="history" ${S.layers.history ? "checked" : ""}> Past reports${S.history ? ` · ${num(S.history.length)}` : ""}</label>
        <label class="toggle"><input type="checkbox" data-layer="rings" ${S.layers.rings ? "checked" : ""}> Hotspots${S.hotspots ? ` · ${S.hotspots.length}` : ""}</label>
        <div class="legend">
          <div class="lg-dec">${decisionPill("review")}<span>${esc(DEC_HELP.review)}</span></div>
          <div class="lg-dec">${decisionPill("hold_for_officer")}<span>${esc(DEC_HELP.hold_for_officer)}</span></div>
          <div><span class="lg-hist"></span>Past report</div>
          <div><span class="lg-ring"></span>New site or emerging hotspot</div>
          <div><span class="lg-ring repeat"></span>Repeat hotspot</div>
        </div>
      </details>`;
    $$("#map-panel .chip").forEach((c) => c.addEventListener("click", () => {
      const k = c.dataset.k;
      S.mapFilter.has(k) ? S.mapFilter.delete(k) : S.mapFilter.add(k);
      renderMapIncidents(true);
    }));
    $$("#map-panel [data-layer]").forEach((cb) => cb.addEventListener("change", () => {
      const l = cb.dataset.layer;
      S.layers[l] = cb.checked;
      const layer = l === "history" ? maps.mainLayers.hist : maps.mainLayers.rings;
      cb.checked ? layer.addTo(maps.main) : layer.remove();
    }));
  }

  // ---------- Module views (Routes, Return, Reduce) ----------
  const VIEW_FN = { routes: "routes", return: "ret", reduce: "reduce" };
  let viewCleanup = null, viewOn = null;
  const ctx = { CH, L: window.L, openIncident, goTo: (tab) => switchTab(tab) };
  function unmountView() {
    if (!viewOn) return;
    try { if (typeof viewCleanup === "function") viewCleanup(); } catch (e) { console.error(e); }
    const el = $(`#cv-${viewOn}`);
    if (el) el.innerHTML = "";
    viewCleanup = null; viewOn = null;
  }
  function mountView(name) {
    const el = $(`#cv-${name}`);
    const fn = window.CHViews && window.CHViews[VIEW_FN[name]];
    viewOn = name;
    if (typeof fn !== "function") {
      el.innerHTML = `<div class="cv-wait"><span class="pill triaging">Loading</span></div>`;
      return;
    }
    try { viewCleanup = fn(el, ctx) || null; } catch (e) {
      console.error(e);
      el.innerHTML = `<div class="cv-wait"><p>This page could not be loaded. Refresh to try again.</p></div>`;
    }
  }

  // ---------- Tabs ----------
  const TABS = ["queue", "map", "routes", "return", "reduce"];
  function switchTab(name) {
    if (!TABS.includes(name)) name = "queue";
    const was = S.tab;
    if (was !== name || viewOn !== (VIEW_FN[name] ? name : null)) unmountView();
    S.tab = name;
    TABS.forEach((t) => {
      $(`#tab-${t}`).setAttribute("aria-selected", String(t === name));
      $(`#tab-${t}`).tabIndex = t === name ? 0 : -1;
      $(`#view-${t}`).hidden = t !== name;
    });
    document.body.dataset.tab = name;
    if (location.hash !== `#${name}`) history.replaceState(null, "", `${location.pathname}${location.search}#${name}`);
    if (name === "map") initMap();
    if (name === "queue") requestAnimationFrame(refreshCardMap);
    if (VIEW_FN[name] && viewOn !== name) mountView(name);
  }

  // Pop-ups (More, decision legend, account): anchored under their trigger, flipped above if there's no room, kept in the viewport.
  const POPS = "details.menu, details.tip, details.cc-user";
  function placePop(d) {
    const pop = d.querySelector(":scope > .menu-pop, :scope > .tip-pop, :scope > .cc-user-pop");
    const sum = d.querySelector(":scope > summary");
    if (!pop || !sum) return;
    const vw = document.documentElement.clientWidth, vh = window.innerHeight, m = 8, gap = 6;
    Object.assign(pop.style, { position: "fixed", right: "auto", bottom: "auto", left: "0px", top: "0px", maxWidth: `${vw - 2 * m}px`, maxHeight: "", overflow: "auto" });
    const r = sum.getBoundingClientRect();
    const pw = pop.offsetWidth, ph = pop.offsetHeight;
    const alignRight = r.left + r.width / 2 > vw / 2;
    let left = alignRight ? r.right - pw : r.left;
    left = Math.max(m, Math.min(left, vw - pw - m));
    let top = r.bottom + gap;
    const below = vh - top - m, above = r.top - gap - m;
    if (ph > below && above > below) { const h = Math.min(ph, above); top = r.top - gap - h; pop.style.maxHeight = `${h}px`; }
    else if (ph > below) pop.style.maxHeight = `${Math.max(120, below)}px`;
    pop.style.left = `${left}px`; pop.style.top = `${top}px`;
    const got = pop.getBoundingClientRect(); // correct for a transformed ancestor
    if (Math.abs(got.left - left) > 1 || Math.abs(got.top - top) > 1) { pop.style.left = `${2 * left - got.left}px`; pop.style.top = `${2 * top - got.top}px`; }
  }
  const placeOpenPops = () => $$(`${POPS}`).forEach((d) => d.open && placePop(d));
  document.addEventListener("toggle", (e) => { if (e.target.matches && e.target.matches(POPS) && e.target.open) placePop(e.target); }, true);
  window.addEventListener("resize", placeOpenPops);
  document.addEventListener("scroll", placeOpenPops, true);

  function bindShell() {
    $$(".cc-tabs [data-tab]").forEach((b) => b.addEventListener("click", () => switchTab(b.dataset.tab)));
    $(".cc-tabs").addEventListener("keydown", (e) => {
      if (!["ArrowDown", "ArrowUp", "ArrowLeft", "ArrowRight"].includes(e.key)) return;
      e.preventDefault();
      const i = TABS.indexOf(S.tab) + (e.key === "ArrowDown" || e.key === "ArrowRight" ? 1 : -1);
      const t = TABS[(i + TABS.length) % TABS.length];
      switchTab(t);
      $(`#tab-${t}`).focus();
    });
    const pickFirst = () => { const f = visibleIncidents()[0]; if (f && !phone.matches) select(f.id, { open: false }); };
    $$("#q-tabs [data-qt]").forEach((b) => b.addEventListener("click", () => {
      S.qtab = b.dataset.qt; S.f.dec.clear();
      renderQueue(true); pickFirst();
    }));
    $$("#q-sort [data-sort]").forEach((b) => b.addEventListener("click", () => { S.sort = b.dataset.sort; renderQueue(true); }));
    $("#q-filter-btn").addEventListener("click", () => { S.fOpen = !S.fOpen; renderQueue(true); });
    const clearFilters = () => { S.f = { dec: new Set(), ward: "", pri: "", growing: false }; renderQueue(true); pickFirst(); };
    $("#q-clear").addEventListener("click", clearFilters);
    const fp = $("#q-filters");
    fp.addEventListener("click", (e) => {
      const c = e.target.closest("[data-dec]");
      if (!c) return;
      const k = c.dataset.dec;
      S.f.dec.has(k) ? S.f.dec.delete(k) : S.f.dec.add(k);
      renderQueue(true); pickFirst();
    });
    fp.addEventListener("change", (e) => {
      if (e.target.id === "f-ward") S.f.ward = e.target.value;
      if (e.target.id === "f-pri") S.f.pri = e.target.value;
      if (e.target.id === "f-grow") S.f.growing = e.target.checked;
      renderQueue(true); pickFirst();
    });
    const ol = $("#q-list");
    ol.setAttribute("role", "listbox");
    ol.addEventListener("click", (e) => {
      if (e.target.closest("[data-clear-filters]")) return clearFilters();
      const li = e.target.closest(".q-item"); if (li) select(+li.dataset.id);
    });
    ol.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") { const li = e.target.closest(".q-item"); if (li) { e.preventDefault(); select(+li.dataset.id); } }
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && S.cardOpen && !$("#cc-modal").innerHTML) { setCardOpen(false); return; }
      if (S.tab !== "queue" || !["ArrowDown", "ArrowUp", "j", "k"].includes(e.key)) return;
      if (e.target.closest("input, textarea, select, .cc-tabs, details, .cc-modal")) return;
      const list = visibleIncidents();
      const i = list.findIndex((x) => x.id === S.selected);
      const next = list[Math.max(0, Math.min(list.length - 1, i + (e.key === "ArrowDown" || e.key === "j" ? 1 : -1)))];
      if (next) { e.preventDefault(); select(next.id, { open: false }); const li = $(`#q-list .q-item[data-id="${next.id}"]`); if (li) li.focus({ preventScroll: true }); }
    });
    document.addEventListener("click", (e) => {
      $$("details.menu[open], details.tip[open], details.cc-user[open]").forEach((d) => { if (!d.contains(e.target)) d.removeAttribute("open"); });
    });
    document.addEventListener("keydown", (e) => { if (e.key === "Escape") $$("details.menu[open], details.tip[open], details.cc-user[open]").forEach((d) => d.removeAttribute("open")); });
    window.addEventListener("hashchange", () => switchTab(location.hash.slice(1)));
    phone.addEventListener("change", () => { if (!phone.matches) setCardOpen(false); if (maps.main) maps.main.invalidateSize(); });
  }

  // ---------- Dummy staff sign-in ----------
  const AUTH_KEY = "mvcc_ft_staff";
  const DEMO_EMAIL = "john.smith@mersey-vale.example";
  function getUser() { try { return JSON.parse(localStorage.getItem(AUTH_KEY) || "null"); } catch (e) { return null; } }
  function nameFrom(email) {
    const local = String(email || "").split("@")[0] || "Officer";
    return local.split(/[._-]+/).filter(Boolean).map((w) => w[0].toUpperCase() + w.slice(1)).join(" ");
  }
  function showUser(u) {
    const name = u.name || nameFrom(u.email);
    $("#cc-user-av").textContent = name.split(" ").map((w) => w[0]).join("").slice(0, 2).toUpperCase();
    $("#cc-user-name").textContent = name;
    $("#cc-user-email").textContent = u.email;
  }
  let signinBound = false;
  function signIn() {
    const signin = $("#signin");
    signin.hidden = false;
    $("#app").hidden = true;
    document.body.dataset.auth = "out";
    const email = $("#si-email");
    email.value = email.value || DEMO_EMAIL;
    // On this laptop any password works. Phones reach the console through the tunnel and need the real one.
    const onLaptop = /^(localhost|127\.0\.0\.1|\[::1\])$/.test(location.hostname);
    if (!onLaptop) {
      $("#si-pass").value = "";
      $(".si-note").textContent = "Demonstration system. Ask the team for the password.";
    }
    if (!signinBound) {
      signinBound = true;
      $("#si-form").addEventListener("submit", async (e) => {
        e.preventDefault();
        const errEl = $("#si-err");
        errEl.hidden = true;
        try {
          await CH.post("/api/council/login", { password: $("#si-pass").value });
        } catch (err) {
          errEl.textContent = err && err.status === 401 ? "That password is not right." : "Could not reach the council system. Try again.";
          errEl.hidden = false;
          $("#si-pass").focus();
          return;
        }
        const u = { email: email.value.trim() || DEMO_EMAIL, at: new Date().toISOString() };
        u.name = u.email === DEMO_EMAIL ? "John Smith" : nameFrom(u.email);
        try { localStorage.setItem(AUTH_KEY, JSON.stringify(u)); } catch (err) { /* private mode: continue */ }
        signin.hidden = true;
        startApp(u);
      });
    }
    $("#si-go").focus();
  }
  function signOut(e) {
    if (e) { e.preventDefault(); e.stopPropagation(); }
    try { localStorage.removeItem(AUTH_KEY); } catch (err) { /* ignore */ }
    const menu = $("details.cc-user"); if (menu) menu.removeAttribute("open");
    setCardOpen(false);
    signIn();
  }

  // ---------- Boot ----------
  let started = false;
  async function startApp(u) {
    document.body.dataset.auth = "in";
    $("#app").hidden = false;
    $("#signin").hidden = true;
    showUser(u);
    if (started) { switchTab(S.tab || "queue"); return; }
    started = true;
    $("#cc-signout").addEventListener("click", signOut);
    bindShell();
    switchTab(location.hash.slice(1) || "queue");
    try {
      const list = await CH.get("/api/incidents?view=council");
      if (MOCK) mockSimulate(list);
      else mergeIncidents(list, true);
    } catch (e) {
      S.offline = true;
      $("#q-list").innerHTML = `<li class="q-empty">Server unavailable. Retrying.</li>`;
    }
    if (S.tab === "map") { maps.main && maps.main.invalidateSize(); renderMapIncidents(true); }
    if (!MOCK) setInterval(poll, 3000);
    setInterval(() => renderQueue(), 30000); // keep "x min ago" fresh
    setInterval(() => $$(".tick[data-since]").forEach((t) => { t.textContent = `${Math.max(0, Math.round((Date.now() - new Date(t.dataset.since)) / 1000))} s`; }), 1000);
  }

  const user = getUser();
  if (user && user.email) {
    // A phone signed in earlier keeps its session only while the password is unchanged.
    CH.get("/api/council/session").then(() => startApp(user)).catch((e) => {
      if (/^401\b/.test(String(e && e.message))) { try { localStorage.removeItem(AUTH_KEY); } catch (err) { /* ignore */ } signIn(); }
      else startApp(user);
    });
  } else signIn();
})();
