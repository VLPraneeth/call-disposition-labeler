# Error analysis

Final system: model `gpt-oss-120b` (open-weight), prompt `p3`, **reasoning_effort low**, strict JSON schema. **5 samples at temperature 0.6 (seeds 7, 107, …, 407), per-field majority vote**, plus the deterministic rules in `labeler/decide.py` (including the F12 and need/no-pain-need consistency rules added in rounds 3–4).
Scores use the published contract: disposition 15, sub_disposition 20 (credited only with the correct parent), lead_quality 15, next_call_at 20 (exact string or null). "Exact" = all four fields correct for a call.

## 1. Results

| Set | N | disposition | sub_disposition | lead_quality | next_call_at | exact match | score /70 |
|---|---|---|---|---|---|---|---|
| Dev (used for iteration) | 30 | 96.7% | 83.3% | 93.3% | 93.3% | 76.7% | **63.8** |
| Holdout | 20 | 100.0% | 70.0% | 95.0% | 95.0% | 60.0% | **62.2** |
| All 50 (= `outputs/predictions.jsonl`) | 50 | 98.0% | 78.0% | 94.0% | 94.0% | 70.0% | **63.2** |
| All 50, independent repeat (new seeds 1007…) | 50 | 96.0% | 78.0% | 92.0% | 92.0% | 72.0% | 62.2 |
| Synthetic stress set (hand-labelled before any run) | 18 | 100% | 100% | 100% | 100% | 100% | 70.0 |

Progress on all 50: round-1 submission (single greedy sample, medium effort) 61.2 → round 3 (5-vote, medium) 62.7 / 62.6 → **final (5-vote, low) 63.2 / 62.2**. Repeat greedy runs scored 59.4–61.6, so differences under about 1 point are noise.

- **Split:** the 50 calls were split once, stratified on (disposition, sub_disposition), seed 20261108 (`data/split.json`). Prompt and rule changes were driven only by dev errors.
- **Holdout caveat:** the holdout was first scored once at the end of round 1 (57.8). Later rounds were *selected* using all-50 and holdout scores as a guard against overfitting, so the holdout is no longer perfectly clean. The changes kept in rounds 3–4 are generic (sampling, thinking level, two literal rule implementations), not tuned to any transcript.
- **Expected score on unseen calls:** about **60–63 / 70, with about 70% of calls fully correct**.
- **Synthetic set:** 18 calls that cover labels absent or rare in the 50, such as Wrong Contact, Test Enquiry, No Pain Need, Policy Exclusion, Outside Service Area, Do Not Contact, Online, Rescheduled, Unable to Assess, refusal-then-booking, amended callback, "in 2 hours" and "parso shaam". All are correct with the final setup. This checks the deterministic rules and the rare branches; it is not a realism benchmark.

**Stability.**
- Two final-setup runs with different seeds score 63.2 and 62.2 (70% and 72% exact).
- Pooling 10 or 20 samples across runs converges to 62.6 / 70% exact. The vote has reached the model's consensus reading, so more samples will not help.
- At temperature 0 the seed has no effect (all "votes" are identical). Voting only helps when the samples can differ, which is why the final setup uses temperature 0.6.

## 2. Failure patterns (all 50, final run)

15 calls have at least one wrong field. On most of them 80–100% of samples agree with each other and disagree with the gold, so the errors are **systematic readings of the call, not noise**. The date arithmetic and the precedence rules did not fail.

| Pattern | Calls | Field(s) | What happened |
|---|---|---|---|
| Travel ↔ Family Discussion | 001, 034 | sub | The customer says "my husband is away" / "she hasn't come home yet". One reads as availability (Travel), the other as a family decision; the model reads them the other way round. |
| Treatment / Current-treatment concern under-detected | 014, 018, 030, 038, 047 | sub | A doubt about the procedure or an ongoing therapy is stated mid-call, but the ending stresses logistics or cost, so the model picks that blocker as main. |
| Main-blocker choice vs final next step | 026, 032, 049 | sub | The gold uses the final next step (Specific Callback, Vague Deferral) or the other blocker; the model keeps a blocker raised mid-call. |
| Postponement vs plain follow-up (+3d vs +1d), callback day | 040, 048 | next_call_at | 048 reads as a postponement ("I'll call you back"), yet the gold has +1 day. 040: "Should I call next week?" + a conditional "yes, call in between" was not taken as agreed. |
| Booking read as unconfirmed | 037 | all four | The consultation slot was confirmed in the gold; the majority of low-effort samples read it as unconfirmed. |
| Lead quality boundary | 022, 042 | LQ | "I will call you myself if I want to come" (Low) read as unclear; 042 (Not Assessable) read as Low. |

Five calls with two competing blockers (014, 020, 025, 038, 043) do not follow one fixed order in the gold: treatment wins twice, and travel, cost and family once each. So no general code rule ("treatment beats travel") can fix them without fitting these calls and contradicting the policy's own tie-break order.

## 3. Iteration log

| Version | Change | Dev result |
|---|---|---|
| p1 + rules v1 | LLM extracts facts with evidence quotes; Python applies D1–D6, the SUB pairs, the LQ order and F1–F12 | 62.8 (sub 70%, the main error source) |
| p2 | Clarified the blocker definitions from the rulebook: Travel covers work, leave, schedules and accompaniment; Family means a decision that waits on family | Partial run only: Groq's free daily quota caused 12 fallbacks |
| p3 | Scan the whole call for blockers; an agreed callback does not remove a blocker; information must be customer-requested; conditional "if I want" counts as exploratory, not refusal; always fill structured time fields | On the 18 calls comparable with v1: v1 64.7, v2 61.4, v2 + repair 62.5 |
| `repair_slot` | Deterministic fill of missing time fields from the model's verbatim `words` (e.g. "26th" with an empty day) | Fixed AVT-017; offline, no API cost (`scripts/rescore.py`) |
| p3, round-1 submission | Full run on all 50 | Dev 63.5 / 62.3 (repeat), holdout 57.8, all 50: 61.2 |

### Second round: prompt rewording, all rejected

Every change in this round was driven **only by dev errors**: I read the 9 dev error transcripts, never the holdout ones. The 9 dev errors came from 4 causes:
1. An answered question about price, distance or timing was treated as the main blocker (013, 032).
2. "Then I'll call you" was missed as a postponement (031).
3. The proposer's own "okay" was counted as acknowledging the callback (041).
4. Family vs Travel, and missed treatment doubts (018, 020, 047).

| Variant | Change (policy-grounded, general) | Dev | Holdout | All 50 |
|---|---|---|---|---|
| p4 | A blocker is a *reason*, not an answered question; main = the "final stated main unresolved blocker" (D4 wording); "customer will call back" = vague (F7); the acknowledgement must come from the *other* party (F3) | 63.3 ×2 | – | – |
| p5 | p4, plus "an agreed callback does not cancel a blocker" | 64.3, 63.7, 63.0, 63.0 (4 seeds), 65.0 in the full run | **54.0** | 60.6 |
| p5, 3-sample vote at temperature 0 | per-field vote across seeds | 63.0 | – | – |
| p5, reasoning_effort=high | more reasoning | 53.2 (10/30 calls exhausted 16k tokens or timed out) | – | – |
| p6 | p5, plus quote the customer's final words *first*, then decide | 61.8 | – | – |

p5 gained on dev but lost 3.8 on the holdout: it turned a clear Explicit Refusal (033) into a Cost Concern. That is overfitting, so p3 was kept.

### Third round: rule fixes in code, policy-verbatim prompts, sampling

The question this round asked was which errors can be fixed **in code, from the rules**, and which are the model's reading of the call. Code-only changes were measured by re-applying `decide.py` to the logged facts (`scripts/rescore.py`), with no new API calls. All numbers are on all 50 calls; prompt variants were run twice.

| # | Variant | Kind | All 50 | Dev | Holdout | Kept? |
|---|---|---|---|---|---|---|
| A | **F12 rule in code:** a callback "next week after <event>" (e.g. "after Dussehra") is not specific; it is a vague postponement (+3 days) | code | 61.2 → **61.6**, 60.5 → **60.9** | = | +1.0 | **yes** |
| B | **F3 check in code:** verify on the speaker-labelled turns that the callback was acknowledged by the *other* party | code | 61.2 → 60.4, 60.5 → 59.3 | −0.7 | −1.0 | no |
| C | **p7:** p3 plus the *verbatim* policy SUB definitions; the model picks the Follow-up sub-disposition itself | prompt | 59.2, 59.2 | 63.0 | 53.5 | no |
| D | **p8:** p7 plus the verbatim F7/F8/F12 text; the model decides vague (+3d) vs none (+1d) | prompt | 58.3, 58.3 | 60.3 | 55.2 | no |
| E | p3, 3 samples at temperature 0 | sampling | 59.4 (all samples identical) | 63.2 | 53.8 | no |
| F | **p3, 5 samples at temperature 0.6, majority vote** | sampling | **62.7, 62.6** (two seed sets) | 66.0, 65.3 | 57.8, 58.5 | **yes** |
| G | p7, 5 samples at temperature 0.6 | prompt + sampling | 61.4 | 65.3 | 55.5 | no |

Notes:
- **A** implements F12 literally. It fixes AVT-024 on every run and changes nothing else.
- **B** follows the policy's wording but disagrees with the gold. In AVT-011 and AVT-014 the customer just continues talking after "I'll call you tomorrow/Friday", and the gold still counts the callback as agreed. The gold reads "acknowledged" loosely, so B was dropped (code removed).
- **C/D:** giving the model the official wording made it *worse*, not better. The added text shifts how it reads the whole call (blockers, refusals), not just the target field. The model's own sub-disposition pick agreed with the facts-based rule on every call, so the extra field added nothing.
- **E vs F:** at temperature 0 the seed is ignored, so "voting" repeats one answer. At temperature 0.6, single samples score 60.3–62.7 (mean 61.4, same as greedy), and the 5-vote is 62.7 / 62.6 on two independent seed sets. 3 votes was unstable (63.1 / 59.6). The gain comes from removing sample-to-sample noise on borderline calls: next_call_at went from 84% to 90% and lead_quality from 94% to 96–98%.

**What could not be fixed in code:** the remaining sub-disposition errors (Travel vs Family, a missed treatment doubt, a mid-call blocker vs the final next step) depend on how the transcript is read. No published rule decides them from the extracted facts, and keyword rules would be fitting these 50 calls.

**Next steps if continued:**
- More labelled examples of the confused boundaries: Travel vs Family, "answered question vs real blocker", and +1d vs +3d endings.
- A second-pass verifier only for refusals (D2 vs a conditional objection; AVT-042).

### Fourth round: thinking level, sampling settings, full rulebook in the prompt

All runs use 5 samples per call with the majority vote. Scores are on all 50, with exact match in brackets.

| Variant | All 50 | Dev | Holdout | Cost / 50 calls | Time (4 workers) | Kept? |
|---|---|---|---|---|---|---|
| medium effort, temperature 0.6 (round 3) | 62.7 (70%), 62.6 (70%) | 66.0, 65.3 | 57.8, 58.5 | $0.43 | 867 s | – |
| **low effort, temperature 0.6** | **63.2 (70%), 62.2 (72%)** | 63.8, 64.5 | **62.2, 58.8** | **$0.30** | **418 s** | **yes** |
| high effort, temperature 0.6 (24k token budget, 600 s timeout, 10 workers) | 61.2 (70%) | 62.3 | 59.5 | $1.18 | 1339 s | no |
| medium effort, temperature 1.0 (gpt-oss default) | 60.5 (66%) | 61.8 | 58.5 | $0.43 | 830 s | no |
| **p9:** p3 plus the **entire official rulebook verbatim** (P0–EX6, about 15k extra characters) | 57.3 (54%) | 59.8 | 53.5 | $0.52 | 780 s | no |
| Pooled vote: 10 samples (medium or low) or 20 (both) | 61.8–62.6 (68–70%) | – | – | – | – | no gain |

- **Thinking level:** low, medium and high give the same accuracy within noise. Low uses about half the reasoning tokens of medium, and high about 4× medium (1.64M completion tokens for 50 calls). High no longer fails now that it has a 24k budget, but it is not more accurate. Low is kept because it is equal in accuracy and 30% cheaper, twice as fast and lighter on Groq's token limits.
- **Full rulebook (p9):** the model has plenty of context window (128k), so length was not the problem. But the extra text made it miss postponements (+1 day instead of +3) and a real callback (029). As with p7/p8, more policy text dilutes how the model reads the transcript. The rules are already applied exactly in code.
- **Consistency rule (code):** with low effort, one synthetic call (SYN-02, "only hair fall, no pain at all") had `relevant_pain_need = "no"` but no invalid reason in 4 of the 5 samples. D1 says reliable evidence of no pain-care need *is* Invalid Lead / No Pain Need, so `decide.py` now adds that reason whenever need = "no". This mirrors the existing guard that drops it when need = "yes". It changes nothing on the 50 and fixes the synthetic set (66.1 → 70.0).
- **Ceiling:** more samples converge to 62.6 / 70% exact. The remaining 15 calls are systematic disagreements with the gold (section 2). Reaching 75% exact (38/50) would mean fitting these specific calls, which round 2 showed does not carry over to unseen calls.

## 4. Runtime, tokens and cost

| Run | Calls | Wall time | Prompt tokens | Completion tokens | Est. cost |
|---|---|---|---|---|---|
| **Final (`predictions.jsonl`), low effort, 5 samples/call** | 50 | 418 s (4 workers) | 1,277,790 | 184,257 | **$0.30** |
| Repeat with new seeds | 50 | 400 s | 1,277,790 | 185,507 | $0.30 |
| Synthetic set, final setup | 18 | 90 s | 307,165 | 55,924 | $0.08 |
| Greedy single sample, medium (`--samples 1 --temperature 0 --reasoning-effort medium`) | 50 | 232 s | 255,558 | 78,097 | $0.085 |

- **Per call (final setup):** about 25.6k prompt and 3.7k completion tokens across 5 samples, about $0.006, about 33 s sequentially (samples run one after another per call; calls run in parallel with `--workers`).
- **Cheap mode:** `--samples 1 --temperature 0` costs about 4× less and scores about 1–2 points lower.
- **Prices:** $0.15 / $0.60 per 1M input/output tokens. This is the published price for `gpt-oss-120b` on both Groq and Fireworks.
- **Total API spend for the project:** about $6.30 across all logged runs, including every rejected experiment.

## 5. Provider note (read this)

- **The submitted system targets Groq** (`openai/gpt-oss-120b`, `GROQ_API_KEY`), as required. Groq's other open text models today are `gpt-oss-20b` and `qwen/qwen3.8-27b`, both smaller, so the 120b model was kept.
- **Why the experiment and final runs used Fireworks:** Groq's free tier allows 200k tokens per day per model, about 33 greedy calls (about 7 calls with 5 samples). The final predictions were therefore produced with the **same open-weight model (`accounts/fireworks/models/gpt-oss-120b`), the same prompt, settings and code**, through Fireworks' OpenAI-compatible endpoint (`--api-url` / `--api-key-env` flags).
- **Equivalence check:** on the 17 calls finished on Groq in round 1, Groq and Fireworks gave identical outputs on 15/17, with the same accuracy. That is the same agreement level as two runs on one provider.
- **Earlier dev iterations** (v1, v2) ran on Groq.
- **Reliability on Groq:** the client honours Groq's `retry-after` headers and daily-quota messages (it waits up to `--max-daily-wait` before falling back). The final setup needs about 1.46M tokens for 50 calls, so it needs a paid Groq tier. On that tier, `python run.py --input … --output …` runs unchanged.
