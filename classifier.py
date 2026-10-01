"""Photo classifier: seed cache first, then the model, one photo at a time on one background worker thread.

FT_CLASSIFIER=gemma (default) loads Gemma 4 12B via mlx-vlm at startup, and runs it on the same thread (MLX streams are
per-thread). =workers-ai sends each photo to Gemma 4 26B on Cloudflare Workers AI instead (the hosted copy, decision 6).
=cache or =off never call a model, and anything not in seed/model_cache.json gets decision "review" with
"Model offline. Check the photo."
"""

from __future__ import annotations

import itertools
import json
import os
import queue
import re
import threading
import time
from pathlib import Path

from common import LAND, MODEL_NAME, SIZES, WASTE, config, log, match_category, seed

MODEL_ID = os.environ.get("FT_MODEL", "mlx-community/gemma-4-12B-it-4bit")
MODE = os.environ.get("FT_CLASSIFIER", "gemma").strip().lower()
CACHE_DELAY = float(os.environ.get("FT_CACHE_DELAY", "0") or 0)
WARMUP = os.environ.get("FT_WARMUP", "1") != "0"

# Workers AI. A hosted copy posts to FT_AI_URL (http://ai.sorted/run), which the Worker in cloudflare/ answers with its
# AI binding and its daily cap. Anywhere else, set CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN to use Cloudflare's API.
AI_MODEL = os.environ.get("FT_AI_MODEL", "@cf/google/gemma-4-26b-a4b-it")
AI_URL = os.environ.get("FT_AI_URL", "")
AI_LIMIT = int(os.environ.get("FT_AI_LIMIT", "0") or 0)  # photos this copy may send to the model; 0 means no limit
# Thinking off, so the reply is the JSON alone and costs a few hundred tokens.
AI_SETTINGS = {"max_completion_tokens": 400, "temperature": 0.0, "chat_template_kwargs": {"enable_thinking": False}}

# Version 9 of evals/prompts/, measured against photos labelled by eye: docs/EVALS.md has the results, and
# tests/test_units.py fails if this text changes without a new run. It lists the items before sizing them. The decision
# comes from the rules in triage.py, so the model isn't asked for one.
PROMPT = """You are triaging a photo sent to an English council's fly-tipping team. Look at the whole photo carefully, then return ONE JSON object on a single line and nothing else, with these fields in this order:
{"what_you_see": "<one plain sentence>", "items": "<each dumped item with a count, e.g. 7 black bags, 1 armchair, 3 boxes; or none>", "fly_tip": "yes"|"no"|"unsure", "confidence": 0-100, "size": "Single black bag"|"Single item"|"Car boot or less"|"Small van load"|"Transit van load"|"Tipper lorry load"|"Significant/multiple loads"|"n/a", "waste_type": "Animal carcasses"|"Green"|"Vehicle parts"|"White goods"|"Other electrical"|"Tyres"|"Asbestos"|"Clinical"|"Construction/demolition/excavation"|"Black bags - commercial"|"Black bags - household"|"Chemical drums, oil or fuel"|"Other household waste"|"Other commercial waste"|"Other (unidentified)"|"n/a", "land_type": "Highway"|"Footpath/bridleway"|"Back alleyway"|"Railway"|"Council land"|"Agricultural"|"Private/residential"|"Commercial/industrial"|"Watercourse/bank"|"Other (unidentified)", "hazards": "<paint tins, fuel cans, gas bottles, batteries, possible asbestos, needles, chemicals; or none>"}

fly_tip is "no" if there is no dumped waste (a clean street, people, pets, food, indoors, a screen) or the waste is put out properly (wheelie bins, a skip, a building site, bags set neatly by bins). Waste left in a garage court, a back alley, on a verge or on a pavement is fly-tipping, garden waste included.

Size, using the Environment Agency bands. First count the bags and the larger items in "items", then judge the whole pile:
- "Single black bag": one bag and nothing else.
- "Single item": one large item on its own, with nothing else, one bag or a little loose litter: a mattress, a sofa, a fridge freezer, a wardrobe, a bath, a footstool or a shopping trolley.
- "Car boot or less": what would fit in a family car boot. For example: 2 to 5 black bags; a carpet roll with 2 or 3 bags; a few paint tins and a bag of plaster; a small heap of garden cuttings with a bag or two.
- "Small van load": too much for a car, about 1 to 4 cubic metres. For example: 6 or more black bags; an armchair with 5 or more bags; a pile of bags, boxes and a broken chair spread along the pavement; a mattress with bags beside it (a mattress never fits in a car boot); a double mattress with a bed frame; a knee-high or waist-high heap of garden cuttings or rubble.
- "Transit van load": about 4 to 10 cubic metres. For example: 16 to 30 bags; several pieces of furniture with many bags; a dismantled shed or a stack of roofing sheets; a wide pile of mixed rubbish spread across a lane, track or lay-by; or a heap taller than a person. Large dumps on country lanes and tracks are often spread out rather than tall, so judge how much ground the pile covers.
- "Tipper lorry load" or "Significant/multiple loads": much more than that, usually on waste ground or a country lane.
When a pile is between two bands, choose by the number of bags: up to 5 is a car boot, 6 or more is a small van.

Waste type is what makes up most of the pile: mainly black bags (even with some boxes or a broken chair) is "Black bags - household"; furniture, mattresses and carpets are "Other household waste"; cuttings are "Green"; rubble, plasterboard, tiles and plaster are "Construction/demolition/excavation"; fridges are "White goods"; fuel cans are "Chemical drums, oil or fuel".

Land type: pavements, verges and roads are "Highway"; "Footpath/bridleway" is only for paths away from roads; garage courts (rows of lock-up garages with a shared yard) are "Council land"; lanes behind terraces are "Back alleyway"."""

DECISIONS = ("clear_now", "hold_for_officer", "specialist", "not_a_fly_tip")
OFFLINE_REASON = "Model offline. Check the photo."
UNREADABLE_REASON = "Model reply unreadable. Check the photo."
LIMIT_REASON = "The demo has read all the photos it can for now. Check the photo."


class AIRefused(RuntimeError):
    """The Worker in front of a hosted copy refused the photo: its daily cap is reached."""


def workers_ai_reply(image: bytes, prompt: str = PROMPT, model: str = AI_MODEL, timeout: float = 90) -> str:
    """Send one JPEG to Gemma 4 on Workers AI and return the reply's text. evals/run.py measures this same call."""
    import base64

    import requests

    url, headers = AI_URL, {}
    if not url:
        account, token = os.environ.get("CLOUDFLARE_ACCOUNT_ID"), os.environ.get("CLOUDFLARE_API_TOKEN")
        if not (account and token):
            raise RuntimeError("set FT_AI_URL, or CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN")
        # The same model and inputs the hosted copy's Worker runs through its AI binding.
        url = f"https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/{model}"
        headers["Authorization"] = f"Bearer {token}"
    photo = "data:image/jpeg;base64," + base64.b64encode(image).decode()
    body = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [{"type": "image_url", "image_url": {"url": photo}}, {"type": "text", "text": prompt}],
            }
        ],
        **AI_SETTINGS,
    }
    r = requests.post(url, json=body, headers=headers, timeout=timeout)
    if r.status_code == 429:
        raise AIRefused(r.text[:200])
    r.raise_for_status()
    data = r.json()
    data = data.get("result", data)  # Cloudflare's /ai/run wraps the reply in {"result": ...}
    if isinstance(data.get("response"), str):
        return data["response"]
    return data["choices"][0]["message"].get("content") or ""


# ---- parsing ------------------------------------------------------------------------------------


def _balanced_objects(text: str):
    """Yield every top-level {...} substring, respecting quoted strings."""
    i = 0
    while True:
        start = text.find("{", i)
        if start < 0:
            return
        depth, in_str, esc = 0, False, False
        for j in range(start, len(text)):
            ch = text[j]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
            elif ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    yield text[start : j + 1]
                    i = j + 1
                    break
        else:
            yield text[start:] + ('"' if in_str else "") + "}" * max(depth, 1)  # truncated reply: close and try
            return


def _try_load(s: str):
    fixes = [
        lambda x: x,
        lambda x: re.sub(r",\s*([}\]])", r"\1", x),
        lambda x: re.sub(r",\s*([}\]])", r"\1", x.replace("“", '"').replace("”", '"').replace("’", "'")),
        lambda x: re.sub(r",\s*([}\]])", r"\1", re.sub(r"(?<![A-Za-z])'|'(?![A-Za-z])", '"', x)),
    ]
    for f in fixes:
        try:
            v = json.loads(f(s))
            if isinstance(v, dict):
                return v
        except (ValueError, TypeError):
            continue
    return None


FIELDS = ("fly_tip", "confidence", "what_you_see", "size", "waste_type", "land_type", "hazards", "decision", "reason")


def parse_json(text: str) -> dict | None:
    if not text:
        return None
    t = re.sub(r"```(?:json)?", "", str(text))
    for cand in _balanced_objects(t):
        d = _try_load(cand)
        if d and any(k in d for k in FIELDS):
            return d
    # last resort: pull fields out one by one
    d = {}
    for k in FIELDS:
        m = re.search(rf'"{k}"\s*:\s*"((?:[^"\\]|\\.)*)"', t) or re.search(rf'"{k}"\s*:\s*([0-9.]+|true|false)', t)
        if m:
            d[k] = m.group(1)
    return d if len(d) >= 3 or "fly_tip" in d else None


def normalise(raw: dict) -> dict:
    """Coerce a parsed model reply onto the exact contract values."""
    ft = str(raw.get("fly_tip", "unsure")).strip().lower()
    ft = {"true": "yes", "false": "no", "y": "yes", "n": "no", "maybe": "unsure"}.get(ft, ft)
    if ft not in ("yes", "no", "unsure"):
        ft = "unsure"
    try:
        conf = float(raw.get("confidence", 50))
        if 0 < conf <= 1:
            conf *= 100
        conf = int(round(max(0, min(100, conf))))
    except (TypeError, ValueError):
        conf = 50
    dec = str(raw.get("decision", "")).strip().lower().replace(" ", "_").replace("-", "_")
    if dec not in DECISIONS:
        dec = {"hold": "hold_for_officer", "not_fly_tip": "not_a_fly_tip", "clear": "clear_now"}.get(dec, "")
    if not dec:
        dec = "not_a_fly_tip" if ft == "no" else "clear_now"
    hz = raw.get("hazards")
    if isinstance(hz, list):
        hz = ", ".join(map(str, hz))
    items = raw.get("items")
    if isinstance(items, list):
        items = ", ".join(map(str, items))
    return {
        "fly_tip": ft,
        "confidence": conf,
        "what_you_see": str(raw.get("what_you_see") or "").strip(),
        "items": str(items or "").strip(),
        "size": match_category(raw.get("size"), SIZES),
        "waste_type": match_category(raw.get("waste_type"), WASTE),
        "land_type": match_category(raw.get("land_type"), LAND) or "Other (unidentified)",
        "hazards": str(hz or "none").strip(),
        "decision": dec,
        "reason": str(raw.get("reason") or "").strip(),
        "seconds": raw.get("seconds"),
        "model": raw.get("model") or MODEL_NAME,
    }


def offline_result(reason: str = OFFLINE_REASON) -> dict:
    return {
        "fly_tip": "unsure",
        "confidence": 0,
        "what_you_see": "",
        "size": None,
        "waste_type": None,
        "land_type": "Other (unidentified)",
        "hazards": "unknown",
        "decision": "review",
        "reason": reason,
        "seconds": 0,
        "model": MODEL_NAME,
        "offline": True,
    }


# ---- cache --------------------------------------------------------------------------------------

_cache_src = None
_cache_map: dict[str, dict] = {}


def cache_lookup(sha: str) -> dict | None:
    global _cache_src, _cache_map
    data = seed("model_cache.json", {}) or {}
    if data is not _cache_src:
        _cache_src = data
        _cache_map = {}
        if isinstance(data, dict):
            for k, v in data.items():
                if isinstance(v, dict):
                    _cache_map[k.lower().removeprefix("sha256:")] = v
    hit = _cache_map.get(sha.lower())
    if hit is None:
        return None
    out = normalise(hit)
    out["seconds"] = hit.get("seconds", 0)
    out["cached"] = True
    return out


# ---- worker -------------------------------------------------------------------------------------


class Classifier:
    def __init__(self):
        self.mode = MODE if MODE in ("gemma", "workers-ai", "cache", "off") else "gemma"
        self.status = {"gemma": "loading", "workers-ai": "ready"}.get(self.mode, "off")
        self.sent = 0  # photos sent to Workers AI, for FT_AI_LIMIT
        # (priority, sequence, ...): priority 0 is the presenter's own photo, 1 is the audience's. One model, one photo
        # at a time; the presenter's photo always goes next.
        self.q: queue.PriorityQueue = queue.PriorityQueue()
        self._seq = itertools.count()
        self.pending: set[int] = set()
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self.model = self.processor = self.formatted = None
        self.load_error: str | None = None

    def start(self):
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, name="classifier", daemon=True)
            self._thread.start()

    def info(self) -> dict:
        with self.q.mutex:
            audience = sum(1 for item in self.q.queue if item[0])
        on, gap = self._audience_settings()
        return {
            "name": MODEL_NAME,
            "id": AI_MODEL if self.mode == "workers-ai" else MODEL_ID,
            "local": self.mode != "workers-ai",
            "status": self.status,
            "queue": self.q.qsize() + (1 if self.status == "busy" else 0),
            "queue_audience": audience,
            "audience_ai": "on" if on else "paused",
            "audience_gap_seconds": gap,
            "mode": self.mode,
        }

    @staticmethod
    def _audience_settings() -> tuple[bool, float]:
        """content/config.json: "audience_ai" ("on" or "paused") and "audience_gap_seconds". Re-read on change."""
        c = config()
        try:
            gap = max(0.0, float(c.get("audience_gap_seconds", 4)))
        except (TypeError, ValueError):
            gap = 4.0
        return str(c.get("audience_ai", "on")).strip().lower() != "paused", gap

    def _stage_waiting(self) -> bool:
        with self.q.mutex:
            return bool(self.q.queue) and self.q.queue[0][0] == 0

    def is_pending(self, incident_id: int) -> bool:
        with self._lock:
            return incident_id in self.pending

    def submit(self, incident_id: int, sha: str, image_path: str, callback, stage: bool = False) -> str:
        """Classify one photo. Returns 'cache', 'queued' or 'offline'. callback(result_dict) runs exactly once.
        stage=True (the presenter's photo) jumps ahead of every audience photo still waiting."""
        hit = cache_lookup(sha)
        if hit is not None:
            if CACHE_DELAY > 0:
                with self._lock:
                    self.pending.add(incident_id)
                threading.Timer(CACHE_DELAY, self._finish, (incident_id, callback, hit)).start()
            else:
                callback(hit)
            return "cache"
        if self.mode not in ("gemma", "workers-ai") or self.status == "off":
            callback(offline_result())
            return "offline"
        with self._lock:
            over = self.mode == "workers-ai" and AI_LIMIT and self.sent >= AI_LIMIT
            if not over:
                self.sent += self.mode == "workers-ai"
                self.pending.add(incident_id)
        if over:
            callback(offline_result(LIMIT_REASON))
            return "offline"
        self.q.put((0 if stage else 1, next(self._seq), incident_id, image_path, callback))
        log.info(
            "incident %s queued for the model (%s); %s waiting",
            incident_id,
            "stage" if stage else "audience",
            self.q.qsize(),
        )
        return "queued"

    def _finish(self, incident_id, callback, result):
        try:
            callback(result)
        except Exception:
            log.exception("classifier callback failed for incident %s", incident_id)
        finally:
            with self._lock:
                self.pending.discard(incident_id)

    def _load(self):
        t0 = time.time()
        try:
            from mlx_vlm import generate, load  # noqa: F401
            from mlx_vlm.prompt_utils import apply_chat_template
            from mlx_vlm.utils import load_config

            self.model, self.processor = load(MODEL_ID)
            config = load_config(MODEL_ID)
            self.formatted = apply_chat_template(self.processor, config, PROMPT, num_images=1)
            log.info("loaded %s in %.1fs", MODEL_ID, time.time() - t0)
            if WARMUP:
                self._warmup()
            self.status = "ready"
        except Exception as e:
            self.load_error = f"{type(e).__name__}: {e}"
            self.status = "off"
            log.exception("could not load %s; falling back to cache/offline", MODEL_ID)

    def _warmup(self):
        """One short generation so the first resident's photo doesn't pay the Metal kernel compile cost."""
        from mlx_vlm import generate
        from PIL import Image

        from common import APP, DATA

        t = time.time()
        try:
            # A full reply on a real photo: a 4-token warm-up still left the first resident's photo about 6 s slower.
            p = next(iter(sorted((APP / "seed" / "photos").glob("case_*_before.jpg"))), None)
            if p is None:
                p = DATA / "warmup.jpg"
                if not p.exists():
                    Image.new("RGB", (512, 384), (128, 128, 120)).save(p, "JPEG")
            generate(
                self.model, self.processor, self.formatted, [str(p)], max_tokens=400, temperature=0.0, verbose=False
            )
            log.info("model warm-up took %.1fs", time.time() - t)
        except Exception:
            log.exception("warm-up failed (not fatal)")

    def _generate(self, image_path: str) -> dict:
        t = time.time()
        if self.mode == "workers-ai":
            try:
                text = workers_ai_reply(Path(image_path).read_bytes())
            except AIRefused as e:
                log.info("Workers AI refused the photo: %s", e)
                return offline_result(LIMIT_REASON)
        else:
            from mlx_vlm import generate

            out = generate(
                self.model, self.processor, self.formatted, [image_path], max_tokens=400, temperature=0.0, verbose=False
            )
            text = getattr(out, "text", out)
        secs = round(time.time() - t, 1)
        parsed = parse_json(text)
        if not parsed:
            log.warning("unreadable model reply: %r", str(text)[:300])
            r = offline_result(UNREADABLE_REASON)
            r["seconds"] = secs
            r["offline"] = False
            r["unreadable"] = True
            return r
        r = normalise(parsed)
        r["seconds"] = secs
        r["model"] = MODEL_NAME
        r["raw_text"] = str(text)[:2000]
        return r

    def _run(self):
        if self.mode == "gemma":
            self._load()
        while True:
            prio, seq, incident_id, image_path, callback = self.q.get()
            if prio and not self._audience_settings()[0]:
                # Audience photos paused: put it back in its place and check again shortly.
                self.q.put((prio, seq, incident_id, image_path, callback))
                self.q.task_done()
                time.sleep(1)
                continue
            try:
                if self.status in ("ready", "busy") and (self.model is not None or self.mode == "workers-ai"):
                    self.status = "busy"
                    try:
                        result = self._generate(image_path)
                    except Exception:
                        log.exception("generate failed for incident %s", incident_id)
                        result = offline_result("Model error. Check the photo.")
                    finally:
                        self.status = "ready"
                else:
                    result = offline_result()
                self._finish(incident_id, callback, result)
            finally:
                self.q.task_done()
            if prio and self.mode == "gemma":
                # Breathing room after an audience photo so the laptop stays usable on stage; a presenter's photo
                # waiting ends the pause at once.
                end = time.time() + self._audience_settings()[1]
                while time.time() < end and not self._stage_waiting():
                    time.sleep(0.25)


classifier = Classifier()
