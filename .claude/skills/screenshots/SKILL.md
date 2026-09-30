---
description: Retake the README's screenshots in docs/screenshots from a throwaway copy of the app with fresh data.
disable-model-invocation: true
---

`scripts/screenshots.py` changes the data it runs against (it reports photos, books and holds jobs), so it gets its own server, database and port. It also switches `content/brand.json` to the example Humpington Council for about a minute and then puts it back, so warn the user that a demo running on 8800 will show that brand briefly.

1. Start the throwaway copy: `FT_RESET=1 FT_PORT=8811 FT_CLASSIFIER=cache FT_DATA_DIR="$(mktemp -d)" scripts/start_server.sh`. The temporary `FT_DATA_DIR` keeps it away from the demo's database in `data/`.
2. Run `uv run --with playwright python scripts/screenshots.py --base http://localhost:8811`. It uses the installed Google Chrome.
3. Stop the copy: `pkill -f "uvicorn server:app --host 0.0.0.0 --port 8811"`.
4. Confirm `content/brand.json` is unchanged (`git diff --quiet content/brand.json`), then list which images in `docs/screenshots/` changed (`git status --short docs/screenshots`). Don't commit them: the user will want to look first.
