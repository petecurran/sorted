# 2. The model reads the photo, and the council's rules decide

Accepted for the demo.

## Context

What a council needs from a report is a decision: send a crew, hold it for an officer to look for evidence, call a licensed specialist, pass it to whoever owns the land, or close it. Those decisions carry weight. Clearing black bags too early destroys evidence, and hazardous waste needs a licensed contractor. A decision made inside a prompt can't be read or changed by an officer, and nobody can say afterwards why a report went where it did.

## Decision

The model returns a reading and nothing else: the size band, waste type and land type in DEFRA's WasteDataFlow categories, the items it can see, any hazards, and a sentence describing the photo. `triage.py` then applies the rules in `content/triage_rules.json` in order, and the first match wins. An officer can read that file and change it, and a change applies on the next page load.

The first four prompts (`evals/prompts/v1.txt` to `v4.txt`) also asked the model for its own decision, which the app only used to flag a possible hazard. From v5, the prompt doesn't ask.

Two rules hold whatever the model says. The model alone never closes a report: if it says a photo isn't fly-tipping, or isn't sure, a person checks. The only automatic close is a bulky collection booked within 30 m that day, which is a fact the photo can't show.

## Consequences

- Every decision comes with a "why" line naming the rule, and an officer can correct the reading on the card and see the rules run again.
- Changing policy needs no prompt change and no new evaluation.
- `evals/score.py` can score the reading and the decision separately. A wrong size band changes no decision; a missed hazard does, so hazards are counted on their own.
- The rules are only as good as the reading. The model often lists paint tins as items without calling them a hazard, so the specialist rule also searches the description and the item list.
- `tests/test_units.py` checks that a model "no" goes to a person. `tests/smoke.py` checks that every report closed as not fly-tipping was closed by a person or by a bulky booking.
