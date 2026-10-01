// The demo bar the Worker adds to every page of a visitor's copy: time left, the way between the residents' site and
// the council console, a QR code to carry on on a phone, and ending the session. It sits in a shadow root, so the
// app's styles and the bar's can't touch each other.
export const BAR_JS = `(() => {
  if (window.top !== window || document.getElementById("sorted-demo-bar")) return;
  const host = document.createElement("div");
  host.id = "sorted-demo-bar";
  document.body.appendChild(host);
  const root = host.attachShadow({ mode: "open" });
  const council = location.pathname.startsWith("/council");
  root.innerHTML = \`<style>
:host { all: initial; }
.wrap { position: fixed; left: 12px; bottom: calc(12px + env(safe-area-inset-bottom, 0px)); z-index: 2147483000; font: 14px/1.45 system-ui, -apple-system, "Segoe UI", sans-serif; color: #1d2327; }
.pill { display: inline-flex; align-items: center; gap: 8px; min-height: 36px; padding: 6px 14px 6px 10px; border: 0; border-radius: 999px; background: #1d2327; color: #fff; font: inherit; font-weight: 600; box-shadow: 0 2px 10px rgba(0,0,0,.25); cursor: pointer; }
.pill:focus-visible, a:focus-visible, button:focus-visible, summary:focus-visible { outline: 3px solid #3fb5b0; outline-offset: 2px; }
.dot { width: 9px; height: 9px; border-radius: 50%; background: #3fb5b0; }
.panel { position: absolute; left: 0; bottom: 46px; width: min(300px, calc(100vw - 24px)); max-height: calc(100vh - 80px); overflow: auto; padding: 14px; border-radius: 14px; background: #fff; border: 1px solid #dde1e4; box-shadow: 0 8px 28px rgba(0,0,0,.22); }
.panel[hidden] { display: none; }
.h { margin: 0 0 10px; font-weight: 700; }
nav { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; margin-bottom: 10px; }
nav a { display: block; padding: 8px 10px; border-radius: 10px; border: 1px solid #dde1e4; color: #1d2327; text-align: center; text-decoration: none; font-weight: 600; }
nav a[aria-current="page"] { background: #e3f3f2; border-color: #0b6e6e; color: #0b6e6e; }
details { margin: 0 0 10px; }
summary { cursor: pointer; font-weight: 600; color: #0b6e6e; }
details img { display: block; margin: 10px 0 6px; width: 148px; height: 148px; image-rendering: pixelated; }
p { margin: 0 0 8px; }
.small { font-size: 12px; color: #5b6670; }
.small a { color: #0b6e6e; }
form { margin: 0 0 10px; }
.end { width: 100%; padding: 8px 10px; border-radius: 10px; border: 1px solid #c9302c; background: #fff; color: #a52622; font: inherit; font-weight: 600; cursor: pointer; }
</style>
<div class="wrap">
  <div class="panel" id="panel" hidden>
    <p class="h">Your copy of the Sorted demo</p>
    <nav aria-label="Demo">
      <a href="/"\${council ? "" : ' aria-current="page"'}>Residents' site</a>
      <a href="/council"\${council ? ' aria-current="page"' : ""}>Council console</a>
    </nav>
    <details>
      <summary>Carry on on your phone</summary>
      <img id="qr" alt="QR code that opens this copy of the demo on a phone">
      <p class="small">Scan it to report from your phone and watch the report arrive in the council console.</p>
    </details>
    <form method="post" action="/__demo/end"><button class="end" type="submit">End now and delete my copy</button></form>
    <p class="small">Your copy, and any photos in it, are deleted when the session ends. This is a demonstration, not a council service: to report fly-tipping, go to <a href="https://www.gov.uk/report-flytipping" target="_blank" rel="noopener">gov.uk/report-flytipping</a>.</p>
  </div>
  <button class="pill" id="pill" type="button" aria-expanded="false" aria-controls="panel"><span class="dot" aria-hidden="true"></span><span id="left">Demo</span></button>
</div>\`;
  const $ = (id) => root.getElementById(id);
  const narrow = window.matchMedia("(max-width: 520px)");
  $("pill").addEventListener("click", () => {
    const open = $("panel").hidden;
    $("panel").hidden = !open;
    $("pill").setAttribute("aria-expanded", String(open));
  });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !$("panel").hidden) { $("panel").hidden = true; $("pill").setAttribute("aria-expanded", "false"); } });
  fetch("/__demo/session", { cache: "no-store" }).then((r) => r.json()).then((s) => {
    $("qr").src = "/api/qr?text=" + encodeURIComponent(s.join);
    const tick = () => {
      const ms = s.expires - Date.now();
      if (ms <= 0) { location.reload(); return; }
      const m = Math.ceil(ms / 60000);
      const full = "Demo: " + m + (m === 1 ? " minute" : " minutes") + " left";
      // On a phone the short form keeps clear of the map's OpenStreetMap credit.
      $("left").textContent = narrow.matches ? m + " min" : full;
      $("pill").setAttribute("aria-label", full + ". Open the demo menu.");
    };
    tick();
    setInterval(tick, 15000);
    narrow.addEventListener("change", tick);
  }).catch(() => {});
})();
`;
