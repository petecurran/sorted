// Stage rebrand. Applies window.CH_BRAND (served from content/brand.json by /api/brand.js) to the page: the brand
// colours, a logo drawn with the new name, and every visible "Mersey Vale" and "MVCC-" rewritten, including cards the
// page renders later. Stored data keeps the baseline names; only what is shown changes. Load in <head>, straight
// after /api/brand.js. window.CH_BRAND_CHECK() reports what was applied, for checking the page after an edit.
(function () {
  const BASE = { council_name: "Mersey Vale City Council", place: "Mersey Vale", case_prefix: "MVCC", colour: "#4E2681", accent: "#FFC71F" };
  const B = Object.assign({}, BASE, window.CH_BRAND || {});
  const root = document.documentElement;
  const same = (a, b) => String(a || "").trim().toLowerCase() === String(b || "").trim().toLowerCase();

  // ---- colours: the stylesheets use these variables throughout ----
  if (!same(B.colour, BASE.colour)) {
    root.style.setProperty("--brand", B.colour);
    root.style.setProperty("--brand-soft", `color-mix(in srgb, ${B.colour} 12%, #fff)`);
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute("content", B.colour);
  }
  if (!same(B.accent, BASE.accent)) root.style.setProperty("--tape", B.accent);

  function luminance(hex) {
    const m = /^#?([0-9a-f]{6})$/i.exec(String(hex).trim());
    if (!m) return null;
    const [r, g, b] = [0, 2, 4].map((i) => parseInt(m[1].slice(i, i + 2), 16) / 255)
      .map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
    return 0.2126 * r + 0.7152 * g + 0.0722 * b;
  }
  const L = luminance(B.colour);
  const whiteContrast = L == null ? null : Math.round((1.05 / (L + 0.05)) * 10) / 10;
  if (whiteContrast != null && whiteContrast < 4.5) {
    console.warn(`brand.json: white text on ${B.colour} has contrast ${whiteContrast}:1 (needs 4.5:1). Choose a darker colour.`);
  }

  // ---- logo: the crest (the standard gull, or brand.json "mark") beside the council's name ----
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  function logoLines() {
    const name = B.council_name.trim(), place = B.place.trim();
    if (place && name.startsWith(place) && name.length > place.length) return [place, name.slice(place.length).trim()];
    const words = name.split(/\s+/);
    if (words.length < 2) return [name, ""];
    let best = 1;
    for (let i = 1; i < words.length; i++) {
      const d = Math.abs(words.slice(0, i).join(" ").length - words.slice(i).join(" ").length);
      if (d < Math.abs(words.slice(0, best).join(" ").length - words.slice(best).join(" ").length)) best = i;
    }
    return [words.slice(0, best).join(" "), words.slice(best).join(" ")];
  }
  function drawLogo(white) {
    const [l1, l2] = logoLines();
    const room = 178; // viewBox units to the right of the mark
    const fs1 = Math.min(27, room / (0.5 * Math.max(l1.length, 1)));
    const fs2 = Math.min(19, room / (0.56 * Math.max(l2.length, 1)));
    const ink1 = white ? "#ffffff" : B.colour, ink2 = white ? "#ffffff" : "#202427";
    const w1 = white ? "#ffffff" : B.colour, w2 = white ? "#ffffff" : "#005DA7";
    const gull = `<g fill="none" stroke-linecap="round" stroke-linejoin="round">` +
      `<path d="M8 26 C 16 16, 24 16, 30 24 C 36 16, 44 16, 52 26" stroke="${w1}" stroke-width="5"/>` +
      `<path d="M6 42 C 14 36, 22 36, 30 42 S 46 48, 54 42" stroke="${w2}" stroke-width="4"/>` +
      `<path d="M6 53 C 14 47, 22 47, 30 53 S 46 59, 54 53" stroke="${w2}" stroke-width="4" opacity="${white ? ".7" : ".55"}"/></g>`;
    const text = l2
      ? `<text x="68" y="29" font-family="'Barlow Semi Condensed','Arial Narrow',sans-serif" font-weight="700" font-size="${fs1.toFixed(1)}" fill="${ink1}" letter-spacing=".3">${esc(l1)}</text>` +
        `<text x="68" y="54" font-family="'IBM Plex Sans',system-ui,sans-serif" font-weight="500" font-size="${fs2.toFixed(1)}" fill="${ink2}">${esc(l2)}</text>`
      : `<text x="68" y="${(32 + fs1 / 3).toFixed(1)}" font-family="'Barlow Semi Condensed','Arial Narrow',sans-serif" font-weight="700" font-size="${fs1.toFixed(1)}" fill="${ink1}" letter-spacing=".3">${esc(l1)}</text>`;
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 250 64" role="img" aria-label="${esc(B.council_name)} (fictional)">` +
      `${markSvg(white ? "#ffffff" : B.colour) || gull}${text}</svg>`;
    return "data:image/svg+xml;charset=utf-8," + encodeURIComponent(svg);
  }
  // A crest from brand.json "mark" (inlined by the server as mark_svg), fitted into the 60 x 60 box left of the name.
  function markSvg(colour) {
    const src = String(B.mark_svg || "").replace(/<\?xml[\s\S]*?\?>|<!DOCTYPE[\s\S]*?>|<!--[\s\S]*?-->/gi, "").trim();
    const open = /^<svg\b[^>]*>/i.exec(src);
    if (!open) return "";
    const attrs = open[0].replace(/\s(?:x|y|width|height|color|style)\s*=\s*("[^"]*"|'[^']*')/gi, "");
    return attrs.replace(/^<svg/i, `<svg x="0" y="2" width="60" height="60" color="${colour}"`) + src.slice(open[0].length);
  }
  const renamed = !same(B.council_name, BASE.council_name) || !same(B.place, BASE.place) || !!B.mark_svg;
  const logoWhite = renamed ? drawLogo(true) : null;
  const logoColour = renamed ? drawLogo(false) : null;
  function swapLogos(scope) {
    if (!logoWhite) return;
    scope.querySelectorAll('img[src*="mvcc-logo-white"]').forEach((img) => { img.src = logoWhite; });
    scope.querySelectorAll('img[src*="mvcc-logo-colour"]').forEach((img) => { img.src = logoColour; });
    scope.querySelectorAll('link[rel="icon"][href*="mvcc-logo"]').forEach((l) => { l.href = logoColour; });
  }

  // ---- words: rewrite what is shown, in one pass so a replacement is never replaced again ----
  const slug = (s) => s.trim().toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
  const MAP = { "Mersey Vale City Council": B.council_name.trim(), "Mersey Vale": B.place.trim(), "MVCC": B.case_prefix.trim(), "mersey-vale": slug(B.place) };
  const RX = /Mersey Vale City Council|Mersey Vale|MVCC(?=[-_])|mersey-vale/g;
  const reuses = Object.entries(MAP).some(([k, v]) => v !== k && /Mersey Vale|MVCC|mersey-vale/.test(v));
  const rewriting = !reuses && Object.keys(MAP).some((k) => MAP[k] !== k);
  if (reuses) console.warn("brand.json: the new name reuses 'Mersey Vale' or 'MVCC', so names are left unchanged.");
  const fix = (s) => s.replace(RX, (m) => MAP[m]);
  const SKIP = new Set(["SCRIPT", "STYLE", "OPTION", "SELECT", "TEXTAREA", "NOSCRIPT"]);
  const ATTRS = ["alt", "title", "aria-label", "placeholder"];

  function fixText(node) {
    const p = node.parentNode;
    if (!p || SKIP.has(p.nodeName)) return;
    const v = node.nodeValue;
    if (v && v.search(RX) !== -1) { const n = fix(v); if (n !== v) node.nodeValue = n; }
  }
  function fixAttrs(el) {
    for (const a of ATTRS) {
      const v = el.getAttribute && el.getAttribute(a);
      if (v && v.search(RX) !== -1) el.setAttribute(a, fix(v));
    }
  }
  function sweep(scope) {
    if (scope.nodeType === 3) { fixText(scope); return; }
    if (scope.nodeType !== 1 && scope.nodeType !== 9) return;
    if (scope.nodeType === 1) { if (SKIP.has(scope.nodeName)) return; fixAttrs(scope); }
    const tw = document.createTreeWalker(scope, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT);
    for (let n = tw.nextNode(); n; n = tw.nextNode()) {
      if (n.nodeType === 3) fixText(n);
      else fixAttrs(n);
    }
  }
  function sweepAll() {
    if (rewriting) {
      document.title = fix(document.title);
      document.querySelectorAll('meta[name="description"]').forEach((m) => m.setAttribute("content", fix(m.getAttribute("content") || "")));
      sweep(document.body || root);
      const email = document.getElementById("si-email");
      if (email && email.value.search(RX) !== -1) email.value = fix(email.value);
    }
    swapLogos(document);
  }

  if (rewriting || logoWhite) {
    new MutationObserver((records) => {
      for (const r of records) {
        if (r.type === "characterData") { if (rewriting) fixText(r.target); continue; }
        if (r.type === "attributes") { if (rewriting) fixAttrs(r.target); if (r.attributeName === "src" && logoWhite) swapLogos(r.target.parentNode || document); continue; }
        r.addedNodes.forEach((n) => {
          if (rewriting) sweep(n);
          if (n.nodeType === 1 && logoWhite) { if (n.matches('img[src*="mvcc-logo"]')) swapLogos(n.parentNode); else swapLogos(n); }
        });
      }
    }).observe(root, { childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: ATTRS.concat(["src"]) });
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", sweepAll);
    else sweepAll();
  }

  window.CH_BRAND_CHECK = () => {
    const left = [];
    if (rewriting) {
      const tw = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
      for (let n = tw.nextNode(); n; n = tw.nextNode()) {
        if (n.parentNode && !SKIP.has(n.parentNode.nodeName) && n.nodeValue.search(RX) !== -1) left.push(n.nodeValue.trim().slice(0, 80));
      }
    }
    const logos = [...document.querySelectorAll("img.cc-logo, img.wm-logo")].map((i) => (i.src.startsWith("data:") ? "drawn" : i.getAttribute("src")));
    return { brand: Object.assign({}, B, { mark_svg: B.mark_svg ? "(inlined)" : "" }), white_text_contrast: whiteContrast, names_rewritten: rewriting, old_names_still_shown: left, logos };
  };
})();
