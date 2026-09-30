"""Fast checks for the model-reply parser, the rules, the trust rule, the content files and the evals.

Run from the repo root: uv run python tests/test_units.py
"""

import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from starlette.datastructures import Headers  # noqa: E402

import triage  # noqa: E402
from classifier import PROMPT, normalise, parse_json  # noqa: E402
from common import APP, COUNCIL_NAME, LAND, SIZES, WASTE, case_ref  # noqa: E402
from triage import _hazard_hit, public_summary  # noqa: E402
from trust import is_remote  # noqa: E402

# (who is calling, client address, headers, remote?): the presenter's laptop is the only caller trusted without a password.
TRUST = [
    ("this laptop, by name", "127.0.0.1", {"host": "localhost:8800"}, False),
    ("this laptop, IPv6", "::1", {"host": "[::1]:8800"}, False),
    ("this laptop's own page", "127.0.0.1", {"host": "127.0.0.1:8800", "origin": "http://localhost:8800"}, False),
    ("a phone on the same wifi", "192.168.1.20", {"host": "192.168.1.5:8800"}, True),
    (
        "a phone through the tunnel",
        "127.0.0.1",
        {"host": "x.trycloudflare.com", "cf-connecting-ip": "203.0.113.9"},
        True,
    ),
    ("any proxy", "127.0.0.1", {"host": "localhost:8800", "x-forwarded-for": "203.0.113.9"}, True),
    (
        "another site's page in this browser",
        "127.0.0.1",
        {"host": "localhost:8800", "origin": "https://evil.example"},
        True,
    ),
    ("a DNS-rebound name", "127.0.0.1", {"host": "rebind.evil.example:8800"}, True),
    ("a sandboxed or file page", "127.0.0.1", {"host": "localhost:8800", "origin": "null"}, True),
    ("no Host header", "127.0.0.1", {}, True),
    ("a malformed Host header", "127.0.0.1", {"host": "[::1"}, True),
    ("no client address", "", {"host": "localhost:8800"}, True),
]


def trust_checks() -> list[tuple[bool, str]]:
    return [
        (is_remote(client, Headers(headers)) is remote, f"trust: {who} is {'remote' if remote else 'trusted'}")
        for who, client, headers, remote in TRUST
    ]


def content_name_checks() -> list[tuple[bool, str]]:
    """The rules match DEFRA categories and ward names exactly, and silently skip a misspelt one, so check every one."""

    def load(name):
        return json.loads((APP / "content" / name).read_text())

    rules, whose, reduce, config = (
        load(f) for f in ("triage_rules.json", "whose_job.json", "reduce.json", "config.json")
    )
    actions = reduce.get("actions", [])
    wards = {f["properties"]["ward"] for f in json.loads((APP / "seed" / "wards.geojson").read_text())["features"]}
    named = {
        "waste types": (
            WASTE,
            rules["specialist_waste_types"]
            + rules["hold_waste_types"]
            + rules["collection_day"].get("applies_to_waste", [])
            + [w for a in actions for w in a.get("waste_types", [])],
        ),
        "land types": (
            LAND,
            [lt for r in whose["rules"] for lt in _as_list(r.get("match", {}).get("land_type"))]
            + [lt for a in actions for lt in a.get("land_types", [])],
        ),
        "sizes": (SIZES, [sz for a in actions for sz in a.get("sizes", [])]),
        "wards": (wards, config.get("collection_day_wards", [])),
    }
    return [
        (not (bad := sorted(set(used) - set(valid))), f"content names: {what} {bad or 'all valid'}")
        for what, (valid, used) in named.items()
    ]


def eval_checks() -> list[tuple[bool, str]]:
    """A prompt change needs a new measurement: the prompt that ships must have a run on the photos that ship."""

    def sha(b: bytes) -> str:
        return hashlib.sha256(b).hexdigest()

    evals = APP / "evals"
    shipped = sha(PROMPT.encode())
    newest = max((evals / "prompts").glob("v*.txt"), key=lambda f: int(f.stem[1:]))
    photos = {
        k: sha((APP / "seed" / "photos" / f"{k}_before.jpg").read_bytes())
        for s in ("dev", "holdout")
        for k in (evals / "splits" / f"{s}.txt").read_text().split()
    }
    measured = []
    for f in sorted((evals / "runs").glob("*/*.json")):
        run = json.loads(f.read_text())
        seen = {Path(r["photo"]).name.removesuffix("_before.jpg"): r.get("photo_sha256") for r in run["results"]}
        if run.get("prompt_sha256") == shipped and all(seen.get(k) == v for k, v in photos.items()):
            measured.append(f.relative_to(evals).as_posix())
    return [
        (sha(newest.read_bytes()) == shipped, f"evals: the newest prompt, {newest.name}, is the one in classifier.py"),
        (bool(measured), f"evals: the shipped prompt is measured on today's photos {measured or ''}"),
    ]


def _as_list(v) -> list:
    return [] if v is None else v if isinstance(v, list) else [v]


CASES = [
    ('{"fly_tip": "yes", "confidence": 90, "size": "Car boot or less", "waste_type": "Tyres"}', "yes"),
    ('```json\n{"fly_tip": "no", "confidence": 0.8, "decision": "not_a_fly_tip",}\n```', "no"),
    ('Here you go: {"fly_tip": "yes", "what_you_see": "A sofa {left} outside", "size": "single item"} thanks', "yes"),
    ('{"fly_tip": "unsure", "confidence": 40, "what_you_see": "Blurry photo of a', "unsure"),  # truncated
    ("{'fly_tip': 'yes', 'confidence': 70, 'waste_type': 'black bags household'}", "yes"),
]


def main():
    fails = 0
    for text, want in CASES:
        d = parse_json(text)
        n = normalise(d or {})
        ok = d is not None and n["fly_tip"] == want
        fails += not ok
        print(
            "PASS" if ok else "FAIL", repr(text[:50]), "->", n["fly_tip"], n["size"], n["waste_type"], n["confidence"]
        )
    checks = [
        (normalise({"size": "single item"})["size"] == "Single item", "size case-insensitive"),
        (normalise({"waste_type": "black bags household"})["waste_type"] == "Black bags - household", "waste fuzzy"),
        (normalise({"size": "n/a"})["size"] is None, "n/a size is None"),
        (normalise({"confidence": 0.8})["confidence"] == 80, "0-1 confidence scaled"),
        (_hazard_hit("possible asbestos, sharp edges", ["asbestos"]) == "asbestos", "hazard keyword"),
        (_hazard_hit("none", ["asbestos"]) is None, "hazard none"),
        (_hazard_hit("no asbestos visible", ["asbestos"]) is None, "hazard negated"),
        (_hazard_hit("soil and rubble", ["oil"]) is None, "oil not in soil"),
        (
            public_summary("The photo shows a sofa and bags on the pavement.") == "A sofa and bags on the pavement",
            "summary trims lead-in",
        ),
        (case_ref(19) == "MVCC-FT-2026-0019", "case_ref prefix"),
    ]
    base = {
        "fly_tip": "yes",
        "confidence": 80,
        "what_you_see": "a sofa",
        "waste_type": "Other household waste",
        "size": "Single item",
        "land_type": "Highway",
        "hazards": "",
    }
    at = dict(lat=53.4084, lon=-2.9916, ward="Central")

    def run(**kw):
        return triage.run({**base, **kw}, **at)

    t_no = run(fly_tip="no")
    t_rail = run(land_type="Railway")
    t_priv = run(land_type="Private/residential")
    t_asb = run(waste_type="Construction/demolition/excavation", hazards="broken asbestos sheeting")
    checks += [
        (t_no["decision"] == "review", "model alone says no -> review, not auto-closed"),
        (t_no["whose_job"]["body"] == COUNCIL_NAME and t_no["forward_to"] is None, "our land: no forward_to"),
        (
            t_rail["forward_to"] == "Network Rail"
            and t_rail["decision_why"] == "Network Rail land. Forward to Network Rail.",
            "railway forwards",
        ),
        ("cost" not in run(), "no cost in triage"),
        (run()["decision_why"] == "No evidence expected. Book a crew.", "plain clear_now why"),
        (t_priv["forward_to"] is None, "private land, clear first bill later: no forward"),
        (t_asb["headline_alert"] == "Possible asbestos: specialist removal", "headline_alert for asbestos"),
        (run()["headline_alert"] is None, "no alert for a plain sofa"),
    ]
    checks += trust_checks() + content_name_checks() + eval_checks()
    for ok, name in checks:
        fails += not ok
        print("PASS" if ok else "FAIL", name)
    print("all passed" if not fails else f"{fails} failed")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
