# call-disposition-labeler

Labels de-identified enrollment-call transcripts for a pain clinic with **disposition**, **sub_disposition**, **lead_quality** and **next_call_at**, following the supplied policy (`assignment-v2`).

**Design:** an open LLM on Groq reads the call and answers small, evidence-backed questions. Plain Python then applies the published rules: precedence, valid label pairs, lead-quality order and calendar arithmetic. The LLM never does date math and never outputs a final label. Each call is read 5 times (temperature 0.6), and the labels are decided by per-field majority vote.

```
transcript ─► LLM ×5 samples (strict JSON schema) ─► facts + verbatim evidence quotes
                                            │
                     Python (labeler/decide.py, labeler/timeparse.py)
                     D1–D6 precedence · SUB pairs & tie-breaks · LQ order · F1–F12 callback rules
                                            │
                     majority vote · validate contract ─► {"transcript_id", "disposition", "sub_disposition",
                                           "lead_quality", "next_call_at"}
```

## Run it (one command)

Requires **Python ≥ 3.10**. There are **no third-party runtime dependencies**: the runner uses only the standard library, including the HTTP client. `openpyxl` is needed only for the one-off workbook conversion script.

```bash
export GROQ_API_KEY=gsk_...          # PowerShell: $env:GROQ_API_KEY="gsk_..."   (a .env file also works)
python run.py --input path/to/inputs.jsonl --output path/to/predictions.jsonl
```

- **Input:** JSONL with `transcript_id`, `call_started_at`, `timezone`, `transcript`. Any other field, including gold labels, is dropped before processing.
- **Output:** JSONL, one object per input in input order, with exactly the five contract keys. `next_call_at` is `"YYYY-MM-DDTHH:MM:SS+05:30"` or JSON `null`.
- **Run log:** `<output>.log.jsonl` with per-record extracted facts and evidence, decision trace, token usage and timings, plus a summary line with runtime, tokens and estimated cost.
- **Optional flags:** `--workers N` (parallel requests on paid tiers), `--timeout`, `--retries`, `--max-daily-wait`, `--model` (Groq model ID), `--reasoning-effort`, `--ids` (restrict to a list), `--samples N` / `--temperature T` / `--seed S` (default 5 / 0.6 / 7; `--samples 1 --temperature 0` is a 5× cheaper greedy mode, about 2 points lower), `--max-completion-tokens`.

Every input ID always receives a valid prediction. If the model is unreachable or returns unusable output after all retries, a documented majority-class fallback is written and flagged in the log.

## Results (details in [reports/ERROR_ANALYSIS.md](reports/ERROR_ANALYSIS.md))

| Set | disposition | sub_disposition | lead_quality | next_call_at | exact | score /70 |
|---|---|---|---|---|---|---|
| Dev, 30 calls | 96.7% | 83.3% | 93.3% | 93.3% | 76.7% | 63.8 |
| **Holdout, 20 calls** | 100.0% | 70.0% | 95.0% | 95.0% | 60.0% | **62.2** |
| **All 50** (`outputs/predictions.jsonl`) | 98.0% | 78.0% | 94.0% | 94.0% | 70.0% | **63.2** |
| All 50, repeat with new seeds | 96.0% | 78.0% | 92.0% | 92.0% | 72.0% | 62.2 |
| Synthetic stress set, 18 calls | 100% | 100% | 100% | 100% | 100% | 70.0 |

Single greedy sample (the earlier setup): 59.4–61.6 across repeat runs. The 5-sample vote adds about 2 points. Low, medium and high thinking score the same within noise; low is used because it is cheapest and fastest. Putting the full rulebook in the prompt made results worse (57.3). Every variant tried is described in the report; only the final version is kept in the code.
50 calls: 418 s with 4 workers, 1.46M tokens, **≈ $0.30**, 0 fallbacks.

**Provider note:** the system runs on Groq. Groq's free tier for `gpt-oss-120b` allows 8k tokens per minute and 200k per day, while one 50-call run uses about 1.46M tokens. So `outputs/predictions.jsonl` was produced by this same code, prompt and settings with the same open model weights (`gpt-oss-120b`) served through Fireworks' OpenAI-compatible endpoint; the endpoint is recorded in `outputs/predictions.log.jsonl`. On 17 calls run on both providers, the outputs agreed on 15/17 with equal accuracy (the same agreement as two runs on one provider). On a paid Groq tier, the one command above reproduces the run.

## Model and generation settings

| Setting | Value |
|---|---|
| Provider / endpoint | Groq, `https://api.groq.com/openai/v1/chat/completions` |
| Model ID | `openai/gpt-oss-120b` (open-weight) |
| temperature / top_p / seed | 0.6 / 1.0 / 7 (sample j uses seed 7 + 100·j) |
| samples per call | 5, per-field majority vote (disposition first, then the other fields among samples with that disposition) |
| reasoning_effort | `low` (medium/high tested: same accuracy, 1.4–4× the cost) |
| max_completion_tokens | 4000 |
| response_format | `json_schema`, `strict: true` (schema in `labeler/schema.py`) |
| Request timeout | 120 s |
| HTTP retries | 6, exponential backoff + jitter; honours `retry-after` / rate-limit reset headers on 429; retries 5xx and network errors |
| Rate limiting | waits proactively when the per-minute token budget is nearly spent; waits up to `--max-daily-wait` (1800 s) if a daily quota frees up soon |
| JSON parse retries | 2 (re-ask with a different seed), then fallback |

## Repository layout

```
run.py                     CLI: input JSONL -> prediction JSONL
labeler/prompts.py         complete system + user prompt templates (versioned)
labeler/schema.py          intermediate facts JSON schema, normalisation, output contract validation
labeler/decide.py          deterministic label rules (each branch cites the policy rule)
labeler/timeparse.py       callback/appointment time resolution (F1-F12) + verbatim-words repair
labeler/groq_client.py     stdlib Groq client: retries, timeouts, rate-limit pacing
labeler/pipeline.py        record -> facts -> labels -> validated prediction (+ fallback)
scripts/convert_xlsx.py    workbook tab -> data/inputs.jsonl + data/gold.jsonl
scripts/split.py           fixed stratified dev (30) / holdout (20) split, seed 20261108
scripts/evaluate.py        scorer mirroring the published scoring contract
scripts/make_synthetic.py  18 hand-labelled stress calls for labels absent from the 50
tests/                     56 unit tests (rulebook boundary examples EX1-EX6 and F-rules)
reports/ERROR_ANALYSIS.md  results, failure patterns, iteration log, runtime/tokens/cost
outputs/predictions.jsonl  final predictions for the 50 supplied calls (+ .log.jsonl: facts, evidence, tokens, cost)
```

## Reproduce the evaluation

```bash
pip install openpyxl==3.1.5                               # only for the conversion step
python scripts/convert_xlsx.py "<workbook>.xlsx" data      # inputs.jsonl + gold.jsonl
python scripts/split.py                                    # data/split.json (seeded)
python -m unittest discover -s tests -t .                  # 56 tests, offline
python run.py --input data/inputs.jsonl --output outputs/predictions.jsonl
python scripts/evaluate.py outputs/predictions.jsonl data/gold.jsonl --ids data/split.json:holdout
python run.py --input data/synthetic/inputs.jsonl --output outputs/synthetic_predictions.jsonl
python scripts/evaluate.py outputs/synthetic_predictions.jsonl data/synthetic/gold.jsonl
```

## Rules compliance

- Only the four input fields reach the workflow, and gold labels are never inputs.
- No lookups by ID, transcript hash or personal details, and no response caching.
- No external search or source-system access, and no manual correction of predictions.
- Prompt examples come from the policy's own boundary definitions. No supplied transcript is embedded in the prompt.
- No secrets are in the repository: `.env` is git-ignored and the key is read from the environment.
