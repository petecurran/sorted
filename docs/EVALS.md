# How good is the model?

With the prompt that ships, Gemma 4 12B gets the size band right on 83% of the generated photos it wasn't tuned on (40 of 48), and the app reaches the right decision on 90% of them. On 20 real photos it's weaker: 10 of 15 on size. Its wrong decisions are nearly all one mistake. It reads bags of household rubbish as general household waste, so the rules send a crew when an officer should first look for evidence.

This was a hackathon evaluation. It was good enough to choose a prompt in an evening and to find where the model is weak. It isn't enough to sign off anything a council would rely on, and the last section says what would be.

## What's measured

The model is Gemma 4 12B in 4-bit (`mlx-community/gemma-4-12B-it-4bit`), at temperature 0, on an Apple M2 Pro laptop with 16 GB. It takes about 14 seconds a photo.

| Set | Photos | Used for |
|---|---|---|
| Dev | 30 generated | Tuning the prompt |
| Holdout | 49 generated | Checking a prompt on photos it wasn't tuned on |
| Real | 20 real: 15 fly-tips and 5 of waste put out properly | Checking it on photos unlike the generated ones. They aren't in this repository; `evals/labels_real.json` links to each one's source |

We labelled every photo by eye. `evals/score.py` reads each of the model's replies with the app's own parser, then runs the app's rules twice: once on the model's reading and once on the label. **Decision** counts the photos where the two agree. It's the number that matters, since a wrong size band changes no decision. **Hazards caught** counts the photos whose label should go to a licensed specialist and did. **Sent to a person** counts the photos the rules handed to an officer to check.

## Results

The shipped prompt is v9; v1 is the first one. From `uv run python evals/score.py evals/runs/2026-09-30/*.json`:

**Tuning photos (generated)**, 30 in the set

| Prompt | Fly-tip or not | Size | Size, within a band | Waste type | Decision | Hazards caught | Sent to a person | Unreadable | Median s |
|---|---|---|---|---|---|---|---|---|---|
| v9 | 100% (30/30) | 87% (26/30) | 97% (29/30) | 80% (24/30) | 87% (26/30) | 50% (2/4) | 0% (0/30) | 0% (0/30) | 14.2 |
| v1 * | 100% (30/30) | 63% (19/30) | 97% (29/30) | 73% (22/30) | 77% (23/30) | 25% (1/4) | 0% (0/30) | 0% (0/30) | 11.7 |

**Held-out photos (generated)**, 49 in the set

| Prompt | Fly-tip or not | Size | Size, within a band | Waste type | Decision | Hazards caught | Sent to a person | Unreadable | Median s |
|---|---|---|---|---|---|---|---|---|---|
| v9 | 100% (49/49) | 83% (40/48) | 96% (46/48) | 90% (43/48) | 90% (44/49) | 100% (2/2) | 2% (1/49) | 0% (0/49) | 13.8 |
| v1 * | 100% (16/16) | 53% (8/15) | 100% (15/15) | 80% (12/15) | 81% (13/16) | 0% (0/1) | 6% (1/16) | 0% (0/16) | 11.8 |

**Real photos**, 20 in the set

| Prompt | Fly-tip or not | Size | Size, within a band | Waste type | Decision | Hazards caught | Sent to a person | Unreadable | Median s |
|---|---|---|---|---|---|---|---|---|---|
| v9 | 85% (17/20) | 67% (10/15) | 87% (13/15) | 73% (11/15) | 80% (16/20) | 100% (1/1) | 20% (4/20) | 0% (0/20) | 13.9 |

\* Measured on earlier copies of the generated photos, before they were re-saved for this repository.

## Where it goes wrong

- **Bags.** All five wrong decisions on the held-out photos, and two on the dev set, are bags of household rubbish read as "Other household waste". The rules hold bags for an officer because they often contain names and addresses. A misread sends a crew, and the evidence goes with the rubbish.
- **Containers it can't name.** On the dev set, paint tins came back as "3 metal cans" and fuel cans as "3 plastic containers", with no hazard listed, so both went to a crew. The rules search the item list as well as the hazards for this reason: on the real asbestos photo the model listed no hazard, but "corrugated metal sheets" in its items sent it to a specialist anyway ([decision 2](decisions/0002-model-reads-rules-decide.md)).
- **Size is usually one band out.** On the held-out photos, 46 of 48 are within one band. Six of the eight misses are between "Car boot or less" and "Small van load".
- **Waste put out properly.** On the real photos, it called bin bags and bulky items awaiting collection fly-tipping. In the app, the bin-day and bulky-booking rules catch these when the council's own data says a collection is due.

## How the prompt got here

On the evening of the hackathon, we tuned the prompt through eight versions in about 80 minutes, scoring each on the dev set. The next morning we looked at the mattress photos again, relabelled 15 of them (a mattress with bags beside it doesn't fit in a car boot) and changed the prompt to match. That's v9, which ships. It wasn't measured before the demo; the 2026-09-30 runs are its first. Dev scores below are against today's labels. The runs from the night used earlier copies of the photos (they were re-saved, smaller, for this repository), so only v9's row is on the published photos.

| Version | What changed | Dev size | Dev decision |
|---|---|---|---|
| v1 | The first prompt. Asked for the model's own decision too | 63% | 77% |
| v2 | Lists each item with a count before anything else; a fuller hazard list; size examples | 70% | 80% |
| v3 | Count the bags before judging size; paint tins can look like buckets | 80% | 80% |
| v4 | Count bags hidden behind others; don't go up a band for a close-up | 77% | 80% |
| v5 | Shorter, and stops asking for a decision: the rules decide | 70% | 87% |
| v6 | The Environment Agency size bands in full, with examples | 87% | 90% |
| v7 | What counts as fly-tipping (garage courts, verges, garden waste) | not run | not run |
| v8 | Large dumps spread along country lanes, from the real photos' misses | 90% | 93% |
| v9 | Mattresses: on their own a single item, with bags a small van load | 87% | 87% |

On the night the headline was 60% to 83% on held-out size, and 9 to 11 of 15 on the real photos. Both hold against the labels as they were then. Against today's labels those runs give 53% and 75%, and v9 on the real photos gets 10 of 15.

## Limits

- One person set the labels, by eye, with no second opinion, and 15 of them changed once.
- The sets are small. On the real photos one photo is 7 points, so treat a difference of one or two photos as noise.
- Neither check set is untouched. The holdout was scored once, for v7, before v8 and v9; v8's change came from the real photos' misses.
- Generated photos are cleaner, better lit and better framed than real ones, and most of the real photos are rural lanes, not city streets.
- Each figure is one run at temperature 0. There's no comparison with any other model.

## What real use would need

- A few hundred of the council's own photos, labelled by two officers with disagreements settled, and plenty of bags and hazards among them.
- A bar for each kind of error, set in that order: hazards missed, bags sent to a crew, then size.
- A comparison with other models, including a hosted one under a data processing agreement.
- A loop from use. When an officer corrects a reading on a card, Sorted keeps the model's original (`ai_original`), so every correction is a new labelled example.

## Reproducing it

```bash
uv run python evals/score.py evals/runs/2026-09-30/*.json                        # any machine: re-score the recorded runs
uv run python evals/score.py evals/runs/2026-09-30/v9.json --set holdout --misses  # the photos it got wrong
uv run --extra gemma python evals/run.py evals/runs/$(date +%F)/v9.json \
  --prompt evals/prompts/v9.txt --sets dev holdout                               # Apple silicon: run the model again
```

For the real photos, download them from the links in `evals/labels_real.json` into a folder, named by their keys, and add `--sets real --real-dir <folder>`. In Claude Code, `/eval` walks through a new prompt, and `evals/CLAUDE.md` has the rules for tuning without fooling yourself.
