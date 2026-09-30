"""Run a local Gemma model over photos with the app's own prompt and parser, to measure it before the demo.

    uv run python scripts/gemma_eval.py OUT.json PHOTO... [--model ID] [--prompt FILE]

Two copies of the 12B model do not fit in 16 GB, so restart the app without its model first
(FT_CLASSIFIER=cache scripts/start_server.sh) and restart it normally afterwards.
Writes one result per photo as it goes, so a long run can be read while it is still going.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))
import classifier  # noqa: E402

ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
ap.add_argument("out")
ap.add_argument("photos", nargs="+")
ap.add_argument("--model", default=classifier.MODEL_ID)
ap.add_argument("--prompt", help="a text file holding a different prompt to try")
a = ap.parse_args()

from mlx_vlm import generate, load  # noqa: E402
from mlx_vlm.prompt_utils import apply_chat_template  # noqa: E402
from mlx_vlm.utils import load_config  # noqa: E402

prompt = Path(a.prompt).read_text() if a.prompt else classifier.PROMPT
t0 = time.time()
model, processor = load(a.model)
formatted = apply_chat_template(processor, load_config(a.model), prompt, num_images=1)
print(f"loaded {a.model} in {time.time() - t0:.0f} s; {len(a.photos)} photos", flush=True)

results = []
for i, p in enumerate(a.photos, 1):
    t = time.time()
    out = generate(model, processor, formatted, [p], max_tokens=400, temperature=0.0, verbose=False)
    text = str(getattr(out, "text", out))
    parsed = classifier.parse_json(text)
    r = classifier.normalise(parsed) if parsed else {"unreadable": True}
    r.update(photo=Path(p).name, seconds=round(time.time() - t, 1), raw_text=text[:1500])
    results.append(r)
    Path(a.out).write_text(
        json.dumps({"model": a.model, "prompt": a.prompt or "classifier.PROMPT", "results": results}, indent=1)
    )
    print(
        f"{i:3}/{len(a.photos)} {r['photo']:<28} {r['seconds']:5.1f} s  {r.get('fly_tip')}  {r.get('size')}  |  "
        f"{r.get('waste_type')}  |  {r.get('decision')}",
        flush=True,
    )
print(f"done in {time.time() - t0:.0f} s")
