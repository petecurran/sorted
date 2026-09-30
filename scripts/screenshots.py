"""Take the README's screenshots from a running copy with fresh data, and write them to docs/screenshots/.

    FT_RESET=1 FT_PORT=8811 FT_CLASSIFIER=cache scripts/start_server.sh
    uv run --with playwright python scripts/screenshots.py --base http://localhost:8811

It reports two demo kit photos from a phone, uploads the other three from the laptop, books and holds a few jobs so
the routes have stops, and photographs each part of the app. It rebrands to the example Humpington Council for a
minute (content/brand.json) and always puts the original back. Uses the installed Google Chrome. Start from fresh
data each time: the script changes it.
"""

from __future__ import annotations

import argparse
import io
import json
import subprocess
import sys
import time
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

APP = Path(__file__).resolve().parents[1]
OUT = APP / "docs" / "screenshots"
KIT = APP / "seed" / "live_demo"
STAFF = {"email": "john.smith@mersey-vale.example", "name": "John Smith", "at": "2026-01-01T09:00:00Z"}
DESKTOP = {"viewport": {"width": 1280, "height": 860}}
PHONE = {"viewport": {"width": 390, "height": 844}, "device_scale_factor": 2, "is_mobile": True, "has_touch": True}
HUMPINGTON = {
    "council_name": "Humpington Council",
    "place": "Humpington",
    "case_prefix": "HC",
    "colour": "#D81B60",
    "accent": "#FFC71F",
    "mark": "humpington-pirate.svg",
}


def save(page, name: str, full: bool = False):
    im = Image.open(io.BytesIO(page.screenshot(full_page=full))).convert("RGB")
    im.save(OUT / f"{name}.jpg", "JPEG", quality=82, optimize=True)
    print(f"  {name}.jpg  {im.width}x{im.height}")


def settle(page, ms: int = 1800):
    page.wait_for_timeout(ms)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base", default="http://localhost:8800")
    a = ap.parse_args()
    base = a.base.rstrip("/")
    OUT.mkdir(parents=True, exist_ok=True)
    for f in OUT.glob("*.jpg"):
        f.unlink()

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome")
        desk = browser.new_context(**DESKTOP)
        council_ctx = browser.new_context(**DESKTOP)
        council_ctx.add_init_script(f"localStorage.setItem('mvcc_ft_staff', {json.dumps(json.dumps(STAFF))});")
        phone = browser.new_context(**PHONE)
        api = council_ctx.request

        def incidents():
            return api.get(f"{base}/api/incidents?view=council").json()

        def find(street=None, pred=None):
            for i in sorted(incidents(), key=lambda i: -i["id"]):
                if (street and i["street"] == street) or (pred and pred(i)):
                    return i
            raise SystemExit(f"no incident found for {street or 'the test'}")

        def open_card(page, iid, tab="action"):
            page.goto(f"{base}/council#queue", wait_until="domcontentloaded")
            settle(page)
            page.click(f'#q-tabs [data-qt="{tab}"]')
            settle(page, 600)
            page.click(f'#q-list .q-item[data-id="{iid}"]')
            settle(page, 1500)

        def phone_report(photo: Path, shots: tuple[str, str], same: bool = False):
            pg = phone.new_page()
            pg.goto(base + "/", wait_until="domcontentloaded")
            settle(pg)
            pg.click("#report-btn")
            settle(pg, 600)
            pg.set_input_files("#rf-library", str(photo))
            pg.wait_for_selector(".locbanner.is-photo", timeout=8000)
            settle(pg, 1500)
            if not same:
                save(pg, shots[0])
            pg.click("#rf-next")
            settle(pg, 1200)
            if same:
                pg.wait_for_selector("#same-yes", timeout=8000)
                save(pg, shots[0])
                pg.click("#same-yes")
            else:
                pg.click("#rf-next")
            pg.wait_for_selector("#rf-done", state="visible", timeout=15000)
            settle(pg, 5000)  # the cached reading lands after about three seconds
            save(pg, shots[1])
            pg.close()

        print("public site")
        pg = desk.new_page()
        pg.goto(base + "/", wait_until="domcontentloaded")
        settle(pg, 2500)
        save(pg, "public-map")
        pm = phone.new_page()
        pm.goto(base + "/", wait_until="domcontentloaded")
        settle(pm, 2500)
        save(pm, "phone-map")

        print("council queue")
        cq = council_ctx.new_page()
        cq.goto(f"{base}/council#queue", wait_until="domcontentloaded")
        settle(cq, 2500)
        save(cq, "council-queue")

        print("reporting from a phone (photo 4, Makin Street)")
        phone_report(KIT / "4_mattress_makin_street.jpg", ("phone-report-location", "phone-report-done"))

        print("the laptop reports photos 1 to 3")
        for f in ("1_black_bags_jubilee_drive.jpg", "2_fridge_lawrence_road.jpg", "3_paint_tins_oglet_lane.jpg"):
            api.post(
                f"{base}/api/reports",
                multipart={"photo": {"name": f, "mimeType": "image/jpeg", "buffer": (KIT / f).read_bytes()}},
            )
        time.sleep(5)

        print("council cards")
        open_card(cq, find("Makin Street")["id"])
        save(cq, "council-card")
        open_card(cq, find("Oglet Lane")["id"])
        save(cq, "council-hazard")
        open_card(cq, find("Lawrence Road")["id"], tab="done")
        save(cq, "council-bulky")
        rail = find(pred=lambda i: i.get("forward_to") == "Network Rail" and i["status"] == "triaged")
        open_card(cq, rail["id"])
        save(cq, "council-network-rail")

        print("a second report of the same thing (photo 5, Belmont Road)")
        phone_report(KIT / "5_optional_merge_belmont_road.jpg", ("phone-same", "phone-merged"), same=True)

        print("a resident's view of a report")
        pm.goto(base + "/", wait_until="domcontentloaded")
        settle(pm, 2500)
        pt = pm.evaluate("""() => { for (const m of document.querySelectorAll('.mk')) { const r = m.getBoundingClientRect();
            if (r.width && r.top > 90 && r.bottom < innerHeight - 180 && r.left > 20 && r.right < innerWidth - 20) return [r.x + r.width / 2, r.y + r.height / 2]; } return null; }""")
        if pt:
            pm.mouse.click(*pt)
            settle(pm, 1500)
            save(pm, "phone-incident")

        print("routes, the return and hotspots")
        for street, act in (("Makin Street", "schedule"), ("Jubilee Drive", "hold"), ("Oglet Lane", "hold")):
            api.post(f"{base}/api/incidents/{find(street)['id']}/actions", data={"action": act})
        crew = [
            i
            for i in incidents()
            if i["status"] == "triaged"
            and (i.get("triage") or {}).get("decision") == "clear_now"
            and not i.get("forward_to")
        ][:3]
        for i in crew:
            api.post(f"{base}/api/incidents/{i['id']}/actions", data={"action": "schedule"})
        for tab, name, wait in (
            ("routes", "council-routes", 6000),
            ("return", "council-return", 2000),
            ("reduce", "council-reduce", 2500),
        ):
            cq.goto(f"{base}/council#{tab}", wait_until="domcontentloaded")
            settle(cq, wait)
            save(cq, name)

        print("rebrand to Humpington Council, and back")
        brand = APP / "content" / "brand.json"
        original = brand.read_text()
        try:
            b = json.loads(original)
            b.update(HUMPINGTON)
            brand.write_text(json.dumps(b, indent=2, ensure_ascii=False) + "\n")
            time.sleep(1.5)
            cq.goto(f"{base}/council#queue", wait_until="domcontentloaded")
            cq.reload(wait_until="domcontentloaded")  # a change of #tab alone does not reload the page
            settle(cq, 2500)
            save(cq, "rebrand-council")
            pm.goto(base + "/", wait_until="domcontentloaded")
            settle(pm, 2500)
            save(pm, "rebrand-phone")
            subprocess.run(
                [sys.executable, str(APP / "scripts" / "brand_check.py"), "--base", base],
                check=False,
                stdout=subprocess.DEVNULL,
            )
            cq.goto(f"{base}/dev/brand-check/", wait_until="load")
            settle(cq, 1500)
            save(cq, "rebrand-check")
        finally:
            brand.write_text(original)
        print("brand.json restored")
        browser.close()


if __name__ == "__main__":
    main()
