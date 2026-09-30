"""Run the local model over photos with a prompt, and record its raw reply to each one.

    uv run --extra gemma python evals/run.py evals/runs/<date>/v10.json --prompt evals/prompts/v10.txt --sets dev holdout
    uv run --extra gemma python evals/run.py OUT.json --sets real --real-dir ~/Downloads/real   # photos from labels_real.json
    uv run --extra gemma python evals/run.py OUT.json PHOTO...                                  # any photos, with no labels

Apple silicon only (MLX). Stop the app first, or run it with FT_CLASSIFIER=cache: two copies of the 12B model don't
fit in 16 GB. The run file is rewritten after every photo, so a long run can be read while it goes.

A run keeps only what the model said, plus the prompt's hash and each photo's fingerprint, so it is tied to the exact
prompt and bytes it measured. evals/score.py parses the replies with the app's current parser and rules.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
import time
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))
import classifier  # noqa: E402

ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
ap.add_argument("out", help="the run file to write, e.g. evals/runs/2026-10-01/v10.json")
ap.add_argument("photos", nargs="*", help="photo files, as well as or instead of --sets")
ap.add_argument(
    "--sets", nargs="+", default=[], choices=("dev", "holdout", "real"), help="photo sets from evals/splits/"
)
ap.add_argument(
    "--real-dir", type=Path, help="where the real photos are (see evals/labels_real.json for their sources)"
)
ap.add_argument("--model", default=classifier.MODEL_ID)
ap.add_argument("--prompt", help="a prompt file from evals/prompts/ (default: the prompt in classifier.py)")
a = ap.parse_args()
photos = [Path(p) for p in a.photos]
for s in a.sets:
    for k in (APP / "evals" / "splits" / f"{s}.txt").read_text().split():
        if s == "real" and not a.real_dir:
            ap.error("--sets real needs --real-dir: the real photos are not in this repository")
        photos.append(a.real_dir / f"{k}.jpg" if s == "real" else APP / "seed" / "photos" / f"{k}_before.jpg")
if not photos:
    ap.error("give some photos, or --sets")
if missing := [str(p) for p in photos if not p.is_file()]:
    ap.error(f"{len(missing)} photos not found, such as {missing[0]}")

from mlx_vlm import generate, load  # noqa: E402
from mlx_vlm.prompt_utils import apply_chat_template  # noqa: E402
from mlx_vlm.utils import load_config  # noqa: E402

prompt = Path(a.prompt).read_text() if a.prompt else classifier.PROMPT
chip = subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"], capture_output=True, text=True).stdout.strip()
memory = subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True).stdout.strip()
run = {
    "model": a.model,
    "prompt": a.prompt or "classifier.PROMPT",
    "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
    "settings": {"max_tokens": 400, "temperature": 0.0, "mlx_vlm": version("mlx-vlm")},
    "machine": f"{chip or platform.machine()}, {int(memory or 0) // 2**30} GB",
    "date": datetime.now(UTC).date().isoformat(),
    "results": [],
}

t0 = time.time()
model, processor = load(a.model)
formatted = apply_chat_template(processor, load_config(a.model), prompt, num_images=1)
print(f"loaded {a.model} in {time.time() - t0:.0f} s; {len(photos)} photos", flush=True)

out = Path(a.out)
out.parent.mkdir(parents=True, exist_ok=True)
for i, p in enumerate(photos, 1):
    t = time.time()
    reply = generate(model, processor, formatted, [str(p)], max_tokens=400, temperature=0.0, verbose=False)
    text = str(getattr(reply, "text", reply))
    run["results"].append(
        {
            "photo": p.name,
            "photo_sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
            "seconds": round(time.time() - t, 1),
            "raw_text": text,
        }
    )
    out.write_text(json.dumps(run, indent=1, ensure_ascii=False) + "\n")
    print(f"{i:3}/{len(photos)} {p.name:<44} {run['results'][-1]['seconds']:5.1f} s", flush=True)
print(f"done in {time.time() - t0:.0f} s")
