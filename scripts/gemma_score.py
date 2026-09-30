"""Score a scripts/gemma_eval.py run against the photo labels in seed/cases/labels.json.

    python3 scripts/gemma_score.py data/gemma_eval/RUN.json [PHOTO_LIST.txt]

Prints fly-tip, size and waste type agreement, and the final decision after the app's rules. Run from app/.
"""
import json, sys, collections
lab = json.load(open("seed/cases/labels.json"))
rules = json.load(open("content/triage_rules.json"))
import re
def decide(fly, wt, hz, seen=""):
    if fly == "no": return "not_a_fly_tip"
    hz = "" if (hz or "").strip().lower() in ("none", "n/a") else (hz or "")
    kw = [k for k in rules["specialist_hazard_keywords"] if re.search(r"\b" + re.escape(k), hz.lower())] + \
         [k for k in rules["specialist_hazard_keywords"] if len(k) > 4 and k not in ("sheet", "sheeting", "cement") and re.search(r"\b" + re.escape(k), seen.lower())]
    if wt in rules["specialist_waste_types"] or kw or "fuel" in (hz or ""): return "specialist"
    if wt in rules["hold_waste_types"]: return "hold_for_officer"
    return "clear_now"
res = json.load(open(sys.argv[1]))["results"]
if len(sys.argv) > 2:
    keep = {l.strip().split("/")[-1] for l in open(sys.argv[2]) if l.strip()}
    res = [r for r in res if r["photo"] in keep]
n = size = waste = dec = fly = 0; conf = collections.Counter(); wconf = collections.Counter(); bad = []
for r in res:
    if not r.get("items"):
        m_ = re.search(r'"items"\s*:\s*"([^"]*)"', r.get("raw_text", ""))
        r["items"] = m_.group(1) if m_ else ""
    k = r["photo"].split("_before")[0]; L = lab.get(k)
    if not L: continue
    n += 1
    fly += (r.get("fly_tip") == L["fly_tip"])
    if L["fly_tip"] == "yes":
        size += r.get("size") == L["size"]; conf[(L["size"], r.get("size"))] += 1
        waste += r.get("waste_type") == L["waste_type"]
        if r.get("waste_type") != L["waste_type"]: wconf[(L["waste_type"], r.get("waste_type"))] += 1
    d_truth = decide(L["fly_tip"], L["waste_type"], L["hazards"]); d_model = decide(r.get("fly_tip"), r.get("waste_type"), r.get("hazards"), f'{r.get("what_you_see", "")}, {r.get("items", "")}')
    dec += d_truth == d_model
    if d_truth != d_model: bad.append((k, d_truth, d_model, r.get("waste_type"), r.get("hazards")))
yes = sum(1 for r in res if lab.get(r["photo"].split("_before")[0], {}).get("fly_tip") == "yes")
print(f"{n} photos: fly-tip {fly}/{n}, size {size}/{yes}, waste {waste}/{yes}, final decision after rules {dec}/{n}")
print("size (truth -> model):", {f"{a} -> {b}": c for (a, b), c in conf.most_common() if a != b})
print("waste misses:", {f"{a} -> {b}": c for (a, b), c in wconf.most_common(8)})
print("secs/photo:", round(sum(r.get("seconds", 0) for r in res) / max(len(res), 1), 1))
print("decision misses:"); [print("  ", *b) for b in bad[:25]]
