# static/

Two front ends in plain HTML, CSS and JavaScript, with no framework and no build step. `server.py` serves the files as they are.

| Folder | What it is |
|---|---|
| `public/` | The residents' site: the map, reporting a photo, "Is it still there?" |
| `council/` | The officers' console: the triage queue and cards, plus the Routes, Return and Reduce tabs in `views/` |
| `shared/` | `api.js` (fetch helper and the status words), `brand.js` (applies `content/brand.json`), `tokens.css` (colours and spacing), `livereload.js` |
| `vendor/leaflet/` | Leaflet 1.9.4, third-party. Don't edit it. |

- **Write the baseline brand.** Pages say "Mersey Vale" and "MVCC-" and use the `--brand` colour variables from `tokens.css`. At load time, `brand.js` recolours the page and rewrites every visible name from `/api/brand.js`, so a rebrand never touches this folder. A colour written straight into a stylesheet won't follow a rebrand.
- **The public site is for remote callers.** Phones reach only the paths `server.py` allows through the tunnel (`TUNNEL_PREFIXES`, `TUNNEL_API` and `_tunnel_allowed`). A new call from `public/` has to be added there, and it must not expose anything from the council side.
- **Residents never see cost, or that an officer is involved.** The public list carries only `triage.decision`, and statuses come from `public_status`. `tests/smoke.py` checks the API side of this; the pages must not work around it.
- **Edits show on reload.** The server sends `no-cache` for everything here except `vendor/`. The `?v=` numbers in the HTML are left over from the hackathon; there's no need to bump them.
- **Check a change on every page.** `scripts/brand_check.py` opens 21 views at desktop and phone sizes and fails any view that shows a console error, is wider than the screen, has a broken logo, or has white text below 4.5:1 contrast on the brand colour. `/screenshots` refreshes the README's images.
