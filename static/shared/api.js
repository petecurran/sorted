// Shared API helper and status vocabulary.
// Set window.CH_MOCK = true (or add ?mock=1 to the URL) to read mock JSON from window.CH_MOCK_BASE (default /static/mock).
// Mock file name = API path without /api/, with ?=&/ turned into _ (e.g. /api/incidents?view=public -> incidents_view_public.json).
(function () {
  const MOCK = window.CH_MOCK || new URLSearchParams(location.search).has("mock");

  async function get(path) {
    if (MOCK) {
      const name = path.replace(/^\/api\//, "").replace(/[?=&/]/g, "_").replace(/_+$/, "");
      const base = window.CH_MOCK_BASE || "/static/mock";
      const r = await fetch(`${base}/${name}.json`);
      if (!r.ok) throw new Error(`mock missing: ${name}.json`);
      return r.json();
    }
    const r = await fetch(path, { headers: { Accept: "application/json" } });
    if (!r.ok) throw new Error(`${r.status} ${path}`);
    return r.json();
  }

  async function post(path, body) {
    const opts = { method: "POST" };
    if (body instanceof FormData) opts.body = body;
    else { opts.body = JSON.stringify(body || {}); opts.headers = { "Content-Type": "application/json" }; }
    const r = await fetch(path, opts);
    const data = await r.json().catch(() => ({}));
    if (!r.ok) { const e = new Error(data.error || `${r.status}`); e.status = r.status; e.data = data; throw e; }
    return data;
  }

  // The one status vocabulary. Key = decision or status; value = [label, css class].
  const STATUS = {
    triaging: ["Checking…", "triaging"],
    clear_now: ["Crew today", "clear_now"],
    hold_for_officer: ["Officer to inspect", "hold_for_officer"],
    specialist: ["Specialist removal", "specialist"],
    review: ["Needs review", "review"],
    not_a_fly_tip: ["Not fly-tipping", "not_fly_tip"],
    not_fly_tip: ["Not fly-tipping", "not_fly_tip"],
    scheduled: ["Crew booked", "clear_now"],
    held: ["Officer to inspect", "hold_for_officer"],
    cleared: ["Cleared", "cleared"],
    forwarded: ["Passed on", "further_inspection"],
  };

  // Which status to show for an incident: cleared/not_fly_tip/triaging win; otherwise the triage decision.
  function statusKey(inc) {
    if (!inc) return "triaging";
    if (inc.status === "cleared") return "cleared";
    if (inc.status === "not_fly_tip") return "not_fly_tip";
    if (inc.status === "forwarded") return "forwarded";
    if (inc.status === "triaging" || !inc.triage) return "triaging";
    if (inc.status === "scheduled") return "scheduled";
    return inc.triage.decision || "review";
  }

  // Public-facing status language (never reveals officer visits). Uses inc.public_status from the API.
  const PUBLIC_STATUS = {
    new_report: ["New report", "new_report"],
    crew_booked: ["Crew booked", "crew_booked"],
    further_inspection: ["Further inspection", "further_inspection"],
    passed_on: ["Passed to landowner", "further_inspection"],
    closed: ["Closed", "not_fly_tip"],
    cleared: ["Cleared", "cleared"],
  };
  function publicPill(inc) {
    const [label, cls] = PUBLIC_STATUS[(inc && inc.public_status) || "new_report"] || PUBLIC_STATUS.new_report;
    return `<span class="pill ${cls}">${label}</span>`;
  }

  function pill(inc) {
    const [label, cls] = STATUS[statusKey(inc)] || STATUS.review;
    return `<span class="pill ${cls}">${label}</span>`;
  }

  window.CH = { get, post, STATUS, statusKey, pill, PUBLIC_STATUS, publicPill, MOCK };
})();
