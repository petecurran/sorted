---
description: Measure a photo prompt with the local model, score it against the labels, and compare it with the prompt that ships.
disable-model-invocation: true
argument-hint: "[prompt file, e.g. evals/prompts/v10.txt; empty for the shipped prompt]"
---

Prompt to measure: $ARGUMENTS (if empty, the prompt in `classifier.py`, which is the newest file in `evals/prompts/`).

Read `evals/CLAUDE.md` first: it has the rules. The short version is to tune on the dev set, look at the holdout once per candidate you'd ship, and never change a label to move a score.

1. **Check this machine can run the model.** It needs Apple silicon (`uname -sm` gives `Darwin arm64`) and about 8 GB free. If it can't, stop and offer to re-score the existing runs instead, which needs no model.
2. **Free the memory.** Two copies of the 12B model don't fit in 16 GB. If `curl -s http://localhost:8800/api/health` shows the app running with `"mode": "gemma"`, ask the user before stopping it, or restart it with `FT_CLASSIFIER=cache scripts/start_server.sh`.
3. **A new prompt is a new file.** Write it as the next `evals/prompts/vN.txt`, holding exactly the text the model should see. Past versions are fixed, because their runs record a hash of them.
4. **Run it in the background**, since it takes about 14 seconds a photo: `uv run --extra gemma python evals/run.py evals/runs/$(date +%F)/vN.json --prompt evals/prompts/vN.txt --sets dev`. Add `holdout` only for a candidate you'd ship. Add `real --real-dir <folder>` if the user has the real photos, which aren't in the repository.
5. **Score it against the shipped prompt's latest run:** `uv run python evals/score.py evals/runs/<date>/vN.json <the shipped prompt's run>`. For what changed, use `--set dev --misses` and `--set dev --sizes`.
6. **Report** the table, the photos that got better or worse, and whether it beats the shipped prompt on decisions and hazards caught as well as on size. Size alone isn't a reason to ship.
7. **Only if the user decides to ship it:** copy the text into `classifier.PROMPT` exactly, run it on the holdout set if you haven't, update the tables in `docs/EVALS.md` from `evals/score.py`, and run `uv run python tests/test_units.py`, whose eval checks confirm the shipped prompt is measured on today's photos.
