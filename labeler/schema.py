"""Intermediate "facts" schema the LLM fills, plus validation/normalisation.

The LLM answers small, evidence-backed questions. It never outputs the final labels;
labeler/decide.py combines these facts deterministically.
"""
from __future__ import annotations

import copy

DAY_REFS = ["none", "today", "tomorrow", "day_after_tomorrow", "in_n_days", "weekday", "this_weekday",
            "next_weekday", "next_week", "explicit_date", "in_n_months", "next_month"]
WEEKDAY_ENUM = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
MERIDIEM = ["am", "pm"]
PARTS = ["morning", "afternoon", "evening", "lunch", "night"]

INVALID_REASONS = ["wrong_contact", "no_pain_need", "outside_service_area", "policy_exclusion", "test_enquiry"]
REFUSALS = ["none", "explicit_refusal", "do_not_contact"]
BLOCKERS = ["family_discussion", "cost_concern", "travel_constraint", "current_treatment", "treatment_concern"]
INTEREST = ["committed", "considering", "exploratory_only", "refused", "unclear"]


def _nullable(t, enum=None):
    s = {"type": [t, "null"]}
    if enum:
        s["enum"] = enum + [None]
    return s


TIME_SLOT = {
    "type": "object",
    "properties": {
        "words": {"type": "string"},
        "relative_minutes": _nullable("integer"),
        "day_ref": {"type": "string", "enum": DAY_REFS},
        "n": _nullable("integer"),
        "weekday": _nullable("string", WEEKDAY_ENUM),
        "day": _nullable("integer"),
        "month": _nullable("integer"),
        "year": _nullable("integer"),
        "hour": _nullable("integer"),
        "minute": _nullable("integer"),
        "meridiem": _nullable("string", MERIDIEM),
        "part_of_day": _nullable("string", PARTS),
    },
    "required": ["words", "relative_minutes", "day_ref", "n", "weekday", "day", "month", "year",
                 "hour", "minute", "meridiem", "part_of_day"],
    "additionalProperties": False,
}


def _obj(props: dict) -> dict:
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}


FACTS_SCHEMA = _obj({
    "patient_need": _obj({
        "evidence": {"type": "string"},
        "relevant_pain_need": {"type": "string", "enum": ["yes", "no", "unclear"]},
    }),
    "assessable": _obj({
        "evidence": {"type": "string"},
        "meaningful_conversation": {"type": "boolean"},
    }),
    "invalid": _obj({
        "evidence": {"type": "string"},
        "reasons": {"type": "array", "items": {"type": "string", "enum": INVALID_REASONS}},
    }),
    "refusal": _obj({
        "evidence": {"type": "string"},
        "final": {"type": "string", "enum": REFUSALS},
    }),
    "appointment": _obj({
        "evidence": {"type": "string"},
        "confirmed": {"type": "boolean"},
        "online": {"type": "boolean"},
        "reschedule": {"type": "boolean"},
        "slot": TIME_SLOT,
    }),
    "blockers": _obj({
        "evidence": {"type": "string"},
        "open": {"type": "array", "items": {"type": "string", "enum": BLOCKERS}},
        "main": {"type": "string", "enum": ["none"] + BLOCKERS},
    }),
    "information_review": _obj({
        "evidence": {"type": "string"},
        "present": {"type": "boolean"},
    }),
    "vague_postponement": _obj({
        "evidence": {"type": "string"},
        "present": {"type": "boolean"},
    }),
    "callback": _obj({
        "proposal": {"type": "string"},
        "acknowledgement": {"type": "string"},
        "agreed": {"type": "boolean"},
        "slot": TIME_SLOT,
    }),
    "lead": _obj({
        "evidence": {"type": "string"},
        "interest": {"type": "string", "enum": INTEREST},
        "defers_over_30_days": {"type": "boolean"},
    }),
})

EMPTY_SLOT = {k: None for k in TIME_SLOT["properties"]}
EMPTY_SLOT.update({"words": "", "day_ref": "none"})


def _enum(v, allowed, default):
    v = (v or "").strip().lower() if isinstance(v, str) else v
    return v if v in allowed else default


def _slot(s) -> dict:
    out = copy.deepcopy(EMPTY_SLOT)
    if isinstance(s, dict):
        for k in out:
            if k in s:
                out[k] = s[k]
    out["day_ref"] = _enum(out.get("day_ref"), DAY_REFS, "none")
    out["weekday"] = _enum(out.get("weekday"), WEEKDAY_ENUM, None)
    out["meridiem"] = _enum(out.get("meridiem"), MERIDIEM, None)
    out["part_of_day"] = _enum(out.get("part_of_day"), PARTS, None)
    return out


def _b(v) -> bool:
    if isinstance(v, str):
        return v.strip().lower() in ("true", "yes", "1")
    return bool(v)


def normalise_facts(raw: dict) -> dict:
    """Coerce an LLM facts object into a well-formed dict (tolerant of minor schema drift)."""
    g = lambda *ks: _dig(raw, ks)
    return {
        "patient_need": {"evidence": str(g("patient_need", "evidence") or ""),
                         "relevant_pain_need": _enum(g("patient_need", "relevant_pain_need"), ["yes", "no", "unclear"], "unclear")},
        "assessable": {"evidence": str(g("assessable", "evidence") or ""),
                       "meaningful_conversation": _b(g("assessable", "meaningful_conversation"))},
        "invalid": {"evidence": str(g("invalid", "evidence") or ""),
                    "reasons": [r for r in (g("invalid", "reasons") or []) if r in INVALID_REASONS]},
        "refusal": {"evidence": str(g("refusal", "evidence") or ""),
                    "final": _enum(g("refusal", "final"), REFUSALS, "none")},
        "appointment": {"evidence": str(g("appointment", "evidence") or ""),
                        "confirmed": _b(g("appointment", "confirmed")),
                        "online": _b(g("appointment", "online")),
                        "reschedule": _b(g("appointment", "reschedule")),
                        "slot": _slot(g("appointment", "slot"))},
        "blockers": {"evidence": str(g("blockers", "evidence") or ""),
                     "open": [b for b in (g("blockers", "open") or []) if b in BLOCKERS],
                     "main": _enum(g("blockers", "main"), ["none"] + BLOCKERS, "none")},
        "information_review": {"evidence": str(g("information_review", "evidence") or ""),
                               "present": _b(g("information_review", "present"))},
        "vague_postponement": {"evidence": str(g("vague_postponement", "evidence") or ""),
                               "present": _b(g("vague_postponement", "present"))},
        "callback": {"proposal": str(g("callback", "proposal") or ""),
                     "acknowledgement": str(g("callback", "acknowledgement") or ""),
                     "agreed": _b(g("callback", "agreed")),
                     "slot": _slot(g("callback", "slot"))},
        "lead": {"evidence": str(g("lead", "evidence") or ""),
                 "interest": _enum(g("lead", "interest"), INTEREST, "unclear"),
                 "defers_over_30_days": _b(g("lead", "defers_over_30_days"))},
    }


def _dig(d, keys):
    for k in keys:
        if not isinstance(d, dict):
            return None
        d = d.get(k)
    return d


# ---- final output contract ----
DISPOSITION_PAIRS = {
    "Appointment Scheduled": ["Clinic Visit", "Online Consultation", "Rescheduled"],
    "Follow-up Required": ["Specific Callback", "Vague Deferral", "Family Discussion", "Cost Concern", "Travel Constraint",
                           "Current Treatment", "Treatment Concern", "Information Requested", "Further Discussion"],
    "Not Interested": ["Explicit Refusal", "Do Not Contact"],
    "Invalid Lead": ["Wrong Contact", "No Pain Need", "Outside Service Area", "Policy Exclusion", "Test Enquiry"],
    "Unable to Assess": ["Incomplete Conversation"],
}
LEAD_QUALITY = ["High", "Medium", "Low", "Not Qualified", "Not Assessable"]
OUTPUT_KEYS = ["transcript_id", "disposition", "sub_disposition", "lead_quality", "next_call_at"]


def validate_output(o: dict) -> list[str]:
    """Return a list of contract violations (empty list = valid)."""
    import re
    errs = []
    if list(o) != OUTPUT_KEYS:
        errs.append(f"keys {list(o)} != {OUTPUT_KEYS}")
    if o.get("disposition") not in DISPOSITION_PAIRS:
        errs.append(f"bad disposition {o.get('disposition')!r}")
    elif o.get("sub_disposition") not in DISPOSITION_PAIRS[o["disposition"]]:
        errs.append(f"invalid pair {o.get('disposition')!r}/{o.get('sub_disposition')!r}")
    if o.get("lead_quality") not in LEAD_QUALITY:
        errs.append(f"bad lead_quality {o.get('lead_quality')!r}")
    nc = o.get("next_call_at")
    if nc is not None and not (isinstance(nc, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+05:30", nc)):
        errs.append(f"bad next_call_at {nc!r}")
    return errs
