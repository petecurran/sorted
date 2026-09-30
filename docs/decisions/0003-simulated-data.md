# 3. Every report is simulated, and the council is made up

Accepted for this repository.

## Context

To show a triage queue, repeat hotspots and a quarterly return, the app needs a couple of years of past reports and a set of photos. Real report data, such as FixMyStreet's, isn't published under an open licence. Photos from the web belong to their photographers, and the openly licensed ones mostly ask for share-alike terms. Using a real council's name or crest would suggest it had endorsed the project.

## Decision

`scripts/build_seed.py` simulates the reports as points on real Liverpool streets from OpenStreetMap, shaped to show what the app looks for: repeat hotspots, repeats near an earlier report, a June peak when students move out, and more reports after weekends. Everything is dated relative to the day it runs. The photos are AI-generated, and each one was labelled by eye in `seed/cases/labels.json`. The council is the fictional Mersey Vale City Council, on Liverpool's real streets and boundaries.

## Consequences

- The code can be published under MIT and the photos and data under CC BY 4.0, with no personal data in either.
- The demo always looks current, because the newest reports are always from the last few hours.
- The patterns are ours, not a council's. The hotspot and trend screens show how the app behaves, not what any real city's data says.
- Generated photos are cleaner and better lit than real ones. The evaluation therefore also uses 20 real photos, which aren't redistributed here: `evals/labels_real.json` links to each one's source.
- `tests/smoke.py` checks that "Liverpool City Council" never appears in the API.
