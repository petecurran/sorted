// Council view: Reduce, a ranked list of repeat sites with one recommended action each. Cost fields are ignored. Exposes CHViews.reduce(el, ctx) -> cleanup.
(function () {
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const STRENGTH = { strong: "Strong evidence", moderate: "Moderate evidence", weak: "Weak evidence" };
  const RANK = { strong: 0, moderate: 1, weak: 2 };
  const TOP = 10;

  // Pick the strongest recommendation as the primary action. Titles and `why` are used as the API gives them.
  function normalise(h) {
    let primary = h.primary_action, others = h.other_actions;
    if (!primary && Array.isArray(h.recommended)) {
      const recs = h.recommended.slice().sort((a, b) => (RANK[a.strength] ?? 3) - (RANK[b.strength] ?? 3));
      const p = recs[0] || {};
      primary = { title: p.title || p.action, why: p.why, strength: p.strength };
      others = recs.slice(1).map((r) => ({ title: r.title || r.action, strength: r.strength }));
    }
    return {
      id: String(h.id), lat: h.lat, lon: h.lon, street: h.street, ward: h.ward,
      n90: h.reports_90d || 0, weekly: Array.isArray(h.weekly_counts) ? h.weekly_counts : null,
      growing: !!h.growing, primary: primary || null, others: others || [],
    };
  }

  function spark(w) {
    if (!w || w.length < 2) return "";
    const W = 96, H = 26, P = 3, max = Math.max(1, ...w);
    const xy = w.map((v, i) => [P + i * (W - 2 * P) / (w.length - 1), H - P - (v / max) * (H - 2 * P)]);
    const line = xy.map((p) => p.map((n) => n.toFixed(1)).join(",")).join(" ");
    const area = `${P},${H - P} ${line} ${W - P},${H - P}`;
    const [lx, ly] = xy[xy.length - 1];
    return `<svg class="cv-spark" viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" role="img" aria-label="Reports per week, last 12 weeks: ${w.join(", ")}">
      <polygon points="${area}" class="cv-spark-area"/><polyline points="${line}" class="cv-spark-line"/><circle cx="${lx.toFixed(1)}" cy="${ly.toFixed(1)}" r="2.6" class="cv-spark-dot"/></svg>`;
  }

  const dot = (s) => `<span class="cv-dot is-${esc(s || "weak")}" title="${esc(STRENGTH[s] || "")}" aria-label="${esc(STRENGTH[s] || "")}"></span>`;

  function row(h, i) {
    const p = h.primary || {};
    const more = h.others.length > 0;
    return `<li class="cv-hs" data-id="${esc(h.id)}">
      <div class="cv-hs-row"${more ? ` tabindex="0" role="button" aria-expanded="false" aria-label="${esc(h.street)}: show other actions"` : ""}>
        <span class="cv-rank">${i + 1}</span>
        <div class="cv-hs-place"><span class="cv-hs-street">${esc(h.street)}</span><span class="cv-hs-ward">${esc(h.ward)}${h.growing ? ` <span class="cv-grow">↑ Rising</span>` : ""}</span></div>
        <div class="cv-hs-count"><b>${h.n90}</b><span class="cv-hs-unit">in 90 days</span></div>
        <div class="cv-hs-trend">${spark(h.weekly)}</div>
        <div class="cv-hs-action">${dot(p.strength)}<div><span class="cv-act-title">${esc(p.title || "No recommended action")}</span>${p.why ? `<span class="cv-act-why">${esc(p.why)}</span>` : ""}</div></div>
      </div>
      ${more ? `<div class="cv-hs-more" hidden><span class="cv-more-label">Other options</span><ul>${h.others.map((o) => `<li>${dot(o.strength)}${esc(o.title)}</li>`).join("")}</ul></div>` : ""}
    </li>`;
  }

  function reduce(el, ctx) {
    const { CH, L } = ctx;
    let list = [], map = null, markers = {}, dead = false;
    el.innerHTML = `<div class="cv cv-reduce">
      <header class="cv-head">
        <div><h2 class="cv-title">Reduce</h2><p class="cv-sub">Top 10 repeat sites by reports in the last 90 days.</p></div>
        <div class="cv-key" aria-hidden="true"><span class="cv-key-label">Evidence</span><span>${dot("strong")}Strong</span><span>${dot("moderate")}Moderate</span><span>${dot("weak")}Weak</span></div>
      </header>
      <div class="cv-reduce-grid">
        <div class="cv-hs-table">
          <div class="cv-hs-row cv-hs-cols" aria-hidden="true"><span></span><span>Site</span><span class="cv-col-num">Reports</span><span class="cv-col-trend">12 weeks</span><span>Recommended action</span></div>
          <ol class="cv-hs-list"><li class="cv-loading">Loading sites…</li></ol>
        </div>
        <aside class="cv-card cv-hs-mapcard"><div class="cv-hs-map" role="region" aria-label="Map of repeat sites"></div></aside>
      </div>
    </div>`;
    const root = el.firstElementChild;
    const listEl = root.querySelector(".cv-hs-list");
    const mapEl = root.querySelector(".cv-hs-map");
    const ro = window.ResizeObserver ? new ResizeObserver(() => map && map.invalidateSize()) : null;

    function drawMap() {
      if (!L) return;
      map = L.map(mapEl, { zoomControl: false, scrollWheelZoom: false, attributionControl: true });
      L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19, attribution: "© OpenStreetMap" }).addTo(map);
      const pts = [];
      list.forEach((h, i) => {
        if (h.lat == null) return;
        pts.push([h.lat, h.lon]);
        const size = Math.round(20 + Math.min(14, h.n90));
        markers[h.id] = L.marker([h.lat, h.lon], {
          icon: L.divIcon({ className: "cv-mk-wrap", html: `<span class="cv-hs-mk${h.growing ? " is-growing" : ""}" style="width:${size}px;height:${size}px">${i + 1}</span>`, iconSize: [size, size], iconAnchor: [size / 2, size / 2] }),
          title: h.street, zIndexOffset: (TOP - i) * 10,
        }).on("click", () => focusRow(h.id)).addTo(map);
      });
      if (pts.length) map.fitBounds(L.latLngBounds(pts), { padding: [24, 24], maxZoom: 14 });
      if (ro) ro.observe(mapEl);
    }

    function focusRow(id) {
      const li = listEl.querySelector(`.cv-hs[data-id="${CSS.escape(id)}"]`); if (!li) return;
      li.scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "center" });
      li.classList.remove("is-flash"); void li.offsetWidth; li.classList.add("is-flash");
    }

    function toggleMore(li) {
      const more = li.querySelector(".cv-hs-more"), r = li.querySelector(".cv-hs-row");
      if (!more) return;
      more.hidden = !more.hidden; r.setAttribute("aria-expanded", String(!more.hidden)); li.classList.toggle("is-open", !more.hidden);
    }

    root.addEventListener("click", (e) => {
      const li = e.target.closest(".cv-hs");
      if (li && e.target.closest(".cv-hs-row")) toggleMore(li);
    });
    root.addEventListener("keydown", (e) => {
      if ((e.key === "Enter" || e.key === " ") && e.target.classList.contains("cv-hs-row")) { e.preventDefault(); toggleMore(e.target.closest(".cv-hs")); }
    });

    (async () => {
      try {
        const raw = await CH.get("/api/hotspots");
        if (dead) return;
        list = (raw || []).map(normalise)
          .sort((a, b) => (b.n90 - a.n90) || (b.growing - a.growing))
          .slice(0, TOP);
        listEl.innerHTML = list.length ? list.map((h, i) => row(h, i)).join("") : `<li class="cv-empty">No repeat sites.</li>`;
        drawMap();
      } catch (e) {
        if (!dead) listEl.innerHTML = `<li class="cv-error">Sites could not be loaded (${esc(e.message)}).</li>`;
      }
    })();

    return () => { dead = true; if (ro) ro.disconnect(); if (map) map.remove(); };
  }

  window.CHViews = Object.assign(window.CHViews || {}, { reduce });
})();
