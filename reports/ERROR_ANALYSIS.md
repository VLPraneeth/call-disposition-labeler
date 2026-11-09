# Error analysis

Model `gpt-oss-120b` (open-weight), prompt `p3`, temperature 0, seed 7, reasoning_effort medium, strict JSON schema.
Scores use the published contract: disposition 15, sub_disposition 20 (credited only with the correct parent), lead_quality 15, next_call_at 20 (exact string or null).

## 1. Results

| Set | N | disposition | sub_disposition | lead_quality | next_call_at | exact match | score /70 |
|---|---|---|---|---|---|---|---|
| Dev (used for iteration) | 30 | 100.0% | 83.3% | 96.7% | 86.7% | 70.0% | **63.5** |
| **Holdout (scored once, never inspected before)** | 20 | 95.0% | 70.0% | 90.0% | 80.0% | 55.0% | **57.8** |
| All 50 (= `outputs/predictions.jsonl`) | 50 | 98.0% | 78.0% | 94.0% | 84.0% | 64.0% | **61.2** |
| Synthetic stress set (hand-labelled before any run) | 18 | 100% | 100% | 100% | 100% | 100% | 70.0 |

- **Split:** the 50 calls were split once, stratified on (disposition, sub_disposition), seed 20261108 (`data/split.json`). Prompt and rule changes were driven only by dev errors. The holdout transcripts were not read until the final run.
- **Dev–holdout gap (63.5 → 57.8):** this is the honest estimate of how much the dev iteration overfit, about 6 points. Our best guess for the private 50 is **≈58–61 / 70**.
- **Synthetic set:** 18 calls that cover labels absent or rare in the 50, such as Wrong Contact, Test Enquiry, Policy Exclusion, Outside Service Area, Do Not Contact, Online, Rescheduled, Unable to Assess, refusal-then-booking, amended callback, "in 2 hours" and "parso shaam". All are correct. This checks the deterministic rules and the rare branches; it is not a realism benchmark.

**Stability.** A second identical run produced the same five fields on 46/50 calls. Dev scored 62.3 vs 63.5, and holdout was 57.8 both times. gpt-oss is not bit-deterministic at temperature 0, and about 8% of calls flip on borderline judgements.

## 2. Failure patterns (all 50, final run)

18 calls have at least one wrong field. Almost all errors are **judgement calls on the main blocker or on postponement**; the date arithmetic and the precedence rules did not fail.

| Pattern | Calls | Field(s) | What happened |
|---|---|---|---|
| Travel ↔ Family Discussion | 001, 020, 034 | sub | The customer says "I'll ask my son/wife", but the real issue is someone's availability or schedule (or the reverse). The prompt rule (p3) fixed most dev cases; the boundary is still the top confusion. |
| Treatment / Current-treatment concern under-detected | 018, 030, 038, 047 | sub | A doubt about the procedure or an ongoing therapy is stated mid-call, but the ending stresses logistics or cost, so the model picks that blocker as main. |
| Main-blocker choice among several | 049, 032, 013 | sub | Two blockers are both present (cost + family, cost + vague, information + travel), and the model emphasises the other one. |
| Postponement vs plain follow-up (+3d vs +1d) | 013, 024, 031, 034, 048 | next_call_at | The default callback day depends on whether the ending counts as a vague postponement (+3 days 11:00) or not (+1 day 11:00). For "next week after Dussehra" (024), the model correctly rejected it as a callback but did not flag the postponement. |
| Callback day | 040, 041 | next_call_at | 041: the model resolved an agreed "Wednesday" callback, while the gold expects the next day. 040: no callback was detected (vague, so +3d), while the gold has the following Monday. |
| Conditional refusal read as final | 042 | all four | Doubts about the treatment plus "I don't want it" were read as an Explicit Refusal. The gold keeps the call open as Treatment Concern. This single call costs 1.4 of the 70 points. |
| Lead quality boundary | 003, 022 | LQ | Medium vs Low on a "considering but vague" lead. |

Where the errors fall: sub_disposition (11 calls) and next_call_at (8 calls) make up about 85% of the 8.8 lost points. Disposition is nearly perfect because the D1–D6 precedence is applied in code.

## 3. Iteration log

| Version | Change | Dev result |
|---|---|---|
| p1 + rules v1 | LLM extracts facts with evidence quotes; Python applies D1–D6, the SUB pairs, the LQ order and F1–F12 | 62.8 (sub 70%, the main error source) |
| p2 | Clarified the blocker definitions from the rulebook: Travel covers work, leave, schedules and accompaniment; Family means a decision that waits on family | Partial run only: Groq's free daily quota caused 12 fallbacks |
| p3 | Scan the whole call for blockers; an agreed callback does not remove a blocker; information must be customer-requested; conditional "if I want" counts as exploratory, not refusal; always fill structured time fields | On the 18 calls comparable with v1: v1 64.7, v2 61.4, v2 + repair 62.5 |
| `repair_slot` | Deterministic fill of missing time fields from the model's verbatim `words` (e.g. "26th" with an empty day) | Fixed AVT-017; offline, no API cost (`scripts/rescore.py`) |
| **p3 final** | Full run on all 50 | **Dev 63.5 / 62.3 (repeat), holdout 57.8** |

### Second round: tried after the first holdout score, all rejected

After the first holdout score, I ran a second round of experiments. Every change was driven **only by dev errors**: I read the 9 dev error transcripts, never the holdout ones. I also decided in advance that a change would be kept only if it held up on the holdout as well.

The 9 dev errors came from 4 causes:
1. An answered question about price, distance or timing was treated as the main blocker (013, 032).
2. "Then I'll call you" was missed as a postponement (031).
3. The proposer's own "okay" was counted as acknowledging the callback (041).
4. Family vs Travel, and missed treatment doubts (018, 020, 047).

| Variant | Change (policy-grounded, general) | Dev | Holdout | All 50 |
|---|---|---|---|---|
| p4 | A blocker is a *reason*, not an answered question; main = the "final stated main unresolved blocker, not every historical objection" (D4 wording); "customer will call back" = vague (F7); the acknowledgement must come from the *other* party (F3) | 63.3 ×2 | – | – |
| p5 | p4, plus "an agreed callback does not cancel a blocker" (fixes a p4 regression on 004) | 64.3, 63.7, 63.0, 63.0 (4 seeds), 65.0 in the full run | **54.0** | 60.6 |
| p5, 3-sample majority vote | per-field vote across seeds 7/107/207 | 63.0 | – | – |
| p5, reasoning_effort=high | more reasoning | 53.2 (10/30 calls exhausted 16k tokens or timed out) | – | – |
| p6 | p5, plus quote the customer's final words *first*, then decide | 61.8 | – | – |

**Decision: keep p3.**
- p5 averaged about +0.6 to +1.5 on dev but lost 3.8 on the holdout. It turned a clear Explicit Refusal (033) into a Cost Concern, and a Travel Constraint into Further Discussion.
- Over all 50 calls, p5 scored 60.6 vs 61.2 for p3. That is noise-level, but not an improvement.
- p6 fixed four of the stubborn dev calls (013, 018, 020, 047) and broke four others.

**Conclusion:** with this model, prompt wording is at its noise floor. One run differs from another by about ±1 point on 30 calls, and every wording change moves borderline calls in both directions. Further gains on dev would be fitting to these 30 calls, not improving the policy reading. p4–p6 were tried after the first holdout score, so the holdout is no longer perfectly clean. I report that rather than hide it.

**Next steps if continued:**
- More labelled data in exactly the confused boundaries: Travel vs Family, "answered question vs real blocker", and +1d vs +3d endings. This is the only way to tune without overfitting.
- A second-pass verifier on refusals (D2 vs a conditional objection).
- A stronger open model on Groq, if one becomes available.

## 4. Runtime, tokens and cost

| Run | Calls | Wall time | Prompt tokens | Completion tokens | Est. cost |
|---|---|---|---|---|---|
| Final (`predictions.jsonl`) | 50 | 232 s (4 workers) | 255,558 | 78,097 | **$0.085** |
| Repeat run (stability) | 50 | 199 s | 255,558 | 77,907 | $0.085 |
| Synthetic set | 18 | 90 s | 61,433 | 21,717 | $0.022 |

- **Per call:** about 5.1k prompt and 1.6k completion tokens (most of it reasoning), about $0.0017, about 13 s sequentially.
- **Prices:** $0.15 / $0.60 per 1M input/output tokens. This is the published price for `gpt-oss-120b` on both Groq and Fireworks, so the cost is the same on either.
- **Total API spend for the project:** about $1.35 across all logged runs (Groq free tier plus Fireworks), including the rejected experiments.

## 5. Provider note (read this)

- **The submitted system targets Groq** (`openai/gpt-oss-120b`, `GROQ_API_KEY`), as required.
- **Why the final run used Fireworks:** Groq's free tier allows 200k tokens per day per model, about 33 calls. That made a full 50-call run take more than a day (Groq answered "try again in 40 min" after every call). The final predictions were therefore produced with the **same open-weight model (`accounts/fireworks/models/gpt-oss-120b`), the same prompt, settings and code**, through Fireworks' OpenAI-compatible endpoint (`--api-url` / `--api-key-env` flags).
- **Equivalence check:** on the 17 calls finished on Groq before switching, Groq and Fireworks gave identical outputs on 15/17, with the same accuracy (14/17 exact each). That is the same agreement level as two runs on one provider (46/50).
- **Earlier dev iterations** (v1, v2) ran on Groq.
- **Reliability on Groq:** the client honours Groq's `retry-after` headers and daily-quota messages (it waits up to `--max-daily-wait` before falling back). On a paid Groq tier, `python run.py --input … --output …` runs unchanged.
