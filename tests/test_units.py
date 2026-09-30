"""Fast checks for the model-reply parser and rule helpers. Run from the repo root: uv run python tests/test_units.py"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import triage  # noqa: E402
from classifier import normalise, parse_json  # noqa: E402
from common import COUNCIL_NAME, case_ref  # noqa: E402
from triage import _hazard_hit, public_summary  # noqa: E402

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
    for ok, name in checks:
        fails += not ok
        print("PASS" if ok else "FAIL", name)
    print("all passed" if not fails else f"{fails} failed")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
