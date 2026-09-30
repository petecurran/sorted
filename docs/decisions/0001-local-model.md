# 1. The model runs on the council's own machine

Accepted for the demo.

## Context

The photos are the sensitive part of a fly-tipping report. They can show faces, number plates and the fronts of houses, and a split black bag can show a name and address. A council sending them to a hosted AI service would need a data protection impact assessment and a processor agreement before the first photo, which a one-day build can't do. The demo also ran in a conference hall, where the wifi was shared with a room of phones.

## Decision

Sorted reads photos with Gemma 4 12B, in the 4-bit MLX build (`mlx-community/gemma-4-12B-it-4bit`, about 7 GB), on the presenter's Apple M2 Pro laptop with 16 GB of memory. `classifier.py` loads it once and runs one photo at a time on its own thread. Nothing leaves the machine.

## Consequences

- A photo takes about 14 seconds, and photos queue. The presenter's photos go to the front of the queue, and the room's wait with a short rest between them, so the laptop stays usable on stage.
- It runs on Apple silicon only. Other machines get cached readings for the demo photos ([decision 5](0005-cached-readings.md)) and send new photos to a person.
- A hosted model would probably read photos better and faster. We didn't compare one, and that comparison, on the council's own photos, would come before any real use.
- Swapping the model means changing `classifier.py` alone. Everything after it takes the same reading ([decision 2](0002-model-reads-rules-decide.md)), and `evals/` measures a new model or prompt the same way.
