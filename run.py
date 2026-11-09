"""Label call transcripts: input JSONL -> prediction JSONL.

    python run.py --input data/inputs.jsonl --output outputs/predictions.jsonl

Reads GROQ_API_KEY from the environment, or from .env in the project root. Each input line must contain
transcript_id, call_started_at, timezone, transcript; any other fields are ignored.
Each output line has exactly: transcript_id, disposition, sub_disposition, lead_quality, next_call_at.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from labeler.groq_client import API_URL, GroqClient, load_api_key
from labeler.pipeline import Labeler, Settings, settings_dict

INPUT_FIELDS = ("transcript_id", "call_started_at", "timezone", "transcript")

# USD per 1M tokens (input, output) on Groq at time of writing; used only for the cost estimate.
PRICES = {"openai/gpt-oss-120b": (0.15, 0.60)}


def read_inputs(path: str) -> list[dict]:
    recs, seen = [], set()
    with open(path, encoding="utf-8-sig") as f:
        for n, line in enumerate(f, 1):
            if not line.strip():
                continue
            raw = json.loads(line)
            rec = {k: raw.get(k) for k in INPUT_FIELDS}  # only the contract's input fields reach the workflow
            if not rec["transcript_id"] or not rec["call_started_at"]:
                print(f"warning: line {n} missing transcript_id/call_started_at; skipped", file=sys.stderr)
                continue
            rec["transcript_id"] = str(rec["transcript_id"])
            rec["transcript"] = rec["transcript"] or ""
            if rec["transcript_id"] in seen:
                print(f"warning: duplicate id {rec['transcript_id']} on line {n}; skipped", file=sys.stderr)
                continue
            seen.add(rec["transcript_id"])
            recs.append(rec)
    return recs


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--input", required=True, help="input JSONL path")
    p.add_argument("--output", required=True, help="prediction JSONL path")
    p.add_argument("--model", default=Settings.model, help="Groq model ID")
    p.add_argument("--reasoning-effort", default=Settings.reasoning_effort, help="gpt-oss: low|medium|high; 'none' to omit")
    p.add_argument("--max-completion-tokens", type=int, default=Settings.max_completion_tokens)
    p.add_argument("--temperature", type=float, default=Settings.temperature,
                   help="sampling temperature (0 = greedy; use >0 with --samples for self-consistency voting)")
    p.add_argument("--seed", type=int, default=Settings.seed, help="base seed (sample j uses seed + 100*j)")
    p.add_argument("--samples", type=int, default=Settings.samples, help="samples per call with different seeds; >1 = majority vote (1 + --temperature 0 = cheap greedy mode)")
    p.add_argument("--workers", type=int, default=1, help="parallel requests (raise on paid Groq tiers)")
    p.add_argument("--timeout", type=float, default=120.0, help="per-request timeout, seconds")
    p.add_argument("--retries", type=int, default=6, help="HTTP retries per request (429/5xx/network)")
    p.add_argument("--max-daily-wait", type=float, default=1800.0,
                   help="if a daily Groq quota is hit and frees up within this many seconds, wait instead of falling back")
    p.add_argument("--ids", default=None, help="optional file with one transcript_id per line (or JSON list) to restrict the run")
    p.add_argument("--log", default=None, help="optional JSONL with per-record facts, trace, usage (default: <output>.log.jsonl)")
    a = p.parse_args(argv)

    recs = read_inputs(a.input)
    if a.ids:
        txt = Path(a.ids).read_text(encoding="utf-8").strip()
        wanted = set(json.loads(txt)) if txt.startswith("[") else {l.strip() for l in txt.splitlines() if l.strip()}
        recs = [r for r in recs if r["transcript_id"] in wanted]

    s = Settings(model=a.model, seed=a.seed, temperature=a.temperature, samples=a.samples,
                 max_completion_tokens=a.max_completion_tokens,
                 reasoning_effort=None if a.reasoning_effort in (None, "none") else a.reasoning_effort)
    labeler = Labeler(GroqClient(load_api_key("GROQ_API_KEY"), timeout=a.timeout, max_retries=a.retries,
                                  max_daily_wait=a.max_daily_wait), s)

    t0 = time.time()
    results: dict[str, tuple[dict, dict]] = {}

    def work(rec):
        pred, meta = labeler.label(rec)
        status = "FALLBACK " + str(meta.get("error"))[:120] if meta["fallback"] else "ok"
        print(f"[{len(results) + 1}/{len(recs)}] {rec['transcript_id']} {pred['disposition']} / {pred['sub_disposition']}"
              f" / {pred['lead_quality']} / {pred['next_call_at']}  ({meta.get('seconds')}s, {status})", flush=True)
        results[rec["transcript_id"]] = (pred, meta)

    if a.workers <= 1:
        for r in recs:
            work(r)
    else:
        with ThreadPoolExecutor(max_workers=a.workers) as ex:
            list(ex.map(work, recs))

    out = Path(a.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        for r in recs:  # input order
            f.write(json.dumps(results[r["transcript_id"]][0], ensure_ascii=False) + "\n")

    elapsed = time.time() - t0
    pin = sum(m["usage"]["prompt_tokens"] for _, m in results.values())
    pout = sum(m["usage"]["completion_tokens"] for _, m in results.values())
    price = PRICES.get(s.model)
    summary = {"records": len(recs), "fallbacks": sum(m["fallback"] for _, m in results.values()),
               "runtime_seconds": round(elapsed, 1), "prompt_tokens": pin, "completion_tokens": pout,
               "estimated_cost_usd": round(pin / 1e6 * price[0] + pout / 1e6 * price[1], 4) if price else None,
               "settings": settings_dict(s), "api_url": API_URL}
    log = Path(a.log) if a.log else out.with_suffix(".log.jsonl")
    with open(log, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps({"summary": summary}, ensure_ascii=False) + "\n")
        for r in recs:
            f.write(json.dumps(results[r["transcript_id"]][1], ensure_ascii=False) + "\n")
    print(json.dumps({k: v for k, v in summary.items() if k != "settings"}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
