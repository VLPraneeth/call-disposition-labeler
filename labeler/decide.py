"""Deterministic combination of extracted facts into the four labels (policy assignment-v2).

Every branch cites the rule it implements (D*, SUB, LQ, F*). No rule here is keyed to a
specific transcript; all of it follows the published policy.
"""
from __future__ import annotations

from datetime import datetime, time, timedelta

from .timeparse import IST, day_offset, format_ts, parse_call_time, resolve_slot

# SUB tie-break orders
INVALID_ORDER = ["test_enquiry", "wrong_contact", "no_pain_need", "policy_exclusion", "outside_service_area"]
BLOCKER_ORDER = ["family_discussion", "cost_concern", "travel_constraint", "current_treatment", "treatment_concern"]

INVALID_LABEL = {"test_enquiry": "Test Enquiry", "wrong_contact": "Wrong Contact", "no_pain_need": "No Pain Need",
                 "policy_exclusion": "Policy Exclusion", "outside_service_area": "Outside Service Area"}
BLOCKER_LABEL = {"family_discussion": "Family Discussion", "cost_concern": "Cost Concern",
                 "travel_constraint": "Travel Constraint", "current_treatment": "Current Treatment",
                 "treatment_concern": "Treatment Concern"}


def _days_at_11(call_started_at: str, days: int) -> str:
    call = parse_call_time(call_started_at)
    return format_ts(datetime.combine(call.date() + timedelta(days=days), time(11, 0), IST))


def decide(facts: dict, call_started_at: str) -> dict:
    """Return {'disposition','sub_disposition','lead_quality','next_call_at','trace'}."""
    trace = []
    need = facts["patient_need"]["relevant_pain_need"]
    meaningful = facts["assessable"]["meaningful_conversation"]

    # Invalid reasons, with a consistency guard: "no_pain_need" cannot coexist with an established need.
    invalid = [r for r in facts["invalid"]["reasons"] if not (r == "no_pain_need" and need == "yes")]
    refusal = facts["refusal"]["final"]
    appt = facts["appointment"]
    blockers = facts["blockers"]

    # Specific callback (F3, F4-F6, F10-F12): must be agreed AND resolve to a future timestamp.
    callback_ts = resolve_slot(facts["callback"]["slot"], call_started_at) if facts["callback"]["agreed"] else None
    if facts["callback"]["agreed"] and callback_ts is None:
        trace.append("callback marked agreed but slot unresolvable/past -> not specific (F6)")

    # ---- Disposition: precedence Invalid > Not Interested > Appointment > Follow-up > Unable (D6) ----
    if invalid:
        disp = "Invalid Lead"                                                    # D1
        sub = INVALID_LABEL[min(invalid, key=INVALID_ORDER.index)]               # SUB tie-break
    elif refusal != "none":
        disp = "Not Interested"                                                  # D2
        sub = "Do Not Contact" if refusal == "do_not_contact" else "Explicit Refusal"
    elif appt["confirmed"]:
        disp = "Appointment Scheduled"                                           # D3
        sub = "Rescheduled" if appt["reschedule"] else ("Online Consultation" if appt["online"] else "Clinic Visit")
    elif meaningful or need == "yes":
        disp = "Follow-up Required"                                              # D4 / D5 (known need is never Unable)
        main = blockers["main"] if blockers["main"] != "none" else None
        open_ = [b for b in blockers["open"] if b in BLOCKER_ORDER]
        if main is None and open_:
            main = min(open_, key=BLOCKER_ORDER.index)                           # SUB tie-break among equals
            trace.append(f"no main blocker named; tie-break over {open_}")
        if main:
            sub = BLOCKER_LABEL[main]
        elif callback_ts:
            sub = "Specific Callback"
        elif facts["information_review"]["present"]:
            sub = "Information Requested"
        elif facts["vague_postponement"]["present"]:
            sub = "Vague Deferral"
        else:
            sub = "Further Discussion"
    else:
        disp, sub = "Unable to Assess", "Incomplete Conversation"               # D5

    # ---- Lead quality: Not Qualified > Not Assessable > Low > High > Medium (LQ order) ----
    interest = facts["lead"]["interest"]
    if disp == "Invalid Lead":
        lq = "Not Qualified"
    elif disp == "Unable to Assess" or need == "unclear" or interest == "unclear":
        lq = "Not Assessable"
    elif disp == "Not Interested" or interest in ("refused", "exploratory_only") or \
            (facts["lead"]["defers_over_30_days"] and disp != "Appointment Scheduled"):
        lq = "Low"
    elif disp == "Appointment Scheduled":
        off = day_offset(appt["slot"], call_started_at)
        unresolved = [b for b in blockers["open"] if b in BLOCKER_ORDER]
        if off is not None and off >= 7:
            lq = "Medium"                                                        # EX6: offset 7+ is Medium
            trace.append(f"appointment offset {off} days -> Medium")
        elif unresolved:
            lq = "Medium"
            trace.append(f"appointment but unresolved blockers {unresolved} -> Medium")
        else:
            lq = "High"
            if off is None:
                trace.append("appointment offset unresolved; assumed within 7 days")
    else:
        lq = "Medium"

    # ---- next_call_at (F2, F3, F7, F8, F9) ----
    if disp in ("Invalid Lead", "Not Interested", "Unable to Assess"):
        nca = None                                                               # F2
    elif callback_ts:
        nca = callback_ts                                                        # F3 (also with appointment)
    elif disp == "Appointment Scheduled":
        nca = None                                                               # F8
    elif facts["vague_postponement"]["present"]:
        nca = _days_at_11(call_started_at, 3)                                    # F7
    else:
        nca = _days_at_11(call_started_at, 1)                                    # F8

    return {"disposition": disp, "sub_disposition": sub, "lead_quality": lq, "next_call_at": nca, "trace": trace}
