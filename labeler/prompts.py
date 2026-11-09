"""Prompt templates (complete, versioned). The LLM extracts evidence-backed facts only;
labels are derived in labeler/decide.py.
"""

PROMPT_VERSION = "p3"   # default; see PROMPTS below for the tested variants

SYSTEM_PROMPT = """You analyse one phone call between the enrollment team of Aster Vale Pain Clinic (an Indian pain clinic) and a prospect. The team books consultations with pain specialists for the caller or a family member (the "intended patient"). Transcripts are translated from Hindi/English; speaker labels may be wrong, so infer who is the agent (clinic) and who is the customer from what they say. Agent claims are not facts.

Return ONLY a JSON object with the facts below. Do not output labels. Judge everything by the FINAL operative state at the end of the call: later corrections, reversals and amendments replace earlier statements. Each "evidence" / "proposal" / "acknowledgement" field is a short verbatim quote (max ~25 words, "" if none).

FACTS
patient_need.relevant_pain_need: "yes" if the intended patient has an actual pain/pain-care need; "no" only with reliable evidence of no pain-care need; "unclear" if it cannot be established.
assessable.meaningful_conversation: false only for silence, immediate disconnect, unresolved identity or unintelligible dialogue. A long unresolved discussion of a pain need is meaningful.
invalid.reasons (usually []): "wrong_contact" (reliably the wrong person/number; a caregiver enquiring for a patient is NOT wrong contact), "no_pain_need", "test_enquiry" (explicit internal test/demo/fake), "policy_exclusion" (intended patient known to be under 15; nothing else), "outside_service_area" (lives permanently outside all served areas AND travel AND remote care are explicitly unavailable/refused; distance alone is not enough). Missing age or pain duration is never a reason.
refusal.final: "do_not_contact" if the customer finally asks to stop calling / remove the number; "explicit_refusal" if a valid prospect finally and unconditionally rejects the clinic's offering (e.g. hangs up saying "I don't want it"); else "none". A rejected date, price objection, "let me think", treatment elsewhere, or rejecting one particular treatment type while leaving the door open ("I don't want injections; I'll call you if I want to come") is NOT a refusal - those are conditional. A refusal later reversed by clear commitment is "none".
appointment.confirmed: true only if, at the end, both sides confirm an actual consultation on a specific date AND a clock time or bounded window (e.g. "book 2:20 tomorrow" + "okay"; "Sunday between 3 and 4"). NOT confirmed: offers, listing available slots, "I will come tomorrow/Monday" without an agreed time, a visit intention, asking for the address, or "we will call to confirm the time". appointment.online: the confirmed consultation is remote (video/phone). appointment.reschedule: it replaces an existing or missed appointment. appointment.slot: the consultation's day/time (fill even if not confirmed, else defaults).
blockers.open: the reasons the customer gave for not committing now that are still unresolved at the end. Scan the WHOLE call: the reason is often stated mid-call (e.g. "I'm out of town", "office meetings", "surgery was suggested, can this cure the root cause?") while the ending only says "I'll see / I'll call you". A reason counts unless it was clearly resolved later.
 - family_discussion: whether to go ahead waits on a family member's discussion, approval or decision ("I'll consult my family/mother and then decide"). Checking whether the patient or a relative can get time off / manage their schedule is NOT family_discussion (it is travel_constraint), even when the caller says "I'll ask my wife/son".
 - cost_concern: affordability, payment, money not available yet, insurance uncertainty.
 - travel_constraint: logistics/availability: patient or customer away/out of town, distance, long journey, transport, work/office/business/shop commitments, needing leave, clinic timing or doctor days not fitting, waiting for a holiday or for someone free to accompany them, or arranging a family member's work schedule (service still feasible). Coordinating someone's availability is travel_constraint, not family_discussion.
 - current_treatment: wants to finish or assess another ongoing treatment (physiotherapy, medicines elsewhere) first.
 - treatment_concern: doubts, fears or mistrust about the treatment, procedure, injections/steroids, whether it can fix the root cause or avoid surgery, doctor suitability or outcome; or waiting for the clinic/doctor to review reports to decide suitability. A neutral request for information (e.g. doctor profiles) without doubt is NOT a treatment_concern.
 An agreed callback does NOT remove a blocker: if the customer said why they cannot come now (e.g. out of town until next week), that reason stays in blockers.open even when a callback date is fixed.
 Merely preferring a later day without giving any reason is NOT a blocker. A price question that was answered and then the customer committed is NOT open.
blockers.main: from blockers.open, the reason that most directly explains why the consultation is not booked now / what the final next step waits on, as the customer emphasises it ("none" if open is empty). If several are truly equally primary, pick the one listed first above.
information_review.present: the CUSTOMER asked for specific non-routine information (doctor profiles, treatment/procedure details, report review) and their final next step is to review it before deciding. Information merely offered by the agent, or routine address/location/contact-number sharing, does NOT count.
vague_postponement.present: at the end the customer explicitly postpones without an agreed resolvable callback day/time: "I'll think", "I'll see", "I need time", "I'll let you know", "I'll call you / get in touch", "call later", "after Diwali/the event", "after the 22nd" (unbounded), "next week or the week after" for the visit, "I'll discuss with family and decide", "not now, maybe in a month". An agent's routine "I'll call you"/"I'll send details" alone is NOT a postponement; a call that simply ends while discussing is NOT one.
callback: the FINAL agreed future phone conversation between clinic and customer (either direction: "I'll call you on Wednesday", "call me this evening", "I will tell you in 15 minutes").
 - callback.agreed = true only if (a) the time is specific: a resolvable calendar day and/or clock time, or "in N minutes/hours"; (b) one party proposed it and the other acknowledged it (okay / haan / theek hai / sure / fine / yes, or clearly accepted it); (c) it was not later rejected, replaced by a vague postponement, or cancelled. An acknowledged amendment replaces the earlier time.
 - "Should I call you next week?" + "yes" IS agreed (day_ref next_week), even if the visit itself is later; "next week after <unresolved event>" is vague.
 - NOT a callback: the consultation slot itself, sending info/WhatsApp at a time, clinic opening hours, "you may receive a call", "call me when you reach", a customer saying a time with no acknowledgement, an agent proposal the customer ignored. A definite "I will call you tomorrow (to confirm)" + acknowledgement IS a callback, even with a booked appointment.
 - callback.slot describes the final agreed callback time (defaults if none). Always fill the structured fields (e.g. "26th" -> day_ref "explicit_date", day 26), not only "words".
lead.interest: "committed" (accepted a consultation), "considering" (genuine interest but undecided/blocked/unconfirmed), "exploratory_only" (no current intent to consult: just enquiring/curious, rejects the proposed treatment, or will only get in touch "if I want/need to", e.g. "I don't want that treatment, I'll call you if I want to come"), "refused", "unclear" (cannot tell whether the intended patient needs or wants care). Pain severity alone is not intent.
lead.defers_over_30_days: the customer puts off consulting by more than 30 days (e.g. "after a month or two").

TIME SLOT (normalise words; do NOT do date arithmetic)
words: the exact time words used. relative_minutes: for "in 15 minutes" -> 15, "in half an hour" -> 30, "in 2 hours" -> 120, else null.
day_ref: "today" (today / this evening / tonight), "tomorrow" (kal, forward-looking), "day_after_tomorrow" (parso), "in_n_days" (in/after N days -> n=N), "weekday" (bare weekday e.g. "Wednesday"), "this_weekday" ("this Friday"), "next_weekday" ("next Friday"), "next_week" ("next week" with no day), "explicit_date" (e.g. "26th", "26 October" -> day, month, year if said), "in_n_months" ("in/after one month" -> n=1), "next_month" (bare "next month"), "none" (no day given, or vague: "later", "this week", "after Diwali", "after the 22nd").
hour/minute: the clock time exactly as spoken in 12h form (4 o'clock -> 4; 10:20 -> 10, 20); for "between 3 and 4" or "after 4" or "around 4" use the first time. Do not convert to 24h. meridiem: "am"/"pm" only if explicitly said. part_of_day: morning / afternoon / evening / lunch / night if said. Unused fields: null."""

# p7: same facts as p3, plus one final field where the model picks the Follow-up
# sub-disposition from the OFFICIAL policy definitions (verbatim, not paraphrased).
FOLLOWUP_ADDON = """

FOLLOW-UP SUB-DISPOSITION (fill this LAST, after all facts above)
followup.label: if the call ends open (no confirmed appointment, no final refusal, not invalid), the sub-disposition under the clinic's official policy. If the call is not open, give the best fit anyway. Official policy text:
D4: Meaningful relevant discussion remains open without a final confirmed appointment, invalidity, or firm refusal. Select the final stated main unresolved blocker, not every historical objection.
 - Family Discussion: A family member's discussion, approval or decision is the final main unresolved next step.
 - Cost Concern: Affordability, payment or insurance uncertainty is the final main unresolved blocker.
 - Travel Constraint: Travel, temporary absence, distance, transport, work or clinic timing prevents commitment; service is still potentially feasible.
 - Current Treatment: Prospect is waiting to finish or assess another current treatment before deciding.
 - Treatment Concern: Unresolved questions or mistrust about treatment, procedure, clinician suitability, injections or outcome prevent commitment.
 - Specific Callback: No named blocker dominates and a future callback with at least a resolvable calendar day or clock time is mutually acknowledged.
 - Information Requested: No named blocker dominates and prospect's final next step is to review requested information or reports; merely sending routine location details does not qualify.
 - Vague Deferral: No named blocker dominates and final response postpones discussion without an agreed resolvable day/time: later, sometime, think about it, or customer will call back without a date.
 - Further Discussion: Relevant open enquiry has none of the above final next steps or blockers.
Tie-breaking: Use the customer's final explicitly primary reason. If several remain equally primary, use Family Discussion, Cost Concern, Travel Constraint, Current Treatment, Treatment Concern in that order; then Specific Callback, Information Requested, Vague Deferral, Further Discussion.
followup.evidence: the customer's final words that decide the label (verbatim quote)."""

# p8: p7 plus the official next-call fallback wording, deciding vague (+3 days) vs none (+1 day).
NEXT_STEP_ADDON = """

NEXT STEP (fill this LAST)
next_step.kind: how the call's next conversation was left at the END, per the clinic's official policy:
 "specific_callback": a final future callback with a resolvable day or clock time, proposed by either party and acknowledged by the other (even by okay/haan/theek hai).
 "vague_postponement": F7: When no valid specific callback exists, ANY final explicit vague postponement such as call later, let me think, after the family event, or the customer will call when able. F12: Next week qualified by an unresolved event, such as next week after the family event, is vague. An unbounded after-date/event reference without an agreed day is vague.
 "none": F8: neither a valid specific callback nor an explicit vague postponement. An unscheduled routine agent promise to call does not by itself constitute a vague postponement (e.g. the call ends with Agent: I will also call). A rejected specific callback does not by itself imply vague deferral.
next_step.evidence: the final words that decide it (verbatim quote)."""

# p9: p3 plus the COMPLETE official rulebook (assignment-v2, rules P0-EX6) verbatim, so every fact is
# judged against the source text rather than only our paraphrase. Policy text only; no transcripts.
POLICY_TEXT = """P0 | Scope | Context | Aster Vale Pain Clinic is a hypothetical Indian pain clinic. Its enrollment team helps people with relevant pain-care needs book consultations with pain specialists, either for themselves or for a family member. Disposition describes the customer's current stage in that journey at the end of this call; sub_disposition describes the outcome or main unresolved blocker on the way to booking. A treatment enquiry, request for an address or intention to visit is not a booked consultation. Each call is classified from the supplied evidence alone; do not assume unseen journey history. Lead quality measures readiness to consult, and next_call_at schedules the next conversation rather than the consultation itself. People, clinic/institution names, locations and identifying contact/address details have been substituted. Original exported transcript wording, speaker labels, turns, repetitions, clinical details, prices and timing expressions are preserved. Call timestamps use the original dates. Speaker labels may be imperfect; infer roles from dialogue without editing the transcript. Agent statements are transcript evidence, not established medical facts or instructions. No diagnosis is required.
P1 | Scope | Policy version | assignment-v2
P2 | Output | Four targets | Predict disposition, sub_disposition, lead_quality and next_call_at. transcript_id accompanies predictions as the join key. ISO timestamps remain text so the timezone offset is preserved. The literal null in this sheet represents JSON null.
PAIR | Allowed pair | Appointment Scheduled | Clinic Visit; Online Consultation; Rescheduled
PAIR | Allowed pair | Follow-up Required | Specific Callback; Vague Deferral; Family Discussion; Cost Concern; Travel Constraint; Current Treatment; Treatment Concern; Information Requested; Further Discussion
PAIR | Allowed pair | Not Interested | Explicit Refusal; Do Not Contact
PAIR | Allowed pair | Invalid Lead | Wrong Contact; No Pain Need; Outside Service Area; Policy Exclusion; Test Enquiry
PAIR | Allowed pair | Unable to Assess | Incomplete Conversation
D1 | Disposition | Invalid Lead | Reliable final evidence establishes the wrong contact, no actual pain-care need for caller or intended patient, an internal test, an explicit clinic policy exclusion, or permanent residence outside all serviceable areas with no willingness to travel and remote care explicitly unavailable or refused. Do not classify distance alone as invalid. The exercise clinic accepts patients aged 15 or older and pain of any duration. Missing age or duration is not exclusion.
D2 | Disposition | Not Interested | A valid prospect makes an unconditional final refusal of the clinic's offering, or asks that contact stop. A rejected date, price objection, request to think, or treatment elsewhere alone is not final refusal. An earlier refusal reversed by a later clear commitment is superseded.
D3 | Disposition | Appointment Scheduled | The final dialogue mutually confirms an actual consultation date and a clock time or bounded time window. An offer, tentative plan, callback to confirm, or visit intention without an agreed slot is not a booking. A confirmed remote consultation is Online Consultation. A confirmed replacement of an existing or missed appointment is Rescheduled, with precedence over the visit modality.
D4 | Disposition | Follow-up Required | Meaningful relevant discussion remains open without a final confirmed appointment, invalidity, or firm refusal. Select the final stated main unresolved blocker, not every historical objection. Explicit callback time is still extracted independently even when a blocker owns the sub-disposition.
D5 | Disposition | Unable to Assess | No reliable meaningful evidence establishes a relevant outcome: silence, immediate disconnect, unresolved identity or unintelligible dialogue. A long but unresolved discussion of a known pain need is Follow-up Required, not Unable to Assess.
D6 | Disposition | Outcome precedence | Use final reliable evidence after corrections. If simultaneously applicable: Invalid Lead before Not Interested before Appointment Scheduled before Follow-up Required before Unable to Assess. Never carry a label from unseen history or CRM state.
SUB | Sub-disposition | Appointment Scheduled: Clinic Visit | Confirmed new in-person consultation.
SUB | Sub-disposition | Appointment Scheduled: Online Consultation | Confirmed new remote consultation.
SUB | Sub-disposition | Appointment Scheduled: Rescheduled | Confirmed replacement slot for a previously scheduled or missed consultation.
SUB | Sub-disposition | Follow-up Required: Family Discussion | A family member's discussion, approval or decision is the final main unresolved next step.
SUB | Sub-disposition | Follow-up Required: Cost Concern | Affordability, payment or insurance uncertainty is the final main unresolved blocker.
SUB | Sub-disposition | Follow-up Required: Travel Constraint | Travel, temporary absence, distance, transport, work or clinic timing prevents commitment; service is still potentially feasible.
SUB | Sub-disposition | Follow-up Required: Current Treatment | Prospect is waiting to finish or assess another current treatment before deciding.
SUB | Sub-disposition | Follow-up Required: Treatment Concern | Unresolved questions or mistrust about treatment, procedure, clinician suitability, injections or outcome prevent commitment.
SUB | Sub-disposition | Follow-up Required: Specific Callback | No named blocker dominates and a future callback with at least a resolvable calendar day or clock time is mutually acknowledged.
SUB | Sub-disposition | Follow-up Required: Information Requested | No named blocker dominates and prospect's final next step is to review requested information or reports; merely sending routine location details does not qualify.
SUB | Sub-disposition | Follow-up Required: Vague Deferral | No named blocker dominates and final response postpones discussion without an agreed resolvable day/time: later, sometime, think about it, or customer will call back without a date.
SUB | Sub-disposition | Follow-up Required: Further Discussion | Relevant open enquiry has none of the above final next steps or blockers.
SUB | Sub-disposition | Not Interested: Explicit Refusal | Unconditional final rejection without a no-contact request.
SUB | Sub-disposition | Not Interested: Do Not Contact | Explicit request to stop calling or remove contact; takes precedence over Explicit Refusal.
SUB | Sub-disposition | Invalid Lead: Wrong Contact | Reliable wrong intended person/number. A caregiver legitimately enquiring for a patient is not wrong contact.
SUB | Sub-disposition | Invalid Lead: No Pain Need | Reliable evidence of no relevant pain-care need for the intended patient.
SUB | Sub-disposition | Invalid Lead: Outside Service Area | Permanently unserviceable with travel and remote-care paths explicitly unavailable or refused.
SUB | Sub-disposition | Invalid Lead: Policy Exclusion | Known patient under 15. No other exclusion may be inferred.
SUB | Sub-disposition | Invalid Lead: Test Enquiry | Explicit internal test, demo or fabricated enquiry.
SUB | Sub-disposition | Unable to Assess: Incomplete Conversation | Insufficient reliable dialogue to establish a relevant outcome.
SUB | Sub-disposition | All: Tie-breaking | Use the customer's final explicitly primary reason. If several remain equally primary, use Family Discussion, Cost Concern, Travel Constraint, Current Treatment, Treatment Concern in that order; then Specific Callback, Information Requested, Vague Deferral, Further Discussion. For multiple invalid reasons use Test Enquiry, Wrong Contact, No Pain Need, Policy Exclusion, Outside Service Area.
LQ | Lead quality | Not Qualified | Disposition is Invalid Lead. This operational exercise label includes invalid contacts; it is not a clinical judgment.
LQ | Lead quality | Not Assessable | Disposition is Unable to Assess, or relevant discussion occurred but the intended patient's need or willingness cannot be established reliably.
LQ | Lead quality | Low | Valid prospect finally refuses, shows only exploratory curiosity without current intent to consult, or defers more than 30 days without a concrete confirmed appointment. Severe pain alone never upgrades intent.
LQ | Lead quality | High | A real pain need is established; customer explicitly commits to a feasible consultation within seven calendar dates counting the call date as day 1 (date offsets 0–6); there is no final unresolved decision, cost, travel or treatment blocker. A price question resolved before commitment does not prevent High. A callback alone is not consultation commitment.
LQ | Lead quality | Medium | A relevant need and genuine consideration exist but a blocker or unconfirmed visit remains, or a confirmed consultation is on day 8 or later (date offset 7 or more). This is the default for an interested but undecided eligible prospect. Mere curiosity belongs to Low.
LQ | Lead quality | Order | Apply Not Qualified, Not Assessable, Low, High, then Medium. Evaluate the intended patient's case, not the caregiver's symptoms or agent enthusiasm. Pain lasting less than one month is allowed and is not a reason for downgrade.
F1 | Next call | Reference | Use call_started_at in Asia/Kolkata. All additions use calendar days. Never use the date the candidate runs the code. Output ISO 8601 with seconds and +05:30, or JSON null.
F2 | Next call | Suppression | Invalid Lead, Not Interested and Unable to Assess always have next_call_at=null, even if an earlier callback proposal exists.
F3 | Next call | Specific commitment | Otherwise use the FINAL future callback time proposed by either party and acknowledged by the other, even by okay/haan/theek hai. Customer stating a time without an agent acknowledgement is not sufficient. An acknowledged amendment replaces earlier callback times. A consultation slot or sending information at a time is not a callback. An explicit distinct callback can coexist with Appointment Scheduled.
F4 | Next call | Relative days | Tomorrow=+1, day after tomorrow/parso=+2 in forward-looking callback context. In N days=+N. A weekday without this/next means nearest strictly future occurrence. This weekday means nearest occurrence today or later with future time; next weekday means the occurrence in the following Monday–Sunday week. Next week alone means next Monday. This week alone is vague.
F5 | Next call | Date and time defaults | Agreed calendar day with no time=11:00. Time only refers to today if future, otherwise tomorrow. Hours 1–7 without AM/PM mean PM; 8–11 mean AM; 12 means noon. Explicit morning/evening/AM/PM wins. Morning=10:00, afternoon=15:00, evening=18:00, lunch=13:00. A bounded callback window uses its start.
F6 | Next call | Absolute dates and past times | Use explicit dates; a month/day lacking year resolves to its next future occurrence. Reject explicitly past full dates and past same-day times, unacknowledged proposals, rejected alternatives and ambiguous event-only references. Do not silently repair an explicit past commitment into tomorrow.
F7 | Next call | Vague fallback | When no valid specific callback exists, ANY final explicit vague postponement such as call later, let me think, after the family event, or the customer will call when able has fallback call date+3 days at 11:00, regardless of which blocker owns sub_disposition. An unscheduled routine agent promise to call does not by itself constitute a vague postponement. A rejected specific callback does not by itself imply vague deferral.
F8 | Next call | Other fallback | Follow-up Required with neither valid specific callback nor explicit vague deferral gets call date+1 day at 11:00. Appointment Scheduled without a distinct valid explicit callback gets null; appointment reminders are not inferred.
F9 | Next call | Final reconciliation | Use only the final next-step agreement. A final vague cancellation of an earlier specific callback removes that specific time and invokes F7; a final do-not-contact request invokes F2. The final next_call_at must be future relative to call_started_at or null.
F10 | Next call | Intervals and flexible windows | In N minutes/hours resolves from call_started_at with seconds preserved. An acknowledged two-date window or accepted alternatives use the earliest future date/time. For this exercise, after a stated clock time uses that time as the inclusive lower bound. Around a single stated day/time also normalizes to that stated day/time. An unbounded after-date/event reference without an agreed day is vague. Broad visit intentions are never callback times.
F11 | Next call | Months | In/after one month means the same day number in the next calendar month, clamped to its final day, at 11:00 if no time. Bare next month without an already-agreed interval means the first day of next month at 11:00. A loose restatement of an accepted interval does not replace it unless clearly proposed as an amendment.
F12 | Next call | Conditional timing | May receive a call, possible calls, clinic opening hours and contact-person availability are not callback commitments. Next week qualified by an unresolved event, such as next week after the family event, is vague; do not use Monday when a finer event condition remains unresolved. A definite will call tomorrow plus acknowledgment is a commitment even when it is a confirmation call for a booked consultation.
EX1 | Boundary example | Specific versus fallback | Call Monday 2026-11-09 at 14:00. Customer: Call tomorrow at 4. Agent: Okay. next_call_at=2026-11-10T16:00:00+05:30.
EX2 | Boundary example | Vague deferral | Same call date. Customer: I need to think; call later. Agent: Okay. No valid specific callback. next_call_at=2026-11-12T11:00:00+05:30 (+3 calendar days).
EX3 | Boundary example | Appointment is not callback | Same call date. Both confirm tomorrow at 15:00 for a clinic consultation. No distinct callback is agreed. Appointment Scheduled/Clinic Visit; next_call_at=null.
EX4 | Boundary example | Unspecified agent call | Relevant open enquiry ends with Agent: I will also call, without an explicit postponement or agreed time. next_call_at=2026-11-10T11:00:00+05:30 (+1 day).
EX5 | Boundary example | Final no contact | A callback is discussed, then customer finally says: Remove my number; do not call. Not Interested/Do Not Contact; Low; next_call_at=null.
EX6 | Boundary example | Commitment and severity | Severe pain plus undecided family approval is Medium. A feasible accepted consultation on date offsets 0–6 without an unresolved blocker is High. A consultation exactly 7 days later is Medium. Pain severity alone is not readiness."""

FULL_POLICY_ADDON = """

OFFICIAL LABEL POLICY (verbatim, rule | field | option | definition). The final labels are computed from your facts by code that implements exactly these rules, so judge every fact the way this policy would:
""" + POLICY_TEXT

PROMPTS = {"p3": SYSTEM_PROMPT, "p9": SYSTEM_PROMPT + FULL_POLICY_ADDON, "p7": SYSTEM_PROMPT + FOLLOWUP_ADDON,
           "p8": SYSTEM_PROMPT + FOLLOWUP_ADDON + NEXT_STEP_ADDON}

USER_TEMPLATE = """Call started at: {call_started_at} ({weekday}), timezone {timezone}.

TRANSCRIPT
{transcript}

Return the JSON facts object."""
