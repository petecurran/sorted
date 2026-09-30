"""Score model runs from evals/run.py against the labels, through the app's own parser and rules.

    uv run python evals/score.py evals/runs/2026-09-30/*.json                        # one row per run, per photo set
    uv run python evals/score.py evals/runs/2026-09-30/v9.json --set holdout --misses  # the photos it got wrong
    uv run python evals/score.py evals/runs/2026-09-30/v9.json --set holdout --sizes   # which size bands it confuses

Each reply is parsed by classifier.py the way the app parses it today. triage.py then decides what happens to the
photo twice, once from the model's reading and once from the label. "Decision" counts the photos where the two agree,
which measures what a reading error does to the outcome. A size error, for example, changes no decision at all.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))
import classifier  # noqa: E402
import triage  # noqa: E402
from common import SIZES  # noqa: E402

EVALS = APP / "evals"
SETS = {
    "dev": "Tuning photos (generated)",
    "holdout": "Held-out photos (generated)",
    "real": "Real photos",
}
# A point in the council's area with no bulky booking and no bin day, so only the photo drives the decision.
PLACE = {"lat": 53.4084, "lon": -2.9916, "ward": None}


def labels() -> dict[str, dict]:
    out = {}
    for f in (APP / "seed" / "cases" / "labels.json", EVALS / "labels_real.json"):
        out |= {k: v for k, v in json.loads(f.read_text()).items() if not k.startswith("_")}
    return out


def split(name: str) -> list[str]:
    return (EVALS / "splits" / f"{name}.txt").read_text().split()


def key(photo: str) -> str:
    return Path(photo).name.removesuffix(".jpg").removesuffix("_before")


def reading(raw_text: str) -> dict:
    """The model's reply as the app reads it (classifier.Classifier._generate)."""
    parsed = classifier.parse_json(raw_text)
    return classifier.normalise(parsed) if parsed else classifier.offline_result(classifier.UNREADABLE_REASON)


def decision(r: dict) -> str:
    return triage.run(r, **PLACE)["decision"]


def stale(run: dict) -> bool:
    """True if any generated photo in the run has changed since it was measured."""
    for r in run["results"]:
        p = APP / "seed" / "photos" / f"{key(r['photo'])}_before.jpg"
        if p.is_file() and hashlib.sha256(p.read_bytes()).hexdigest() != r.get("photo_sha256"):
            return True
    return False


def rows(run: dict, set_name: str) -> list[dict]:
    lab, keep = labels(), set(split(set_name))
    out = []
    for r in run["results"]:
        k = key(r["photo"])
        if k not in keep:
            continue
        truth, got = lab[k], reading(r["raw_text"])
        out.append({"photo": k, "truth": truth, "got": got, "seconds": r.get("seconds"),
                    "want": decision(truth), "decided": decision(got)})  # fmt: skip
    return out


def band(size: str | None) -> int | None:
    return SIZES.index(size) if size in SIZES else None


def metrics(rs: list[dict]) -> dict[str, tuple[int, int]]:
    """Each metric as (right, out of)."""
    tips = [r for r in rs if r["truth"]["fly_tip"] == "yes"]
    hazards = [r for r in rs if r["want"] == "specialist"]

    def near(r):
        a, b = band(r["truth"]["size"]), band(r["got"]["size"])
        return a is not None and b is not None and abs(a - b) <= 1

    return {
        "Fly-tip or not": (sum(r["got"]["fly_tip"] == r["truth"]["fly_tip"] for r in rs), len(rs)),
        "Size": (sum(r["got"]["size"] == r["truth"]["size"] for r in tips), len(tips)),
        "Size, within a band": (sum(map(near, tips)), len(tips)),
        "Waste type": (sum(r["got"]["waste_type"] == r["truth"]["waste_type"] for r in tips), len(tips)),
        "Decision": (sum(r["decided"] == r["want"] for r in rs), len(rs)),
        "Hazards caught": (sum(r["decided"] == "specialist" for r in hazards), len(hazards)),
        "Sent to a person": (sum(r["decided"] == "review" for r in rs), len(rs)),
        "Unreadable": (sum(bool(r["got"].get("offline")) for r in rs), len(rs)),
    }


def cell(right: int, total: int) -> str:
    return f"{100 * right / total:.0f}% ({right}/{total})" if total else "n/a"


def name(run: dict, path: Path) -> str:
    return Path(run.get("prompt") or path.stem).stem + (" *" if stale(run) else "")


def table(paths: list[Path]) -> str:
    runs = [(p, json.loads(p.read_text())) for p in paths]
    out, any_stale = [], False
    for set_name, title in SETS.items():
        scored = [(p, run, rows(run, set_name)) for p, run in runs]
        scored = [s for s in scored if s[2]]
        if not scored:
            continue
        heads = list(metrics(scored[0][2]))
        out += [f"**{title}**, {len(split(set_name))} in the set", "", "| Prompt | " + " | ".join(heads) + " | Median s |",
                "|---" * (len(heads) + 2) + "|"]  # fmt: skip
        for p, run, rs in scored:
            any_stale |= stale(run)
            m = metrics(rs)
            secs = statistics.median(r["seconds"] for r in rs if r["seconds"] is not None)
            out.append(f"| {name(run, p)} | " + " | ".join(cell(*m[h]) for h in heads) + f" | {secs:.1f} |")
        out.append("")
    if any_stale:
        out.append(
            "\\* Measured on earlier copies of the generated photos, before they were re-saved for this repository."
        )
    return "\n".join(out)


def misses(path: Path, set_name: str) -> str:
    run = json.loads(path.read_text())
    out = [
        "| Photo | Size (label → model) | Waste type (label → model) | Decision (label → model) |",
        "|---|---|---|---|",
    ]
    for r in rows(run, set_name):
        t, g = r["truth"], r["got"]
        if r["decided"] == r["want"] and g["size"] == t["size"] and g["waste_type"] == t["waste_type"]:
            continue
        out.append(f"| {r['photo']} | {t['size']} → {g['size']} | {t['waste_type']} → {g['waste_type']} | "
                   f"{r['want']} → {r['decided']} |")  # fmt: skip
    return "\n".join(out)


def sizes(path: Path, set_name: str) -> str:
    rs = [r for r in rows(json.loads(path.read_text()), set_name) if r["truth"]["fly_tip"] == "yes"]
    cols = [*SIZES, None]
    used = [c for c in cols if any(r["got"]["size"] == c for r in rs)]
    out = ["| Label ↓ model → | " + " | ".join(c or "none" for c in used) + " |", "|---" * (len(used) + 1) + "|"]
    for want in SIZES:
        line = [sum(r["truth"]["size"] == want and r["got"]["size"] == c for r in rs) for c in used]
        if any(line):
            out.append(f"| {want} | " + " | ".join(str(n) if n else "" for n in line) + " |")
    return "\n".join(out)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("runs", nargs="+", type=Path)
    ap.add_argument("--set", choices=SETS, help="with --misses or --sizes: which photos")
    ap.add_argument("--misses", action="store_true", help="list the photos the model got wrong")
    ap.add_argument("--sizes", action="store_true", help="print the size confusion matrix")
    a = ap.parse_args()
    if a.misses or a.sizes:
        if len(a.runs) != 1 or not a.set:
            ap.error("--misses and --sizes take one run and a --set")
        print(misses(a.runs[0], a.set) if a.misses else sizes(a.runs[0], a.set))
    else:
        print(table(a.runs))
