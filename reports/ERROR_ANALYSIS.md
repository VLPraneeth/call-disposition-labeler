# Error analysis

Final system: model `gpt-oss-120b` (open-weight), prompt `p3`, reasoning_effort medium, strict JSON schema. **5 samples at temperature 0.6 (seeds 7, 107, …, 407), per-field majority vote**, plus the deterministic rules in `labeler/decide.py` (including the F12 rule added in round 3).
Scores use the published contract: disposition 15, sub_disposition 20 (credited only with the correct parent), lead_quality 15, next_call_at 20 (exact string or null).

## 1. Results

| Set | N | disposition | sub_disposition | lead_quality | next_call_at | exact match | score /70 |
|---|---|---|---|---|---|---|---|
| Dev (used for iteration) | 30 | 100.0% | 86.7% | 100.0% | 93.3% | 80.0% | **66.0** |
| Holdout | 20 | 95.0% | 65.0% | 90.0% | 85.0% | 55.0% | **57.8** |
| All 50 (= `outputs/predictions.jsonl`) | 50 | 98.0% | 78.0% | 96.0% | 90.0% | 70.0% | **62.7** |
| All 50, independent repeat (new seeds 1007…) | 50 | 98.0% | 76.0% | 98.0% | 90.0% | 70.0% | 62.6 |
| Synthetic stress set (hand-labelled before any run) | 18 | 100% | 100% | 100% | 100% | 100% | 70.0 |

The previous submission (single greedy sample) scored 61.2 on all 50. Repeat runs of that greedy setup scored 61.2, 60.5 and 59.4, with the F12 rule 61.6, 60.9 and 59.4 (mean about 60.6).

- **Split:** the 50 calls were split once, stratified on (disposition, sub_disposition), seed 20261108 (`data/split.json`). Prompt and rule changes were driven only by dev errors.
- **Holdout caveat:** the holdout was first scored once at the end of round 1 (57.8). Rounds 2 and 3 were *selected* using all-50 and holdout scores as a guard against overfitting, so the holdout is no longer perfectly clean. The round-3 change (voting) is a generic variance-reduction method, not tuned to any transcript.
- **Expected score on unseen calls:** about **58–62 / 70**. The dev–holdout gap (about 8 points) is partly overfitting and partly that the holdout happens to hold harder calls (7 of the 11 sub-disposition misses are there).
- **Synthetic set:** 18 calls that cover labels absent or rare in the 50, such as Wrong Contact, Test Enquiry, Policy Exclusion, Outside Service Area, Do Not Contact, Online, Rescheduled, Unable to Assess, refusal-then-booking, amended callback, "in 2 hours" and "parso shaam". All are correct with the final setup. This checks the deterministic rules and the rare branches; it is not a realism benchmark.

**Stability.**
- Two final-setup runs with different seeds agree on all four fields for 47/50 calls (62.7 vs 62.6).
- Two greedy runs agreed on 46/50 calls and their scores varied by up to 2.2 points across days.
- At temperature 0 the seed has no effect (all "votes" are identical). Voting only helps when the samples can differ, which is why the final setup uses temperature 0.6.

## 2. Failure patterns (all 50, final run)

15 calls have at least one wrong field. Almost all errors are **judgement calls on the main blocker**. The date arithmetic and the precedence rules did not fail.

| Pattern | Calls | Field(s) | What happened |
|---|---|---|---|
| Travel ↔ Family Discussion | 001, 020, 034, 049 | sub | The customer says "I'll ask my son/wife", but the real issue is someone's availability or schedule (or the reverse). 049: cost vs family. This is still the top confusion. |
| Treatment / Current-treatment concern under-detected | 014, 030, 038, 047 | sub | A doubt about the procedure or an ongoing therapy is stated mid-call, but the ending stresses logistics or cost, so the model picks that blocker as main. |
| Main-blocker choice vs final next step | 013, 032 | sub | The gold uses the final next step (Information Requested, Vague Deferral). The model keeps a blocker raised mid-call (travel, cost) that the agent had answered. |
| Postponement vs plain follow-up (+3d vs +1d) | 031, 034, 048 | next_call_at | Whether the ending counts as a vague postponement (+3 days 11:00) or not (+1 day 11:00). 048 reads as a postponement ("I'll call you back"), yet the gold has +1 day. |
| Callback day | 040 | next_call_at | "Should I call next week?" + a conditional "yes, call in between" was not taken as agreed; the gold has the following Monday. |
| Conditional refusal read as final | 042 | all four | Doubts about the treatment plus "Forget it" were read as an Explicit Refusal. The gold keeps the call open as Treatment Concern. This single call costs 1.4 of the 70 points. |
| Lead quality boundary | 003 | LQ | "I will consult my wife" was read as deferring over 30 days (Low). |

Voting removed most next_call_at errors (8 → 5) and two lead-quality errors. Sub-disposition (11 calls) is now the main source of the 7.3 lost points; it is a reading-the-call problem, not a rules problem.

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

## 4. Runtime, tokens and cost

| Run | Calls | Wall time | Prompt tokens | Completion tokens | Est. cost |
|---|---|---|---|---|---|
| **Final (`predictions.jsonl`), 5 samples/call** | 50 | 867 s (4 workers) | 1,277,790 | 398,880 | **$0.43** |
| Repeat with new seeds | 50 | 789 s | 1,277,790 | 399,488 | $0.43 |
| Synthetic set, final setup | 18 | 203 s | 307,165 | 106,327 | $0.11 |
| Greedy single sample (`--samples 1 --temperature 0`) | 50 | 232 s | 255,558 | 78,097 | $0.085 |

- **Per call (final setup):** about 25.6k prompt and 8.0k completion tokens across 5 samples, about $0.009, about 70 s sequentially (samples run one after another per call; calls run in parallel with `--workers`).
- **Cheap mode:** `--samples 1 --temperature 0` costs 5× less and scores about 2 points lower (about 60.6 on average).
- **Prices:** $0.15 / $0.60 per 1M input/output tokens. This is the published price for `gpt-oss-120b` on both Groq and Fireworks.
- **Total API spend for the project:** about $3.45 across all logged runs, including every rejected experiment.

## 5. Provider note (read this)

- **The submitted system targets Groq** (`openai/gpt-oss-120b`, `GROQ_API_KEY`), as required. Groq's other open text models today are `gpt-oss-20b` and `qwen/qwen3.8-27b`, both smaller, so the 120b model was kept.
- **Why the experiment and final runs used Fireworks:** Groq's free tier allows 200k tokens per day per model, about 33 greedy calls (about 6 calls with 5 samples). The final predictions were therefore produced with the **same open-weight model (`accounts/fireworks/models/gpt-oss-120b`), the same prompt, settings and code**, through Fireworks' OpenAI-compatible endpoint (`--api-url` / `--api-key-env` flags).
- **Equivalence check:** on the 17 calls finished on Groq in round 1, Groq and Fireworks gave identical outputs on 15/17, with the same accuracy. That is the same agreement level as two runs on one provider.
- **Earlier dev iterations** (v1, v2) ran on Groq.
- **Reliability on Groq:** the client honours Groq's `retry-after` headers and daily-quota messages (it waits up to `--max-daily-wait` before falling back). The final setup needs about 1.7M tokens for 50 calls, so it needs a paid Groq tier. On that tier, `python run.py --input … --output …` runs unchanged.
