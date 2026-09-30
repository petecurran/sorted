// Council view: today's crew and officer routes. Exposes CHViews.routes(el, ctx) -> cleanup.
// Normalises older response shapes as well as the current one.
(function () {
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const TEAMS = {
    crew: { name: "Crew route", send: "Send to crew", scan: "Scan to open on a phone", color: "var(--st-clear)", hex: "#006C11" },
    officer: { name: "Officer route", send: "Send to officer", scan: "Scan to open on a phone", color: "var(--st-hold)", hex: "#A66A00" },
  };

  const STRAIGHT_RE = /straight|fallback|nearest|2-opt/i;
  // The API's order_method is technical, so it is never shown as is.
  function methodText(straight, urgentFirst) {
    const parts = [];
    if (straight) parts.push("Road data unavailable");
    if (urgentFirst) parts.push("Urgent jobs first");
    return parts.join(". ");
  }

  function gmapsUrls(depot, stops) {
    const urls = [];
    let prev = depot;
    for (let i = 0; i < stops.length; i += 9) {
      const c = stops.slice(i, i + 9), dest = c[c.length - 1];
      const q = new URLSearchParams({ api: "1", origin: `${prev.lat},${prev.lon}`, destination: `${dest.lat},${dest.lon}`, travelmode: "driving" });
      if (c.length > 1) q.set("waypoints", c.slice(0, -1).map((s) => `${s.lat},${s.lon}`).join("|"));
      urls.push("https://www.google.com/maps/dir/?" + q.toString());
      prev = dest;
    }
    return urls;
  }

  // Older shapes: derive leg minutes from eta_min, strip "Street: " label prefixes, build Maps links client-side.
  function normalise(d, team) {
    const svc = d.service_min_per_stop || 0;
    // Forwarded incidents belong to another authority, so they never go on a route.
    const stops = (d.stops || []).filter((s) => s.status !== "forwarded").map((s, i, arr) => {
      let mins = s.drive_min_from_prev;
      if (mins == null && s.eta_min != null) mins = i === 0 ? s.eta_min : Math.max(0, s.eta_min - arr[i - 1].eta_min - svc);
      const street = s.street || "";
      let label = s.label || "";
      if (street && label.startsWith(street + ": ")) label = label.slice(street.length + 2);
      return {
        id: s.incident_id, ref: s.case_ref || "", order: s.order || i + 1, lat: s.lat, lon: s.lon, street, label,
        urgent: s.priority_level === "urgent" || (!s.priority_level && s.decision === "specialist"),
        mins, km: s.drive_km_from_prev,
      };
    });
    const depot = Object.assign({}, d.depot || {});
    depot.name = String(depot.name || "Depot").replace(/\s*\(demo\)\s*$/i, "");
    const urls = (d.google_maps_urls && d.google_maps_urls.length) ? d.google_maps_urls : (stops.length ? gmapsUrls(depot, stops) : []);
    // Road geometry comes from OSRM. Only when the API says it fell back (or sent no geometry) do we
    // join the stops with straight lines, and then the card says so.
    const method = d.order_method || (d.source === "osrm" ? "OSRM" : d.source ? "straight" : "");
    let geometry = Array.isArray(d.geometry) ? d.geometry : [];
    const straight = stops.length > 0 && (STRAIGHT_RE.test(method) || geometry.length < 2);
    if (straight && geometry.length < 2 && depot.lat != null) {
      geometry = [[depot.lat, depot.lon], ...stops.map((s) => [s.lat, s.lon]), [depot.lat, depot.lon]];
    }
    return {
      team, depot, stops, urls,
      qr: d.qr_url || null,
      totalMin: d.total_drive_min != null ? d.total_drive_min : (d.drive_min != null ? d.drive_min : d.duration_min),
      totalKm: d.total_km != null ? d.total_km : d.distance_km,
      method: methodText(straight, d.urgent_first === true || (d.urgent_first == null && stops.some((s) => s.urgent))),
      back: d.return_to_depot ? { mins: d.return_to_depot.drive_min, km: d.return_to_depot.drive_km } : null,
      geometry, straight,
    };
  }

  function fmtMin(m) {
    if (m == null) return "";
    m = Math.round(m);
    return m >= 60 ? `${Math.floor(m / 60)} h${m % 60 ? ` ${m % 60} min` : ""}` : `${m} min`;
  }
  const fmtKm = (k) => (k == null ? "" : `${Number(k).toFixed(1)} km`);
  const leg = (s) => [fmtMin(s.mins), fmtKm(s.km)].filter(Boolean).join(" · ");

  function teamCard(r) {
    const t = TEAMS[r.team];
    if (!r.stops.length) {
      return `<section class="cv-card cv-team" style="--team:${t.color}">
        <div class="cv-team-top"><h3 class="cv-team-name"><span class="cv-swatch"></span>${t.name}</h3></div>
        <p class="cv-empty">No stops today.</p></section>`;
    }
    const parts = r.urls.slice(1).map((u, i) => `<a class="cv-link" href="${esc(u)}" target="_blank" rel="noopener">Part ${i + 2}</a>`).join("");
    const qr = r.qr || `/api/routes/qr?team=${r.team}`;
    return `<section class="cv-card cv-team" style="--team:${t.color}" data-team="${r.team}">
      <div class="cv-team-top">
        <h3 class="cv-team-name"><span class="cv-swatch"></span>${t.name}</h3>
        <div class="cv-totals"><span><b>${esc(fmtMin(r.totalMin))}</b> driving</span><span><b>${esc(fmtKm(r.totalKm))}</b></span><span><b>${r.stops.length}</b> ${r.stops.length === 1 ? "stop" : "stops"}</span></div>
      </div>
      ${r.method ? `<p class="cv-method">${r.straight ? `<span class="cv-est">Approximate</span>` : ""}${esc(r.method)}</p>` : ""}
      <div class="cv-send">
        <img class="cv-qr" src="${esc(qr)}" alt="QR code that opens the ${r.team} route in Google Maps" title="Show larger" role="button" tabindex="0" data-qr-title="${esc(t.name)}" width="96" height="96" data-fallback="${esc(r.urls[0] ? "/api/qr?text=" + encodeURIComponent(r.urls[0]) : "")}">
        <div class="cv-send-body">
          <div class="cv-send-row">
            <a class="cv-btn cv-btn-primary" href="${esc(r.urls[0] || "#")}" target="_blank" rel="noopener">${t.send} <span aria-hidden="true">↗</span></a>
            ${parts}
          </div>
          <div class="cv-send-row">
            <button type="button" class="cv-btn cv-btn-quiet" data-copy="${esc(r.urls.join("\n"))}">Copy link</button>
            <span class="cv-hint cv-qr-hint">${t.scan}</span>
          </div>
        </div>
      </div>
      <ol class="cv-stops">
        <li class="cv-depot"><span class="cv-rail"><span class="cv-depot-mark" aria-hidden="true"></span></span><span class="cv-depot-name"><b>Start</b> ${esc(r.depot.name || "Depot")}</span></li>
        ${r.stops.map((s, i) => `
        <li class="cv-leg"><span class="cv-rail"></span><span>${esc(leg(s))}${i === 0 ? " from depot" : ""}</span></li>
        <li class="cv-stop${s.urgent ? " is-urgent" : ""}">
          <span class="cv-rail"><span class="cv-num">${i + 1}</span></span>
          <button type="button" class="cv-stop-main" data-open="${esc(s.id)}">
            <span class="cv-stop-street">${esc(s.street)}${s.urgent ? ` <span class="cv-tag-urgent">Urgent</span>` : ""}</span>
            <span class="cv-stop-label">${esc(s.label)}</span>
          </button>
          ${s.ref ? `<span class="cv-ref">${esc(s.ref.replace(/^[A-Z]+-FT-/, ""))}</span>` : ""}
        </li>`).join("")}
        ${r.back ? `<li class="cv-leg"><span class="cv-rail"></span><span>${esc(leg(r.back))}</span></li>
        <li class="cv-depot cv-depot-end"><span class="cv-rail"><span class="cv-depot-mark" aria-hidden="true"></span></span><span class="cv-depot-name"><b>Finish</b> ${esc(r.depot.name || "Depot")}</span></li>` : ""}
      </ol>
    </section>`;
  }

  function markerIcon(L, n, t, urgent) {
    return L.divIcon({
      className: "cv-mk-wrap",
      html: `<span class="cv-mk${urgent ? " is-urgent" : ""}" style="--team:${t.color}">${n}</span>`,
      iconSize: [26, 26], iconAnchor: [13, 13],
    });
  }

  // Direction arrows every ~1.75 km along the road geometry, rotated to the local heading in screen space.
  const ARROW_M = 1750;
  function metres(a, b) {
    const R = 6371000, r = Math.PI / 180;
    const dLat = (b[0] - a[0]) * r, dLon = (b[1] - a[1]) * r;
    const h = Math.sin(dLat / 2) ** 2 + Math.cos(a[0] * r) * Math.cos(b[0] * r) * Math.sin(dLon / 2) ** 2;
    return 2 * R * Math.asin(Math.sqrt(h));
  }
  function arrowPoints(geom) {
    const cum = [0];
    for (let i = 1; i < geom.length; i++) cum.push(cum[i - 1] + metres(geom[i - 1], geom[i]));
    const total = cum[cum.length - 1];
    const at = (d) => {
      let i = 1; while (i < cum.length - 1 && cum[i] < d) i++;
      const seg = cum[i] - cum[i - 1] || 1, f = Math.min(1, Math.max(0, (d - cum[i - 1]) / seg));
      return [geom[i - 1][0] + (geom[i][0] - geom[i - 1][0]) * f, geom[i - 1][1] + (geom[i][1] - geom[i - 1][1]) * f];
    };
    const out = [];
    for (let d = ARROW_M * 0.6; d < total - 300; d += ARROW_M) out.push({ p: at(d), a: at(Math.max(0, d - 40)), b: at(Math.min(total, d + 40)) });
    return out;
  }
  function arrowIcon(L, hex, deg) {
    return L.divIcon({
      className: "cv-mk-wrap cv-arrow-wrap",
      html: `<svg class="cv-arrow" viewBox="0 0 16 16" width="16" height="16" style="transform:rotate(${deg.toFixed(0)}deg)" aria-hidden="true"><path d="M3 2.5 L13.5 8 L3 13.5 L6 8 Z" fill="${hex}" stroke="#fff" stroke-width="1.6" stroke-linejoin="round"/></svg>`,
      iconSize: [16, 16], iconAnchor: [8, 8],
    });
  }

  function routes(el, ctx) {
    const { CH, L } = ctx;
    el.innerHTML = `<div class="cv cv-routes">
      <header class="cv-head">
        <div><h2 class="cv-title">Today's routes</h2><p class="cv-sub">Crew clearances and officer inspections.</p></div>
        <button type="button" class="cv-btn cv-btn-ghost" data-replan><span class="cv-spin" aria-hidden="true">↻</span> Re-plan</button>
      </header>
      <div class="cv-card cv-map-card">
        <div class="cv-map" role="region" aria-label="Map of today's routes"></div>
        <div class="cv-legend" aria-hidden="true">
          <span><i class="cv-lg-line" style="--team:var(--st-clear)"></i>Crew</span>
          <span><i class="cv-lg-line" style="--team:var(--st-hold)"></i>Officer</span>
          <span><i class="cv-lg-arrow"></i>Direction</span>
          <span><i class="cv-lg-urgent"></i>Urgent</span>
          <span><i class="cv-depot-mark"></i>Depot</span>
        </div>
      </div>
      <div class="cv-teams"><p class="cv-loading">Loading routes…</p></div>
    </div>`;
    const root = el.firstElementChild;
    const teamsEl = root.querySelector(".cv-teams");
    const mapEl = root.querySelector(".cv-map");
    let map = null, layer = null, dead = false, fit = null;
    if (L) {
      map = L.map(mapEl, { zoomControl: true, scrollWheelZoom: false }).setView([53.4084, -2.9916], 12);
      L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19, attribution: "© OpenStreetMap contributors" }).addTo(map);
      layer = L.layerGroup().addTo(map);
    }
    // Refit when the map box changes size (tab shown, window resized), so the routes always fill it.
    const ro = window.ResizeObserver ? new ResizeObserver(() => { if (!map) return; map.invalidateSize(); if (fit) map.fitBounds(fit, { padding: [28, 28], maxZoom: 15 }); }) : null;
    if (ro) ro.observe(mapEl);

    function drawMap(list) {
      if (!map) return;
      layer.clearLayers();
      const pts = [];
      list.forEach((r) => {
        const t = TEAMS[r.team];
        if (r.geometry.length > 1) {
          // smoothFactor 0: draw every OSRM vertex so the line hugs the road at any zoom.
          const dash = r.straight ? "7 8" : null;
          L.polyline(r.geometry, { color: "#fff", weight: 8, opacity: .9, smoothFactor: 0, interactive: false }).addTo(layer);
          L.polyline(r.geometry, { color: t.hex, weight: 4.5, opacity: .95, smoothFactor: 0, dashArray: dash, interactive: false }).addTo(layer);
          r.geometry.forEach((p) => pts.push(p));
          arrowPoints(r.geometry).forEach(({ p, a, b }) => {
            const pa = map.project(a, 16), pb = map.project(b, 16);
            const deg = Math.atan2(pb.y - pa.y, pb.x - pa.x) * 180 / Math.PI;
            L.marker(p, { icon: arrowIcon(L, t.hex, deg), interactive: false, keyboard: false, zIndexOffset: -200 }).addTo(layer);
          });
        }
        r.stops.forEach((s, i) => {
          pts.push([s.lat, s.lon]);
          L.marker([s.lat, s.lon], { icon: markerIcon(L, i + 1, t, s.urgent), title: `${i + 1}. ${s.street}`, riseOnHover: true })
            .on("click", () => ctx.openIncident && ctx.openIncident(s.id)).addTo(layer);
        });
      });
      const d = list[0] && list[0].depot;
      if (d && d.lat != null) {
        pts.push([d.lat, d.lon]);
        L.marker([d.lat, d.lon], { icon: L.divIcon({ className: "cv-mk-wrap", html: `<span class="cv-mk-depot" title="${esc(d.name || "Depot")}"></span>`, iconSize: [22, 22], iconAnchor: [11, 11] }), zIndexOffset: 500, keyboard: false })
          .bindTooltip("Depot", { permanent: true, direction: "top", offset: [0, -12], className: "cv-depot-tip" })
          .addTo(layer);
      }
      if (pts.length) { fit = L.latLngBounds(pts); map.invalidateSize(); map.fitBounds(fit, { padding: [28, 28], maxZoom: 15 }); }
    }

    // Click (or Enter) on a QR code shows it full size so people in the room can scan it.
    function openQr(img) {
      const box = document.createElement("div");
      box.className = "cv-qr-modal";
      box.setAttribute("role", "dialog");
      box.setAttribute("aria-modal", "true");
      box.setAttribute("aria-label", `${img.dataset.qrTitle || "Route"} QR code`);
      box.innerHTML = `<div class="cv-qr-modal-card">
          <button type="button" class="cv-qr-close" aria-label="Close">×</button>
          <h3 class="cv-qr-modal-title">${esc(img.dataset.qrTitle || "Route")}</h3>
          <img src="${esc(img.currentSrc || img.src)}" alt="${esc(img.alt)}">
          <p class="cv-qr-modal-hint">Scan to open the route in Google Maps</p>
        </div>`;
      const close = () => { box.remove(); document.removeEventListener("keydown", onKey); img.focus(); };
      const onKey = (e) => { if (e.key === "Escape") close(); };
      box.addEventListener("click", (e) => { if (e.target === box || e.target.closest(".cv-qr-close")) close(); });
      document.addEventListener("keydown", onKey);
      document.body.appendChild(box);
      box.querySelector(".cv-qr-close").focus();
    }

    function bindQr() {
      root.querySelectorAll(".cv-qr").forEach((img) => {
        img.addEventListener("click", () => openQr(img));
        img.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); openQr(img); } });
        img.addEventListener("error", () => {
          const fb = img.dataset.fallback;
          if (fb && img.getAttribute("src") !== fb) { img.src = fb; return; }
          img.hidden = true;
          const hint = img.parentElement.querySelector(".cv-qr-hint");
          if (hint) hint.hidden = true;
        });
      });
    }

    async function load() {
      const btn = root.querySelector("[data-replan]");
      btn.disabled = true; root.classList.add("is-busy");
      try {
        const [crew, officer] = await Promise.all(["crew", "officer"].map((t) => CH.get(`/api/routes?team=${t}`).then((d) => normalise(d, t))));
        if (dead) return;
        teamsEl.innerHTML = teamCard(crew) + teamCard(officer);
        bindQr();
        drawMap([crew, officer]);
      } catch (e) {
        if (!dead) teamsEl.innerHTML = `<p class="cv-error">Routes could not be loaded (${esc(e.message)}).</p>`;
      } finally {
        btn.disabled = false; root.classList.remove("is-busy");
      }
    }

    async function copy(text, btn) {
      try { await navigator.clipboard.writeText(text); }
      catch (_) {
        const ta = document.createElement("textarea"); ta.value = text; document.body.appendChild(ta); ta.select();
        try { document.execCommand("copy"); } catch (_) { /* ignore */ }
        ta.remove();
      }
      const old = btn.textContent; btn.textContent = "Copied"; btn.classList.add("is-done");
      setTimeout(() => { btn.textContent = old; btn.classList.remove("is-done"); }, 1600);
    }

    root.addEventListener("click", (e) => {
      const c = e.target.closest("[data-copy]"); if (c) return copy(c.dataset.copy, c);
      const o = e.target.closest("[data-open]"); if (o && ctx.openIncident) return ctx.openIncident(Number(o.dataset.open) || o.dataset.open);
      if (e.target.closest("[data-replan]")) load();
    });

    load();
    setTimeout(() => map && map.invalidateSize(), 60);
    return () => { dead = true; if (ro) ro.disconnect(); if (map) map.remove(); };
  }

  window.CHViews = Object.assign(window.CHViews || {}, { routes });
})();
