"""Check the rebrand on every page, at desktop and phone sizes, and make a contact sheet of screenshots.

    uv run --with playwright python scripts/brand_check.py                  # the brand in content/brand.json
    uv run --with playwright python scripts/brand_check.py --show           # the same, with the browsers visible
    uv run --with playwright python scripts/brand_check.py --try try.json   # preview a brand without saving it

Uses the installed Google Chrome, in its own profile, so the stage screens are not touched. Screenshots and the
contact sheet go to data/brand_check/, which the app serves at http://localhost:8800/dev/brand-check/.
A view fails if it still shows the old name, the logo does not load, white text on the brand colour is below 4.5:1,
the page logs an error, or the page is wider than the screen. Exits 1 if any view fails.
"""

from __future__ import annotations

import argparse
import asyncio
import html
import json
import re
import sys
import time
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))
from common import brand, brand_script  # noqa: E402

OUT = APP / "data" / "brand_check"
OLD = re.compile(r"Mersey Vale|MVCC-|mersey-vale")
STAFF = {"email": "john.smith@mersey-vale.example", "name": "John Smith", "at": "2026-09-28T09:00:00Z"}

SIZES = {
    "desktop": {"viewport": {"width": 1280, "height": 800}},
    "phone": {
        "viewport": {"width": 390, "height": 844},
        "device_scale_factor": 2,
        "is_mobile": True,
        "has_touch": True,
    },
}
# (site, view, path, what to open first, signed in, sizes)
VIEWS = [
    ("Public", "Map", "/", None, False, ("desktop", "phone")),
    ("Public", "Report", "/", "#report-btn", False, ("desktop", "phone")),
    ("Public", "Find your area", "/", "#find-area", False, ("desktop", "phone")),
    ("Public", "Incident", "/", "marker", False, ("desktop", "phone")),
    ("Council", "Sign in", "/council", None, False, ("desktop", "phone")),
    ("Council", "Queue", "/council#queue", None, True, ("desktop", "phone")),
    ("Council", "Triage card", "/council#queue", "#q-list .q-item", True, ("phone",)),
    ("Council", "Map", "/council#map", None, True, ("desktop", "phone")),
    ("Council", "Routes", "/council#routes", None, True, ("desktop", "phone")),
    ("Council", "Return", "/council#return", None, True, ("desktop", "phone")),
    ("Council", "Reduce", "/council#reduce", None, True, ("desktop", "phone")),
]

PROBE = """() => {
  const c = window.CH_BRAND_CHECK ? window.CH_BRAND_CHECK() : null;
  const logos = [...document.querySelectorAll("img.cc-logo, img.wm-logo")].filter((i) => i.offsetParent !== null);
  return {
    check: c,
    logos: logos.length,
    broken_logos: logos.filter((i) => !i.complete || i.naturalWidth === 0).length,
    overflow: document.documentElement.scrollWidth - window.innerWidth,
  };
}"""


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


async def open_marker(page) -> bool:
    """Click the first incident marker that is on screen (off-screen ones cannot be clicked)."""
    pt = await page.evaluate("""() => {
      for (const m of document.querySelectorAll(".mk")) {
        const r = m.getBoundingClientRect();
        if (r.width && r.top > 70 && r.bottom < innerHeight - 160 && r.left > 0 && r.right < innerWidth) return [r.x + r.width / 2, r.y + r.height / 2];
      }
      return null;
    }""")
    if not pt:
        return False
    await page.mouse.click(*pt)
    return True


async def run_size(browser, size: str, base: str, payload: str | None, problems: list, rows: list, brand_wide: set):
    opts = SIZES[size]
    ctx_out = await browser.new_context(**opts)
    ctx_in = await browser.new_context(**opts)
    await ctx_in.add_init_script(f"localStorage.setItem('mvcc_ft_staff', {json.dumps(json.dumps(STAFF))});")
    if payload is not None:
        for ctx in (ctx_out, ctx_in):
            await ctx.route(
                "**/api/brand.js", lambda r: r.fulfill(status=200, content_type="text/javascript", body=payload)
            )
    for site, view, path, opener, signed_in, sizes in VIEWS:
        if size not in sizes:
            continue
        page = await (ctx_in if signed_in else ctx_out).new_page()
        errors: list[str] = []

        def on_console(m, errors=errors):
            url = (m.location or {}).get("url", "")
            if m.type == "error" and ("favicon.ico" in url or not url.startswith(base)):
                return  # map tiles or fonts offline, or the council page's missing favicon: not ours
            if m.text.startswith("brand.json"):
                brand_wide.add(m.text[:200])  # the same on every page: reported once
            elif m.type == "error":
                errors.append(m.text[:160])

        page.on("console", on_console)
        page.on("pageerror", lambda e, errors=errors: errors.append(f"script error: {str(e)[:160]}"))
        name = f"{size}-{slug(site)}-{slug(view)}"
        t_view = time.time()
        issues: list[str] = []
        try:
            # Map tiles and fonts come from the internet and can be slow on conference wifi, so don't wait for them.
            await page.goto(base + path, wait_until="domcontentloaded", timeout=15000)
            await page.wait_for_timeout(1800)
            if opener == "marker":
                if not await open_marker(page):
                    issues.append("no incident marker on screen to open")
            elif opener:
                await page.locator(opener).first.click(timeout=4000)
            if opener:
                await page.wait_for_timeout(900)
            p = await page.evaluate(PROBE)
            title = await page.title()
            await page.screenshot(path=str(OUT / f"{name}.png"))
        except Exception as e:  # a view that will not open is itself a finding
            issues.append(f"could not open: {str(e).splitlines()[0][:140]}")
            p, title = {"check": None, "logos": 0, "broken_logos": 0, "overflow": 0}, ""
        c = p["check"] or {}
        renamed = c.get("names_rewritten")
        if p["check"] is None and not issues:
            issues.append("brand script not running on this page")
        if renamed and c.get("old_names_still_shown"):
            issues.append("old name still shown: " + "; ".join(c["old_names_still_shown"][:3]))
        if renamed and OLD.search(title):
            issues.append(f"old name in page title: {title}")
        if p["logos"] == 0 and not issues:
            issues.append("no logo visible")
        if p["broken_logos"]:
            issues.append(f"{p['broken_logos']} logo(s) did not load")
        if p["overflow"] > 1:
            issues.append(f"page is {p['overflow']}px wider than the screen")
        issues += errors
        rows.append({"size": size, "site": site, "view": view, "file": f"{name}.png", "issues": issues})
        problems += [f"{size} · {site} · {view}: {i}" for i in issues]
        print(
            f"  {'FAIL' if issues else 'ok  '}  {size:<7} {site:<8} {view:<15} {time.time() - t_view:4.1f} s"
            + (f"  ({issues[0]})" if issues else "")
        )
        await page.close()
    await ctx_out.close()
    await ctx_in.close()


def contact_sheet(b: dict, rows: list, problems: list, seconds: float, csv_note: str) -> str:
    colour = html.escape(b["colour"])
    head = f"{len(rows)} views checked in {seconds:.0f} s. " + (
        "No problems found." if not problems else f"{len(problems)} problem(s) found."
    )

    def card(r):
        bad = "".join(f"<li>{html.escape(i)}</li>" for i in r["issues"])
        return (
            f'<figure class="{"bad" if r["issues"] else "ok"} {r["size"]}"><a href="{r["file"]}"><img src="{r["file"]}" alt="" loading="lazy"></a>'
            f"<figcaption><b>{html.escape(r['site'])} · {html.escape(r['view'])}</b>"
            f'<span class="tag">{"Check" if r["issues"] else "Pass"}</span>{f"<ul>{bad}</ul>" if bad else ""}</figcaption></figure>'
        )

    sections = "".join(
        f"<h2>{label}</h2><div class='grid {size}'>{''.join(card(r) for r in rows if r['size'] == size)}</div>"
        for size, label in (("desktop", "Desktop, 1280 × 800"), ("phone", "Phone, 390 × 844"))
    )
    return f"""<!doctype html><html lang="en-GB"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Brand check · {html.escape(b["council_name"])}</title>
<style>
  :root {{ --brand: {colour}; --ink: #202427; --ink-3: #6C757D; --paper: #F4F4F5; --line: #E1E2E3; --bad: #9E2131; --ok: #0B4F17; }}
  body {{ margin: 0; background: var(--paper); color: var(--ink); font: 15px/1.45 "IBM Plex Sans", system-ui, sans-serif; }}
  header {{ background: var(--brand); color: #fff; padding: 18px 24px; }}
  header h1 {{ margin: 0 0 4px; font: 700 26px/1.1 "Barlow Semi Condensed", "Arial Narrow", sans-serif; }}
  header p {{ margin: 0; opacity: .92; }}
  main {{ padding: 8px 24px 40px; max-width: 1500px; }}
  h2 {{ font: 700 20px/1.2 "Barlow Semi Condensed", "Arial Narrow", sans-serif; margin: 24px 0 10px; }}
  .problems {{ background: #fff; border-left: 4px solid var(--bad); padding: 10px 16px; margin-top: 16px; }}
  .grid {{ display: grid; gap: 14px; }}
  .grid.desktop {{ grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); }}
  .grid.phone {{ grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); }}
  figure {{ margin: 0; background: #fff; border: 1px solid var(--line); border-radius: 10px; overflow: hidden; }}
  figure.bad {{ border: 2px solid var(--bad); }}
  figure img {{ display: block; width: 100%; height: auto; border-bottom: 1px solid var(--line); }}
  figcaption {{ padding: 8px 10px; font-size: 13px; display: flex; flex-wrap: wrap; gap: 6px; align-items: center; justify-content: space-between; }}
  figcaption ul {{ flex-basis: 100%; margin: 4px 0 0; padding-left: 16px; color: var(--bad); }}
  .tag {{ font: 600 11px/1 ui-monospace, Menlo, monospace; text-transform: uppercase; letter-spacing: .06em; padding: 3px 6px; border-radius: 4px; color: #fff; background: var(--ok); }}
  .bad .tag {{ background: var(--bad); }}
  @media (max-width: 600px) {{ main {{ padding: 8px 16px 32px; }} header {{ padding: 16px; }} }}
</style></head><body>
<header><h1>Brand check: {html.escape(b["council_name"])}</h1>
<p>{html.escape(head)} Case references {html.escape(b["case_prefix"])}-FT-2026. Colour {colour}, accent {html.escape(b["accent"])}. {html.escape(csv_note)}</p></header>
<main>{"<div class='problems'><b>Problems</b><ul>" + "".join(f"<li>{html.escape(p)}</li>" for p in problems) + "</ul></div>" if problems else ""}
{sections}</main></body></html>"""


async def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--show", action="store_true", help="show the browsers while checking")
    ap.add_argument(
        "--try", dest="try_file", help="a JSON file of brand fields to preview instead of content/brand.json"
    )
    ap.add_argument("--base", default="http://localhost:8800")
    a = ap.parse_args()

    from playwright.async_api import async_playwright

    b = brand()
    payload = None
    if a.try_file:
        b = {**b, **{k: v for k, v in json.loads(Path(a.try_file).read_text()).items() if k in b}}
        payload = brand_script(b)
    OUT.mkdir(parents=True, exist_ok=True)
    for f in OUT.glob("*.png"):
        f.unlink()
    print(f"Checking {b['council_name']} ({'preview' if payload else 'live'}) at {a.base}")
    t0 = time.time()
    problems: list[str] = []
    rows: list[dict] = []
    brand_wide: set[str] = set()
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel="chrome", headless=not a.show)
        await asyncio.gather(*(run_size(browser, s, a.base, payload, problems, rows, brand_wide) for s in SIZES))
        problems[:0] = sorted(brand_wide)
        csv_note = ""
        if payload is None:
            ctx = await browser.new_context()
            r = await ctx.request.get(a.base + "/api/return.csv")
            body, disp = await r.text(), r.headers.get("content-disposition", "")
            renamed = b["council_name"] != "Mersey Vale City Council"
            if renamed and (OLD.search(body) or "MVCC" in disp):
                problems.append("DEFRA CSV export still names the old council (restart the server?)")
                csv_note = "The DEFRA CSV export still uses the old name."
            else:
                csv_note = f"DEFRA CSV export: {disp.split('filename=')[-1].strip(chr(34))}."
            await ctx.close()
        await browser.close()
    order = {(s, v[0], v[1]): i for i, v in enumerate(VIEWS) for s in SIZES}
    rows.sort(key=lambda r: order[(r["size"], r["site"], r["view"])])
    seconds = time.time() - t0
    (OUT / "index.html").write_text(contact_sheet(b, rows, problems, seconds, csv_note))
    (OUT / "summary.json").write_text(
        json.dumps(
            {"brand": {k: v for k, v in b.items() if k != "mark_svg"}, "views": rows, "problems": problems}, indent=1
        )
    )
    print(
        f"\n{len(rows)} views in {seconds:.0f} s: "
        + ("no problems." if not problems else f"{len(problems)} problem(s):")
    )
    for pr in problems:
        print(f"  - {pr}")
    print(f"Contact sheet: {a.base}/dev/brand-check/")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
