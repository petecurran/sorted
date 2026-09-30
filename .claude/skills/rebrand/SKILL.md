---
description: Rebrand Sorted for another council (name, colours, case prefix and an optional crest), then check every page at desktop and phone sizes. Use when asked to rebrand or re-skin it, or to make it look like another council's.
argument-hint: "[council name, colours, crest]"
---

Rebrand to: $ARGUMENTS

1. Read `content/brand.json`, including its `_about` note: it sets the rules. `colour` is the header and button colour and must take white text at 4.5:1 or better; `accent` highlights the Demo badge and focus rings; `place` is the short name used in sentences; `case_prefix` starts every case reference. Never reuse "Mersey Vale" or "MVCC" inside the new name.
2. If a crest is wanted, draw it as `static/shared/marks/<short-name>.svg`: `viewBox="0 0 64 64"`, drawn in `currentColor` so it takes the header's text colour. `humpington-pirate.svg` is a worked example. Put its file name in `mark`, or leave `mark` empty for the standard gull and waves.
3. Make sure the app is running on 8800 (`curl -s http://localhost:8800/api/health`). If it isn't, start it with `scripts/start_server.sh`, without `FT_RESET`.
4. Save `content/brand.json`. Both sites change on the next page load, and screens opened with `?live=1` reload by themselves. To preview a brand without saving it, write it to a temporary file and pass that file to the check below with `--try`.
5. Run `uv run --with playwright python scripts/brand_check.py`. It uses the installed Google Chrome, in its own profile. If any view fails (the old name still showing, a broken logo, low contrast, a page wider than the screen, a console error), fix the cause and run it again until every view passes.
6. Report the new brand, the contact sheet at http://localhost:8800/dev/brand-check/, and how to undo it: `git restore content/brand.json`, and delete the crest file if you made one.
