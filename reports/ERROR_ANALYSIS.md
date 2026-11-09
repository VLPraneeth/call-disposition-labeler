# Error analysis

**Final system:** `openai/gpt-oss-120b` on Groq, reasoning_effort `low`, strict JSON schema. Each call is read 5 times at temperature 0.6 and decided by per-field majority vote, then the deterministic policy rules in `labeler/decide.py` are applied.
Scores follow the published contract: disposition 15, sub_disposition 20 (credited only with the correct parent), lead_quality 15, next_call_at 20. "Exact" means all four fields are correct for a call.

## 1. Results

| Set | N | disposition | sub_disposition | lead_quality | next_call_at | exact match | score /70 |
|---|---|---|---|---|---|---|---|
| Dev | 30 | 96.7% | 83.3% | 93.3% | 93.3% | 76.7% | 63.8 |
| Holdout | 20 | 100.0% | 70.0% | 95.0% | 95.0% | 60.0% | 62.2 |
| **All 50** (`outputs/predictions.jsonl`) | 50 | 98.0% | 78.0% | 94.0% | 94.0% | 70.0% | **63.2** |
| All 50, repeat run with new seeds | 50 | 96.0% | 78.0% | 92.0% | 92.0% | 72.0% | 62.2 |

- **Split:** the 50 calls were split once into dev (30) and holdout (20), stratified on (disposition, sub_disposition), seed 20261108 (`data/split.json`). Changes were driven by dev errors.
- **Holdout caveat:** later choices were also checked against the holdout as a guard against overfitting, so it is not perfectly clean.
- **Expected on unseen calls:** about 60–63 / 70, with about 70% of calls fully correct. Two runs with different seeds score 63.2 and 62.2, so differences below about 1 point are noise.

## 2. Main failure patterns

15 of the 50 calls have at least one wrong field. On 13 of them, none of the 5 reads is fully correct: the reads agree with each other and disagree with the gold. These are **systematic readings of the call, not random noise**, which is why more reads or more reasoning do not fix them. Date arithmetic and the precedence rules did not cause any error.

| Pattern | Calls | Field | What happened |
|---|---|---|---|
| Travel vs Family Discussion | 001, 034 | sub | "My husband is away" (gold: Travel) and "she hasn't come home yet" (gold: Family) are read the other way round. |
| Treatment / current-treatment doubt missed | 014, 018, 030, 038, 047 | sub | A doubt about the procedure, the doctor or an ongoing therapy is raised, but the model takes a logistics or cost reason as the main blocker, or hears no blocker at all. |
| Main blocker vs final next step | 026, 032, 049 | sub | The gold uses the final next step (Specific Callback, Vague Deferral) or another blocker; the model keeps a blocker raised mid-call. |
| Postponement vs plain follow-up | 040, 048 | next_call_at | 048 reads as a postponement (+3 days) but the gold has +1 day; in 040 a conditional "yes, call in between" was not taken as an agreed callback. |
| Booking read as unconfirmed | 037 | all four | The gold treats the consultation slot as confirmed; most reads did not. |
| Lead-quality boundary | 022, 042 | lead_quality | "I will call you myself if I want to come" (gold Low) read as unclear; 042 (gold Not Assessable) read as Low. |

**sub_disposition is the weak field:** it is wrong on 11 of the 15 calls, and on 10 of them it is the only wrong field. Most of these involve choosing the *main* blocker when the customer gives more than one reason. On the five such calls in the data, the gold picks Treatment twice and Travel, Cost and Family once each, which is not one fixed order. A code rule such as "treatment beats travel" would therefore fit these specific calls rather than the policy, so none was added.

## 3. Changes made

| Step | Change | Effect |
|---|---|---|
| 1 | Split the task: the LLM extracts evidence-backed facts in a strict JSON schema; Python applies precedence, label pairs, lead-quality order and callback time rules | Dev 62.8 / 70. Disposition, lead quality and timing were mostly right; sub_disposition was the main error source. |
| 2 | Prompt: blocker definitions written out from the policy (scan the whole call; an agreed callback does not remove a blocker; information must be requested by the customer; a conditional "if I want" is exploratory, not a refusal); always fill structured time fields | Fewer missed blockers and time fields. This is the final prompt. |
| 3 | Deterministic repair of missing time fields from the model's verbatim words (e.g. "26th" with an empty day field) | Fixed a wrong callback date with no extra API cost. |
| 4 | Code rules from the policy: "next week after <event>" is vague (F12 → F7); "no pain need" and Invalid Lead / No Pain Need are kept consistent (D1) | Fixed one callback-time error; keeps rare branches consistent. |
| 5 | 5 reads per call at temperature 0.6 with a per-field majority vote | Single greedy reads scored 59.4–61.6 across repeat runs; the vote scores 62.2–63.2 (about +2). |
| 6 | reasoning_effort `low` | Same accuracy as medium and high within noise; about 30% cheaper than medium and twice as fast. |

Prompt edits that raised the dev score but lowered the holdout score were treated as overfitting and not kept. Longer prompts, more reasoning and more votes (10–20 reads) did not beat this setup.

## 4. Runtime, tokens and cost

| Run | Calls | Wall time | Prompt tokens | Completion tokens | Est. cost |
|---|---|---|---|---|---|
| Final predictions (5 reads per call) | 50 | 418 s (4 parallel workers) | 1,277,790 | 184,257 | **$0.30** |

- About 29k tokens and $0.006 per call. `--samples 1 --temperature 0` uses about 5× fewer tokens and scores about 2 points lower.
- Prices: $0.15 / $0.60 per 1M input / output tokens (Groq price for `gpt-oss-120b`).
- 0 fallbacks in the final run.
- **Where it was run:** the submitted 50 predictions were generated by this code with the same `gpt-oss-120b` weights through Fireworks' OpenAI-compatible API, because Groq's free tier allows only 200k tokens per day. On 17 calls run on both Groq and Fireworks, the outputs agreed on 15 with equal accuracy (the same agreement as two runs on one provider). The endpoint is recorded in `outputs/predictions.log.jsonl`.
