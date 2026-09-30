# content/

The rules, words and settings an officer can change without touching code. `README.md` here is the officer's guide to these files and must stay true: if you change how a rule behaves, change it too.

- **Edits apply on the next page load.** `common.load_json` re-reads a file when its modification time changes, so there's no restart. Screens opened with `?live=1` reload by themselves.
- **A broken file fails quietly.** Invalid JSON is logged and the last good copy stays in use, so the edit looks as if it did nothing. The edit hook checks JSON after every change; check by hand with `python3 -m json.tool content/<file>.json`.
- **Names must match exactly.** DEFRA sizes, waste types and land types must be spelt as in `common.SIZES`, `WASTE` and `LAND`, and wards as in `seed/wards.geojson`. The rules skip a misspelt name without complaint; `tests/test_units.py` catches it.
- **The order of the rules lives in code.** `triage.run` fixes the precedence (specialist, bulky booking, bin day, a model "no" or "unsure", hold, crew). `triage_rules.json` holds the lists and the wording. Changing the order means changing `triage.py`, `README.md` here and [decision 2](../docs/decisions/0002-model-reads-rules-decide.md) together.
- **`scripts/room.sh` edits `config.json` with a regular expression.** Keep each `audience_*` switch a quoted string on one line, as `"audience_ai": "on"`, or the script can't find it.
- **Keys starting with `_` are notes for people.** The app ignores them, so they're the place to explain a value.
- **`brand.json`** follows its own `_about` note. After changing it, run `/rebrand` or `scripts/brand_check.py`.
