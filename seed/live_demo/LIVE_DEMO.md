# Live demo kit

Five photos with GPS written into them, so uploading one drops its pin by itself. Each photo's reading is cached (`seed/model_cache.json`), so the result appears in about three seconds, with or without the local model. The photos are AI-generated illustrations; `scripts/build_kit.py` makes them from `seed/photos` using the places in `scripts/demo_places.py`.

**Before you start:** restart with fresh data (`FT_RESET=1 scripts/start_server.sh`). Upload the files as they are. If a phone re-saves or resizes a photo, its GPS and its match in the cache are lost: you would have to place the pin by hand, and the model would read it live (about 14 seconds on an Apple M2 Pro). Uploading from the laptop is safest.

| # | File | Pin lands at | What should happen |
|---|---|---|---|
| 1 | `1_black_bags_jubilee_drive.jpg` | Jubilee Drive, Kensington & Fairfield | **Officer to inspect**: household bags may hold names and addresses |
| 2 | `2_fridge_lawrence_road.jpg` | Lawrence Road, Wavertree, the bulky collection booked for today in `content/config.json` | **Not fly-tipping**: it is awaiting collection |
| 3 | `3_paint_tins_oglet_lane.jpg` | Oglet Lane, Speke, a quiet lane at the city's edge | **Specialist removal**: paint tins are a possible chemical hazard |
| 4 | `4_mattress_makin_street.jpg` | Makin Street, County, the busiest repeat hotspot in the simulated history | **Crew today**, on a repeat hotspot |
| 5 (optional) | `5_optional_merge_belmont_road.jpg` | Belmont Road, Everton, 9 m from an open report | Asks **"Is it the same?"**, and yes adds a "still there" confirmation |

## What each one shows

1. **Evidence first.** Black bags can hold names and addresses, so the rules hold them for an officer to search before a crew clears them.
2. **Local context.** The model sees a fridge left out and calls it fly-tipping. The pin falls within 30 m of a bulky collection booked for today, so the rules change the decision to "Not fly-tipping" and keep it off the crew's route.
3. **The rules catch hazards.** Paint tins are listed as a hazard, so the incident goes to a licensed specialist team and onto the officer's route, not the crew's.
4. **Prevention.** The mattress is a routine clearance, but the site has many past reports within 100 m in the last 90 days, so it is a repeat hotspot. The Reduce tab shows what would stop it coming back.
5. **One incident, many reports.** Upload it from the public page. The app spots the open Belmont Road report 9 m away, shows both photos and asks whether it is the same. Yes adds a "still there" confirmation to the existing report (which raises its priority) and sends no duplicate. No sends it as a new report, and the server still joins it to the open one.

## Suggested running order (about three minutes)

1. **Public, on a phone or the laptop:** upload photo 4. The pin drops from the photo, then "Checking…", then "Crew today" and the timeline.
2. **Council console:** open the new card and walk through the reading, the DEFRA codes, the decision and why, whose job it is, and the hotspot.
3. **Upload 1 and 2:** Officer to inspect for the bags, then the bulky-booking flag.
4. **Upload 3:** Specialist removal.
5. **Plan today's routes:** the crew route picks up 4 and anything booked on stage; the officer route picks up 3 and anything held.
6. **The WasteDataFlow return, then Reduce:** the quarter's return, laid out like the form, and the repeat-hotspot actions.

## A room of phones (optional)

To let an audience report from their phones, share the app through a tunnel (`scripts/tunnel.sh` or `scripts/room.sh tunnel`, which use a Cloudflare Quick Tunnel: fine for a demo, not for anything more). Phones get the public site; the council console on a phone asks for a password, which is made the first time a phone signs in and kept in `data/council_password.txt` (not in git). On the laptop itself, any password works.

| Command | What it does |
|---|---|
| `scripts/room.sh status` | Phones connected in the last minute, the switches, the model's queue, and whether the tunnel is reachable |
| `scripts/room.sh pause` / `resume` | Holds the room's photos back from the model; the laptop's still go straight through |
| `scripts/room.sh close` / `open` | Stops the room reporting; they can still watch the map |
| `scripts/room.sh off` / `on` | Every phone shows a thank-you and stops polling, which frees the wifi |
| `scripts/room.sh kill` | Stops the tunnel (run `off` first). A new tunnel has a new link |
| `scripts/room.sh password [new]` | Shows or changes the council password for phones |

The laptop's photos always go ahead of the room's, and the room's run one at a time with a short rest between them, so the laptop stays usable. On your own phone, open the link with `?stage=1` so your photos also go first and the kit photos are recognised.
