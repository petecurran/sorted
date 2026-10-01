# The hosted demo

The hosted demo puts Sorted on the web for people to try, one person at a time. A visitor opens the link, starts a session, and gets their own copy of Sorted for 30 minutes: the residents' site to report on, and the council console to triage in. Nobody can see anyone else's copy. When the session ends, the copy is deleted along with any photos in it. It's for showing the demo, not for a community to report into, and [decision 6](decisions/0006-hosted-copy.md) explains why it works this way.

It runs on Cloudflare: a Worker in `cloudflare/` with a container per visitor, built from the `Dockerfile` at the root of the repository.

## How it fits together

```
visitor ──> Worker (cloudflare/src/index.ts)
              ├── landing page, sessions and caps ──> the Gate (one Durable Object)
              └── everything else ──> the visitor's own copy (a container running the app)
                                         ├── http://ai.sorted/run ──> Worker ──> Workers AI (Gemma 4 26B)
                                         └── http://osrm.sorted   ──> Worker ──> OSRM demo server (road routes)
```

- **The Worker** shows the landing page, starts sessions, and sends each visitor to their own copy by the session id in their cookie. It adds a small demo bar to every page, with the time left, links to the residents' site and the council console, a QR code to carry on on a phone, and "End now and delete my copy".
- **The Gate** keeps the sessions and the daily counts. When a session ends, it stops that copy's container, and Cloudflare wipes the container's disk.
- **A copy** is the same app, started with hosted mode on. Its visitor is the council, so any password opens the console. Photos go to Workers AI, and the demo kit is offered to visitors who have no photo of their own. Each copy starts from fresh demo data for today.
- **The container has no internet.** It can only reach two names, and the Worker answers both. `ai.sorted` counts the photo against the caps and then calls the model. The Worker chooses the model and its settings, so a copy can't pick a more expensive one. `osrm.sorted` passes route requests to the OSRM demo server.

## What it costs

Containers need the Workers Paid plan, which is $5 a month. Everything beyond that is bounded by the caps in `cloudflare/wrangler.jsonc`:

| Cap | Setting | Default |
|---|---|---|
| Copies running at once | `MAX_ACTIVE_SESSIONS` | 20 |
| Sessions a day, across all visitors | `MAX_SESSIONS_PER_DAY` | 100 |
| Sessions a day from one internet connection | `MAX_SESSIONS_PER_VISITOR_PER_DAY` | 20 |
| Session length, in minutes | `SESSION_MINUTES` | 30 |
| Photos the model reads in one session | `MAX_PHOTOS_PER_SESSION` | 8 |
| Photos the model reads in a day | `MAX_PHOTOS_PER_DAY` | 300 |

The worst case is every session used in full every day: 100 sessions of 30 minutes is 50 container-hours a day, or about 1,500 a month. A copy uses a "basic" container (a quarter of a vCPU, 1 GiB of memory, 4 GB of disk). Beyond the plan's allowance, that costs about a cent an hour, mostly memory at $0.009 a GiB-hour, plus a little for the Durable Object each copy runs alongside its container. CPU is charged only while it's busy. So the worst month comes to about $25 including the plan, and a quiet one is $5. A session counts from "Start my copy", and a copy that's left alone stops after 15 minutes, so most sessions cost less than the full 30 minutes. If a busy first week settles down, lowering the cap to 25 brings the worst month to about $9. The number of copies at once doesn't change the worst case, because the daily cap limits the total hours. It's set high because a link shared in a busy Slack channel brings people at once, and each copy holds its place for the full session. A "visitor" is an internet connection, so everyone in one office shares the per-visitor limit.

The model costs nothing at these caps. A photo is at most about 2,000 tokens in and 400 out, about $0.0003 at Gemma 4 26B's prices. Workers AI gives each account 10,000 "neurons" a day free, about $0.11 worth, and 300 photos uses at most about 80% of it. The demo kit photos never reach the model, because their readings are cached.

Cloudflare has no hard spending limit, so set a budget alert as well. Go to Manage Account, then Billing, then Billable Usage, and choose "Create budget alert". $10 is a sensible threshold.

## What protects the photos

- A visitor's photos stay in their own copy. The only way in is the session id in their cookie, a random 128-bit number. The phone QR code carries the same id, so anyone who scans it joins that copy until it ends.
- The app strips each photo's hidden data (GPS, camera details) as it arrives, as it always has.
- Photos the model reads go to Workers AI. [Cloudflare says](https://developers.cloudflare.com/workers-ai/platform/privacy/) it doesn't store them or use them for training. The demo kit photos never leave the copy.
- When the session ends, the Gate stops the container and its disk is wiped, every photo with it. "End now" does the same straight away. A copy that gets no requests for 15 minutes stops anyway.
- The Gate stores no addresses. It counts each visitor by a hash with a salt that changes daily, and it forgets each day's counts after two days.
- The app writes no request log. The Worker's logs (`npm run tail`, or Workers Logs in the dashboard) record each request's path and status, never a photo.
- Every page says this is a demonstration and points real reports to [gov.uk/report-flytipping](https://www.gov.uk/report-flytipping), and every page is marked `noindex`, so search engines won't list it.

## Publishing it

Do these once, on a personal Cloudflare account:

1. Sign up at cloudflare.com, then turn on the Workers Paid plan (Workers & Pages, then Plans).
2. Start Docker Desktop. `wrangler` builds the image locally and pushes it to Cloudflare.
3. Sign in and install:

   ```bash
   cd cloudflare && npm install && npx wrangler login
   ```

4. Publish:

   ```bash
   cd cloudflare && npm run deploy
   ```

   The first deploy takes several minutes, and the containers can take a few more to become available before the first session starts. When it finishes, wrangler prints the address, which looks like `https://sorted-demo.<your-subdomain>.workers.dev`. A custom domain is optional (the Worker's Settings, then Domains & Routes).

5. Create the budget alert (above).
6. Turn on the status page by choosing a key (any long password) and storing it as a secret:

   ```bash
   cd cloudflare && npx wrangler secret put STATUS_KEY
   ```

   Then open `/__demo/status` on the demo's address. The browser asks for a user name and password: any user name will do, and the password is the key.
7. Try it yourself: start a session, report a demo kit photo and one of your own, open the council console, then use "End now".
8. Measure the hosted model before sharing the link widely (below).

## Running it

- **Change a cap:** edit `vars` in `cloudflare/wrangler.jsonc`, then `npm run deploy`.
- **Close it to new visitors:** set `DEMO_OPEN` to `"no"` and deploy. Sessions already running carry on until they end.
- **Watch it:** the status page (`/__demo/status`) shows today's and yesterday's use against each cap: sessions, visitors, photos and copies running. It also says how many times each cap turned someone away, and it refreshes every minute. Each refusal is logged too, as `refused: busy`, `refused: today`, `refused: you`, `refused: closed`, `refused: photos_today` or `refused: photos_session`. Search for "refused" in Workers Logs in the dashboard, or watch them live with `npm run tail`.
- **After changing the app:** `npm run deploy` rebuilds the image and rolls it out.
- **Take it down:** `npx wrangler delete` removes the Worker. Then `npx wrangler containers list` shows the container application, and `npx wrangler containers delete <ID>` removes it. The Workers Paid plan keeps charging $5 a month until you cancel it (Workers & Pages, then Plans).

## Measuring the hosted model

The hosted copy reads photos with Gemma 4 26B on Workers AI. It uses the same prompt, but the prompt was tuned and measured on Gemma 4 12B on a laptop (`docs/EVALS.md`). To measure the hosted model on the same photos, make a Workers AI API token (in the dashboard: AI, then Workers AI, then "Use REST API"), then run:

```bash
CLOUDFLARE_ACCOUNT_ID=<id> CLOUDFLARE_API_TOKEN=<token> uv run python evals/run.py evals/runs/<today>/v9-workers-ai.json --backend workers-ai --sets dev holdout
```

```bash
uv run python evals/score.py evals/runs/<today>/v9-workers-ai.json
```

Add the tables to `docs/EVALS.md`. The run is 79 photos, well within the free daily allowance. These calls go straight to Cloudflare's API, not through the Worker, so its caps don't count them.

## Trying it on your own machine

```bash
cd cloudflare && npm run dev
```

This runs the same Worker and container on http://localhost:8787, with Docker running and no Cloudflare account. Workers AI only runs on Cloudflare, so a photo the model would read gets a fake reading instead (`FAKE_AI=1`, in `cloudflare/.dev.vars`). Settings in `.dev.vars` override the caps, so you can try them small, such as `SESSION_MINUTES=1`. The local status page is at http://localhost:8787/__demo/status, with the password `local-status`.

## What it doesn't do

- One copy per visitor means nobody sees anyone else's reports. That's deliberate.
- The app converts iPhone HEIC photos with a macOS tool, which a Linux container doesn't have. Safari turns a photo into a JPEG when it uploads one, so this rarely matters, but an HEIC file sent another way is refused.
- The OpenStreetMap tiles and the OSRM demo server are for light use. They're fine at these caps, and a busier demo would need its own (`NOTICE.md`).
- It's still a demonstration. The "Before real use" list in `docs/TECHNICAL.md` applies in full.
