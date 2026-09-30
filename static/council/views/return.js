// Council view: the quarterly WasteDataFlow fly-tipping return. Exposes CHViews.ret(el, ctx) -> cleanup.
(function () {
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const num = (n) => Number(n || 0).toLocaleString("en-GB");
  const SIZES = ["Single black bag", "Single item", "Car boot or less", "Small van load", "Transit van load", "Tipper lorry load", "Significant/multiple loads"];
  const SMALL = new Set(SIZES.slice(0, 3));
  const ACTIONS = [
    ["investigations", "Investigations"], ["warning_letters", "Warning letters"], ["statutory_notices", "Statutory notices"],
    ["fixed_penalty_notices", "Fixed penalty notices"], ["prosecutions", "Prosecutions"],
  ];

  function dueLabel(deadline, today) {
    const d = new Date(deadline + "T00:00:00Z");
    const t = today ? new Date(today + "T00:00:00Z") : new Date(new Date().toISOString().slice(0, 10) + "T00:00:00Z");
    const days = Math.round((d - t) / 864e5);
    const short = d.toLocaleDateString("en-GB", { day: "numeric", month: "long", timeZone: "UTC" });
    if (days < 0) return { text: `Overdue since ${short}`, days };
    return { text: `Due ${short}${days === 0 ? ", today" : days === 1 ? ", 1 day left" : ", " + days + " days left"}`, days };
  }

  // rows: [{label, n}]. keepOrder = ordinal data (sizes); otherwise sorted by count.
  function chart(title, rows, keepOrder, id) {
    const total = rows.reduce((a, r) => a + r.n, 0);
    const nz = rows.filter((r) => r.n > 0);
    const zero = rows.filter((r) => r.n <= 0);
    if (!keepOrder) nz.sort((a, b) => b.n - a.n);
    const max = Math.max(1, ...nz.map((r) => r.n));
    return `<section class="cv-card cv-chart">
      <div class="cv-chart-head"><h3>${esc(title)}</h3><span class="cv-chart-total">${num(total)}</span></div>
      <div class="cv-bars" role="table" aria-label="${esc(title)}">
        ${nz.map((r) => `<div class="cv-bar-row" role="row">
          <span class="cv-bar-label" role="cell">${esc(r.label)}</span>
          <span class="cv-bar-track" role="presentation"><span class="cv-bar" style="width:${(r.n / max * 100).toFixed(1)}%"></span></span>
          <span class="cv-bar-val" role="cell">${num(r.n)}</span>
        </div>`).join("")}
      </div>
      ${zero.length ? `<button type="button" class="cv-zero" aria-expanded="false" aria-controls="${id}-zero">Show ${zero.length} ${zero.length === 1 ? "category" : "categories"} with no incidents</button>
        <p class="cv-zero-list" id="${id}-zero" hidden>${zero.map((r) => esc(r.label)).join(" · ")}</p>` : ""}
    </section>`;
  }

  function render(r, today) {
    const total = r.total_incidents || 0;
    const sizeRows = SIZES.map((s) => { const v = (r.size || {})[s] || {}; const n = typeof v === "number" ? v : v.count || 0; return { label: s, n }; });
    const small = sizeRows.filter((x) => SMALL.has(x.label)).reduce((a, x) => a + x.n, 0);
    const sizedTotal = sizeRows.reduce((a, x) => a + x.n, 0) || total;
    const acts = r.actions || {};
    const enforcement = ACTIONS.slice(1).reduce((a, [k]) => a + (acts[k] || 0), 0);
    const checks = r.checks || [];
    const failed = checks.filter((c) => !c.ok);
    const due = dueLabel(r.deadline || "2026-10-25", today);
    // WasteDataFlow quarters run on the April–March financial year, so July–September is Q2.
    const period = [r.quarter_name || quarterName(r.quarter), r.quarter_label || r.period].filter(Boolean).join(" · ");
    const q = encodeURIComponent(r.quarter || "");
    return `<div class="cv cv-return">
      <header class="cv-ret-head">
        <div class="cv-ret-titles">
          <h2 class="cv-title">Fly-tipping return to DEFRA</h2>
          <p class="cv-ret-period">${esc([period, due.text].filter(Boolean).join(" · "))}</p>
        </div>
        <div class="cv-ret-cta">
          <a class="cv-btn cv-btn-primary cv-btn-lg" href="/api/return.csv${q ? "?quarter=" + q : ""}" download>
            <span aria-hidden="true">↓</span> Download for DEFRA (CSV)</a>
          <p class="cv-hint">Laid out to match the WasteDataFlow fly-tipping form.</p>
        </div>
      </header>
      ${failed.length ? `<div class="cv-checks is-warn" role="status">${failed.map((c) => `<span class="cv-check-main">✕ ${esc(c.text)}</span>`).join("")}</div>` : ""}

      <div class="cv-kpis">
        <div class="cv-card cv-kpi"><span class="cv-kpi-label">Incidents</span><span class="cv-kpi-num">${num(total)}</span><span class="cv-kpi-sub">This quarter</span></div>
        <div class="cv-card cv-kpi"><span class="cv-kpi-label">Car boot or less</span><span class="cv-kpi-num">${sizedTotal ? Math.round(small / sizedTotal * 100) : 0}<small>%</small></span><span class="cv-kpi-sub">${num(small)} of ${num(sizedTotal)} incidents</span></div>
        <div class="cv-card cv-kpi"><span class="cv-kpi-label">Enforcement actions</span><span class="cv-kpi-num">${num(enforcement)}</span><span class="cv-kpi-sub">Excludes ${num(acts.investigations)} ${acts.investigations === 1 ? "investigation" : "investigations"}</span></div>
      </div>

      <div class="cv-charts">
        ${chart("Land type", Object.entries(r.land_type || {}).map(([label, n]) => ({ label, n })), false, "cv-land")}
        ${chart("Waste type", Object.entries(r.waste_type || {}).map(([label, n]) => ({ label, n })), false, "cv-waste")}
        ${chart("Size", sizeRows, true, "cv-size")}
        <section class="cv-card cv-chart cv-actions">
          <div class="cv-chart-head"><h3>Actions</h3><span class="cv-chart-total">${num(ACTIONS.reduce((a, [k]) => a + (acts[k] || 0), 0))}</span></div>
          <table class="cv-table">
            <tbody>${ACTIONS.map(([k, label]) => `<tr${acts[k] ? "" : ' class="is-zero"'}><th scope="row">${label}</th><td>${num(acts[k])}</td></tr>`).join("")}</tbody>
          </table>
        </section>
      </div>
    </div>`;
  }

  const AUTHORITY = "Mersey Vale City Council";
  // "2026-Q2" -> "Q2 2026/27" (financial-year quarters, April start).
  function quarterName(id) {
    const m = /^(\d{4})-Q([1-4])$/.exec(id || ""); if (!m) return "";
    const y = Number(m[1]); return `Q${m[2]} ${y}/${String(y + 1).slice(2)}`;
  }

  function ret(el, ctx) {
    const { CH } = ctx;
    let dead = false;
    el.innerHTML = `<div class="cv cv-return"><p class="cv-loading">Loading the return…</p></div>`;
    (async () => {
      try {
        const cfg = await CH.get("/api/config").catch(() => null);
        const qid = (cfg && cfg.quarter && cfg.quarter.id) || "2026-Q2";
        const r = await CH.get(`/api/return?quarter=${qid}`);
        if (!r.deadline && cfg && cfg.quarter) r.deadline = cfg.quarter.deadline;
        if (!r.quarter_label && cfg && cfg.quarter && cfg.quarter.label) r.quarter_label = cfg.quarter.label;
        if (dead) return;
        el.innerHTML = render(r, cfg && cfg.today);
      } catch (e) {
        if (!dead) el.innerHTML = `<div class="cv"><p class="cv-error">The return could not be loaded (${esc(e.message)}).</p></div>`;
      }
    })();
    const onClick = (e) => {
      const b = e.target.closest(".cv-zero"); if (!b) return;
      const list = document.getElementById(b.getAttribute("aria-controls"));
      const open = b.getAttribute("aria-expanded") !== "true";
      b.setAttribute("aria-expanded", String(open));
      if (list) list.hidden = !open;
    };
    el.addEventListener("click", onClick);
    return () => { dead = true; el.removeEventListener("click", onClick); };
  }

  window.CHViews = Object.assign(window.CHViews || {}, { ret });
})();
