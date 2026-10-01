# cloudflare/

The hosted demo: a Cloudflare Worker that gives each visitor their own copy of Sorted, in a container built from the root `Dockerfile`, for a limited time and within daily caps. `docs/HOSTING.md` explains it, what it costs and how to publish it, and [decision 6](../docs/decisions/0006-hosted-copy.md) says why it works this way.

| File | What it is |
|---|---|
| `wrangler.jsonc` | The Worker, its container, its bindings and the caps (`vars`) |
| `src/index.ts` | The Worker's routes, the Gate (sessions and counts, one Durable Object), `SortedApp` (one visitor's copy) and the two hosts a copy can reach |
| `src/pages.ts` | The landing page, the wait while a copy starts, and the status page (`/__demo/status`, behind the `STATUS_KEY` secret) |
| `src/bar.ts` | The demo bar added to every page of a copy |
| `dev.mjs` | `npm run dev`: everything locally, with no account and a fake model |

## Rules

- **The container has no internet.** Every way out is a host in `SortedApp.outboundByHost`, and the Worker decides what it costs. The Worker picks the model and its settings, never the container, and `spendPhoto` counts each photo before the model is called.
- **A copy is reached only through a session the Gate issued.** Never route to a container by anything else, or a stranger could start copies outside the caps.
- **The Gate holds every count**, and counts every refusal for the status page. A new cap should be counted there and logged as `refused: <reason>` in the same way. Keep a check's storage reads and writes after its last other `await`, so two requests can't both slip under a cap.
- **The pages say it's a demonstration** and point real reports to gov.uk/report-flytipping. Their words follow the repository's: British English and no em dashes.
- `npm run check` type-checks and `npm run dev` runs it all locally. `npm run deploy` publishes to the internet, so ask before running it.
