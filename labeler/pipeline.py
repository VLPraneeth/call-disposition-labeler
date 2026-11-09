"""One record in -> one validated prediction out.

transcript -> LLM facts (strict JSON schema) -> normalise -> decide() -> validate.
If the LLM call or parsing fails after retries, a documented majority-class fallback is
emitted so every input ID always gets a schema-valid prediction.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .decide import _days_at_11, decide
from .groq_client import GroqClient, GroqError
from .prompts import PROMPT_VERSION, SYSTEM_PROMPT, USER_TEMPLATE
from .schema import FACTS_SCHEMA, OUTPUT_KEYS, normalise_facts, validate_output
from .timeparse import parse_call_time


@dataclass
class Settings:
    model: str = "openai/gpt-oss-120b"
    temperature: float = 0.0
    top_p: float = 1.0
    seed: int = 7
    reasoning_effort: str | None = "medium"   # gpt-oss only; None for other models
    max_completion_tokens: int = 4000
    structured_output: str = "json_schema"    # "json_schema" (strict) | "json_object"
    parse_attempts: int = 2                   # LLM re-asks when output is not valid JSON
    prompt_version: str = PROMPT_VERSION
    extra: dict = field(default_factory=dict)


def build_messages(rec: dict) -> list[dict]:
    call = parse_call_time(rec["call_started_at"])
    user = USER_TEMPLATE.format(call_started_at=rec["call_started_at"], weekday=call.strftime("%A"),
                                timezone=rec.get("timezone") or "Asia/Kolkata", transcript=rec["transcript"])
    return [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user}]


def build_body(rec: dict, s: Settings) -> dict:
    body = {"model": s.model, "messages": build_messages(rec), "temperature": s.temperature, "top_p": s.top_p,
            "seed": s.seed, "max_completion_tokens": s.max_completion_tokens}
    if s.reasoning_effort and "gpt-oss" in s.model:
        body["reasoning_effort"] = s.reasoning_effort
    if s.structured_output == "json_schema":
        body["response_format"] = {"type": "json_schema",
                                   "json_schema": {"name": "call_facts", "strict": True, "schema": FACTS_SCHEMA}}
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
        """Return (prediction, meta). Never raises for model/parse problems."""
        t0 = time.time()
        meta = {"transcript_id": rec["transcript_id"], "usage": {"prompt_tokens": 0, "completion_tokens": 0},
                "attempts": 0, "fallback": False, "error": None}
        body = build_body(rec, self.s)
        for i in range(self.s.parse_attempts):
            try:
                if i > 0:  # vary the seed on a re-ask so a deterministic bad output is not repeated
                    body = {**body, "seed": self.s.seed + i}
                resp, info = self._call(body)
                meta["attempts"] += info.get("attempts", 0)
                meta["cached"] = info.get("cached", False)
                u = resp.get("usage") or {}
                meta["usage"]["prompt_tokens"] += u.get("prompt_tokens", 0)
                meta["usage"]["completion_tokens"] += u.get("completion_tokens", 0)
                content = resp["choices"][0]["message"].get("content") or ""
                facts = normalise_facts(parse_json(content))
                out = decide(facts, rec["call_started_at"])
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


def settings_dict(s: Settings) -> dict:
    return asdict(s)
