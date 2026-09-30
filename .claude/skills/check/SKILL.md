---
description: Run all of Sorted's checks (lint, formatting, unit tests and the end-to-end smoke test) and report what failed. Use before committing, and after changing Python, the rules or the content files.
allowed-tools: Bash(uv run ruff check *) Bash(uv run ruff format *) Bash(uv run python tests/test_units.py)
---

Run these from the repo root, in order, and carry on past a failure so the report is complete.

1. `uv run ruff check .`
2. `uv run ruff format --check .`
3. `uv run python tests/test_units.py`: the parser, the rules, the trust rule, every DEFRA and ward name in `content/`, and whether the shipped prompt has been measured on the published photos.
4. `FT_CLASSIFIER=cache FT_OSRM_URL=http://127.0.0.1:9 uv run python tests/smoke.py`: starts its own server on port 8810 with a throwaway database and checks every endpoint. The dead OSRM address makes the Routes tab use its straight-line fallback, so the test never calls the public routing server. It rebuilds the seed files for today, which a running demo on 8800 doesn't notice.

Report one line per step. For a failure, give the failing check's name, the output that matters, and the likely cause, pointing at `CLAUDE.md` if a rule there explains it. Don't fix anything unless asked.
