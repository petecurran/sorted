# evals/

How well the model reads photos, measured through the app's own parser and rules. `docs/EVALS.md` has the results and what they mean; this is how to change them without fooling yourself.

| Path | What it is |
|---|---|
| `prompts/vN.txt` | Every prompt version, exactly as the model saw it. The newest is the one in `classifier.PROMPT` |
| `splits/dev.txt`, `holdout.txt`, `real.txt` | Which photos are in each set |
| `labels_real.json` | Labels for the 20 real photos, with a link to each one's source. The photos aren't in the repository |
| `runs/<date>/vN.json` | What the model replied to each photo, with the prompt's hash and each photo's fingerprint |
| `run.py` | Runs the model (Apple silicon only). `/eval` wraps it |
| `score.py` | Scores runs with no model, so any machine can re-score them |

## Rules

- **Tune on `dev`. Look at `holdout` once per candidate you'd ship.** A prompt tuned against the holdout set has nothing left to be measured on.
- **The real photos are a check, not a target.** Generated photos are cleaner than real ones. Report the real set alongside, and don't tune on it.
- **Never change a label to match the model.** Labels change only when a person looks at the photo and finds the label wrong. That moves every score, so re-score and say so in `docs/EVALS.md`. The edit hook blocks agents from changing labels.
- **A run is a record.** Don't edit one; make a new one. Scores come from the raw replies, so a parser or rules change is re-scored on old runs for free: run `score.py` again.
- **A prompt change needs a new run before it ships.** `tests/test_units.py` fails unless the prompt in `classifier.py` is the newest file here and has a run on every published dev and holdout photo.
- **Decisions and hazards beat size.** A size error changes no decision ([decision 2](../docs/decisions/0002-model-reads-rules-decide.md)), while a missed hazard sends a crew to paint tins. Weigh a change by "Decision" and "Hazards caught" first.
- **The sets are small.** On 15 real fly-tips, one photo is 7 points. Treat a difference of one or two photos as noise.
