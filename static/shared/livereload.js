// Live reload for the stage screen. Open any page with ?live=1 (remembered for this tab) and it reloads
// itself within about a second of any saved change to the front end or content files. ?live=0 turns it off.
(function () {
  const q = new URLSearchParams(location.search);
  try {
    if (q.get("live") === "1") sessionStorage.setItem("ch_live", "1");
    if (q.get("live") === "0") sessionStorage.removeItem("ch_live");
    if (sessionStorage.getItem("ch_live") !== "1") return;
  } catch (e) {
    if (q.get("live") !== "1") return;
  }
  let seen = null;
  async function tick() {
    try {
      const r = await fetch("/api/dev/version", { cache: "no-store" });
      const { v } = await r.json();
      if (seen && v !== seen) { location.reload(); return; }
      seen = v;
    } catch (e) { /* server restarting: keep trying */ }
    setTimeout(tick, 800);
  }
  tick();
})();
