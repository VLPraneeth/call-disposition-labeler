"""One record in -> one validated prediction out.

transcript -> LLM facts (strict JSON schema) -> normalise -> decide() -> validate.
If the LLM call or parsing fails after retries, a documented majority-class fallback is
emitted so every input ID always gets a schema-valid prediction.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .decide import _days_at_11, decide
from .groq_client import GroqClient, GroqError
from .prompts import PROMPT_VERSION, PROMPTS, USER_TEMPLATE
from .schema import OUTPUT_KEYS, facts_schema, normalise_facts, validate_output
from .timeparse import parse_call_time


@dataclass
class Settings:
    model: str = "openai/gpt-oss-120b"
    temperature: float = 0.6                  # >0 so the 5 samples differ (self-consistency vote)
    top_p: float = 1.0
    seed: int = 7
    reasoning_effort: str | None = "low"      # gpt-oss only; low = medium accuracy at ~half the tokens (round 4)
    max_completion_tokens: int = 4000
    structured_output: str = "json_schema"    # "json_schema" (strict) | "json_object"
    parse_attempts: int = 2                   # LLM re-asks when output is not valid JSON
    samples: int = 5                          # independent samples per call; >1 = per-field majority vote
    prompt_version: str = PROMPT_VERSION
    extra: dict = field(default_factory=dict)


def build_messages(rec: dict, prompt_version: str = PROMPT_VERSION) -> list[dict]:
    call = parse_call_time(rec["call_started_at"])
    user = USER_TEMPLATE.format(call_started_at=rec["call_started_at"], weekday=call.strftime("%A"),
                                timezone=rec.get("timezone") or "Asia/Kolkata", transcript=rec["transcript"])
    return [{"role": "system", "content": PROMPTS[prompt_version]}, {"role": "user", "content": user}]


def build_body(rec: dict, s: Settings) -> dict:
    body = {"model": s.model, "messages": build_messages(rec, s.prompt_version), "temperature": s.temperature, "top_p": s.top_p,
            "seed": s.seed, "max_completion_tokens": s.max_completion_tokens}
    if s.reasoning_effort and "gpt-oss" in s.model:
        body["reasoning_effort"] = s.reasoning_effort
    if s.structured_output == "json_schema":
        body["response_format"] = {"type": "json_schema",
                                   "json_schema": {"name": "call_facts", "strict": True, "schema": facts_schema(s.prompt_version)}}
    else:
        body["response_format"] = {"type": "json_object"}
    body.update(s.extra)
    return body


def parse_json(text: str) -> dict:
    """Parse a JSON object from model text, tolerating code fences or leading prose."""
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        i, j = text.find("{"), text.rfind("}")
        if i >= 0 and j > i:
            return json.loads(text[i:j + 1])
        raise


def fallback_prediction(rec: dict) -> dict:
    """Majority-class prior from the labeled data (Follow-up / Travel Constraint / Medium / +3d 11:00).
    Used only when the model cannot be reached or returns unusable output after all retries."""
    return {"transcript_id": rec["transcript_id"], "disposition": "Follow-up Required",
            "sub_disposition": "Travel Constraint", "lead_quality": "Medium",
            "next_call_at": _days_at_11(rec["call_started_at"], 3)}


class Labeler:
    def __init__(self, client: GroqClient, settings: Settings, cache_dir: str | None = None):
        self.client, self.s = client, settings
        self.cache = Path(cache_dir) if cache_dir else None
        if self.cache:
            self.cache.mkdir(parents=True, exist_ok=True)

    def _cache_key(self, body: dict) -> str:
        # Keyed on the full request (model + settings + prompt + transcript text): a response cache,
        # never a label lookup. Disabled unless --cache-dir is given.
        return hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()

    def _call(self, body: dict) -> tuple[dict, dict]:
        if self.cache:
            f = self.cache / f"{self._cache_key(body)}.json"
            if f.exists():
                d = json.loads(f.read_text(encoding="utf-8"))
                return d["response"], {"attempts": 0, "cached": True}
        resp, info = self.client.chat(body)
        if self.cache:
            f.write_text(json.dumps({"response": resp}, ensure_ascii=False), encoding="utf-8")
        return resp, info

    def label(self, rec: dict) -> tuple[dict, dict]:
        """Return (prediction, meta). With samples > 1, run independent samples (different seeds) and take a
        per-field majority vote among the samples that agree with the majority disposition. Never raises."""
        if self.s.samples <= 1:
            return self._label_once(rec, self.s.seed)
        t0 = time.time()
        runs = [self._label_once(rec, self.s.seed + 100 * j) for j in range(self.s.samples)]
        ok = [(p, m) for p, m in runs if not m["fallback"]]
        meta = {"transcript_id": rec["transcript_id"],
                "usage": {k: sum(m["usage"][k] for _, m in runs) for k in ("prompt_tokens", "completion_tokens")},
                "attempts": sum(m["attempts"] for _, m in runs), "fallback": not ok,
                "error": "; ".join(str(m["error"]) for _, m in runs if m["error"]) or None,
                "samples": [{k: p[k] for k in OUTPUT_KEYS[1:]} for p, _ in runs],
                "sample_facts": [m.get("facts") for _, m in runs]}
        if not ok:
            meta["seconds"] = round(time.time() - t0, 2)
            return fallback_prediction(rec), meta
        pred = vote(rec["transcript_id"], [p for p, _ in ok])
        first = next(m for p, m in ok if p["disposition"] == pred["disposition"])
        meta.update(facts=first["facts"], trace=first["trace"], seconds=round(time.time() - t0, 2))
        return pred, meta

    def _label_once(self, rec: dict, seed: int) -> tuple[dict, dict]:
        t0 = time.time()
        meta = {"transcript_id": rec["transcript_id"], "usage": {"prompt_tokens": 0, "completion_tokens": 0},
                "attempts": 0, "fallback": False, "error": None}
        body = {**build_body(rec, self.s), "seed": seed}
        for i in range(self.s.parse_attempts):
            try:
                if i > 0:  # vary the seed on a re-ask so a deterministic bad output is not repeated
                    body = {**body, "seed": seed + i}
                resp, info = self._call(body)
                meta["attempts"] += info.get("attempts", 0)
                meta["cached"] = info.get("cached", False)
                u = resp.get("usage") or {}
                meta["usage"]["prompt_tokens"] += u.get("prompt_tokens", 0)
                meta["usage"]["completion_tokens"] += u.get("completion_tokens", 0)
                content = resp["choices"][0]["message"].get("content") or ""
                facts = normalise_facts(parse_json(content))
                out = decide(facts, rec["call_started_at"], transcript=rec["transcript"])
                pred = {"transcript_id": rec["transcript_id"], **{k: out[k] for k in OUTPUT_KEYS[1:]}}
                errs = validate_output(pred)
                if errs:
                    raise ValueError("; ".join(errs))
                meta.update(facts=facts, trace=out["trace"], seconds=round(time.time() - t0, 2))
                return pred, meta
            except GroqError as e:
                meta["error"] = str(e)
                if "Daily token limit" in str(e):
                    break
            except (ValueError, KeyError, TypeError, json.JSONDecodeError) as e:
                meta["error"] = f"parse/validate: {e}"
        meta.update(fallback=True, seconds=round(time.time() - t0, 2))
        return fallback_prediction(rec), meta


def vote(transcript_id: str, preds: list[dict]) -> dict:
    """Majority disposition (ties -> earliest sample), then per-field majority among the samples
    with that disposition, so the (disposition, sub_disposition) pair stays valid."""
    disp = Counter(p["disposition"] for p in preds).most_common(1)[0][0]
    group = [p for p in preds if p["disposition"] == disp]
    out = {"transcript_id": transcript_id, "disposition": disp}
    for k in OUTPUT_KEYS[2:]:
        out[k] = json.loads(Counter(json.dumps(p[k]) for p in group).most_common(1)[0][0])
    return out


def settings_dict(s: Settings) -> dict:
    return asdict(s)
