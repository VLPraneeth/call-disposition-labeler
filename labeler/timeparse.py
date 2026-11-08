"""Deterministic calendar resolution for callback / appointment time slots.

The LLM never does date arithmetic. It only normalises the words it heard into a
small "time slot" structure (see labeler/schema.py, TIME_SLOT). This module turns
that structure into an exact timestamp relative to call_started_at, following the
policy rules F1-F12 of assignment-v2.

All arithmetic is in calendar days in Asia/Kolkata (fixed +05:30; India has no DST,
so no tz database is needed - this keeps the runner dependency-free on Windows too).
"""
from __future__ import annotations

import calendar
import re
from datetime import date, datetime, time, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

# F5 named parts of day
PART_OF_DAY_DEFAULT = {"morning": (10, 0), "afternoon": (15, 0), "evening": (18, 0), "lunch": (13, 0), "night": (18, 0)}
DEFAULT_DAY_TIME = (11, 0)  # F5: agreed calendar day with no time


def parse_call_time(call_started_at: str) -> datetime:
    """Parse the input timestamp and express it in IST (F1)."""
    dt = datetime.fromisoformat(call_started_at.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=IST)
    return dt.astimezone(IST)


def format_ts(dt: datetime | None) -> str | None:
    """ISO 8601 with seconds and +05:30, or None (F1)."""
    if dt is None:
        return None
    return dt.astimezone(IST).replace(microsecond=0).isoformat(timespec="seconds")


def _int(v):
    try:
        return int(v) if v is not None and str(v).strip() != "" else None
    except (TypeError, ValueError):
        return None


def resolve_clock(slot: dict) -> tuple[int, int] | None:
    """Return (hour, minute) in 24h from a slot, or None if no time-of-day was given (F5)."""
    hour, minute = _int(slot.get("hour")), _int(slot.get("minute")) or 0
    meridiem = (slot.get("meridiem") or "").lower() or None
    part = (slot.get("part_of_day") or "").lower() or None
    if part not in PART_OF_DAY_DEFAULT:
        part = None
    if hour is None:
        return PART_OF_DAY_DEFAULT[part] if part else None
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        return None
    if hour >= 13 or hour == 0:  # already 24h clock
        return hour, minute
    # Explicit AM/PM wins, then explicit part of day, then the 1-7 PM / 8-11 AM / 12 noon default.
    if meridiem == "pm":
        return (hour % 12) + 12, minute
    if meridiem == "am":
        return hour % 12, minute
    if part in ("afternoon", "evening", "night"):
        return (hour % 12) + 12, minute
    if part == "lunch":
        return (hour % 12) + 12 if hour <= 7 or hour == 12 else hour, minute
    if part == "morning":
        return hour % 12, minute
    if 1 <= hour <= 7:
        return hour + 12, minute
    return hour, minute  # 8-11 AM, 12 noon


def _add_months(d: date, n: int) -> date:
    y, m = divmod(d.month - 1 + n, 12)
    y, m = d.year + y, m + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def resolve_date(slot: dict, call: datetime, clock: tuple[int, int] | None) -> date | None:
    """Resolve the calendar day of a slot (F4, F6, F11). Returns None when vague/unresolvable."""
    ref = (slot.get("day_ref") or "none").lower()
    today = call.date()
    n = _int(slot.get("n"))
    wd_name = (slot.get("weekday") or "").lower()
    wd = WEEKDAYS.index(wd_name) if wd_name in WEEKDAYS else None

    if ref == "today":
        return today
    if ref == "tomorrow":
        return today + timedelta(days=1)
    if ref == "day_after_tomorrow":
        return today + timedelta(days=2)
    if ref == "in_n_days":
        return today + timedelta(days=n) if n is not None and n >= 0 else None
    if ref == "weekday" and wd is not None:  # bare weekday: nearest strictly future occurrence
        delta = (wd - today.weekday()) % 7
        return today + timedelta(days=delta or 7)
    if ref == "this_weekday" and wd is not None:  # today or later, with future time
        delta = (wd - today.weekday()) % 7
        d = today + timedelta(days=delta)
        if delta == 0:
            hh, mm = clock or DEFAULT_DAY_TIME
            if datetime.combine(d, time(hh, mm), IST) <= call:
                d += timedelta(days=7)
        return d
    if ref == "next_weekday" and wd is not None:  # occurrence in the following Mon-Sun week
        next_monday = today + timedelta(days=7 - today.weekday())
        return next_monday + timedelta(days=wd)
    if ref == "next_week":  # next week alone -> next Monday
        return today + timedelta(days=7 - today.weekday())
    if ref == "explicit_date":
        day, month, year = _int(slot.get("day")), _int(slot.get("month")), _int(slot.get("year"))
        if day is None:
            return None
        if month is None:  # "on the 26th": this month, else next month (next future occurrence)
            for k in range(0, 3):
                cand_m = _add_months(today.replace(day=1), k)
                if day <= calendar.monthrange(cand_m.year, cand_m.month)[1]:
                    cand = cand_m.replace(day=day)
                    if cand >= today:
                        return cand
            return None
        try:
            if year is not None:
                return date(year, month, day)  # may be past -> rejected later (F6)
            cand = date(today.year, month, day)
            return cand if cand >= today else date(today.year + 1, month, day)
        except ValueError:
            return None
    if ref == "in_n_months":
        return _add_months(today, n if n is not None and n > 0 else 1)
    if ref == "next_month":
        return _add_months(today.replace(day=1), 1)
    return None


_NUM_WORDS = {"one": 1, "a": 1, "an": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
              "eight": 8, "nine": 9, "ten": 10, "fifteen": 15, "twenty": 20, "thirty": 30, "forty-five": 45}


def _num(tok: str) -> int | None:
    return int(tok) if tok.isdigit() else _NUM_WORDS.get(tok)


def repair_slot(slot: dict | None) -> dict | None:
    """Fill fields the LLM left empty from the verbatim `words` of the slot.

    The model sometimes quotes the time correctly ("26th", "parso shaam") but leaves the
    structured fields incomplete. This deterministic backup only FILLS missing fields; it never
    overrides a value the model set. Unbounded "after <date/event>" phrases stay vague (F10).
    """
    if not slot:
        return slot
    s = dict(slot)
    w = (s.get("words") or "").lower()
    if not w:
        return s
    unbounded_after = re.search(r"\bafter\b(?!\s+(tomorrow|\d+\s*(days?|hours?|minutes?|mins?)))", w) is not None
    ref = s.get("day_ref") or "none"

    if s.get("relative_minutes") is None:
        m = re.search(r"\b(?:in|after)\s+(half an hour|\d+|an?|one|two|three|four|five|ten|fifteen|twenty|thirty|forty-five)\s*(minutes?|mins?|hours?|hrs?)\b", w)
        if m:
            if m.group(1) == "half an hour":
                s["relative_minutes"] = 30
            elif _num(m.group(1)) is not None:
                n = _num(m.group(1))
                s["relative_minutes"] = n * 60 if m.group(2).startswith("h") else n
        elif "half an hour" in w or "half hour" in w:
            s["relative_minutes"] = 30

    needs_day = ref == "none" or (ref == "explicit_date" and s.get("day") is None) or \
        (ref in ("weekday", "this_weekday", "next_weekday") and not s.get("weekday")) or \
        (ref in ("in_n_days", "in_n_months") and s.get("n") is None)
    if needs_day and not unbounded_after:
        wd = re.search(r"\b(next|this|coming)?\s*(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", w)
        dnum = re.search(r"\b(\d{1,2})\s*(st|nd|rd|th)\b", w)
        ndays = re.search(r"\b(?:in|after)\s+(\d+|one|two|three|four|five|six|seven|ten)\s+days?\b", w)
        if ref in ("explicit_date", "none") and dnum:
            s.update(day_ref="explicit_date", day=int(dnum.group(1)))
        elif wd:
            s["weekday"] = wd.group(2)
            if ref not in ("weekday", "this_weekday", "next_weekday"):
                s["day_ref"] = {"next": "next_weekday", "this": "this_weekday"}.get(wd.group(1), "weekday")
        elif ndays and _num(ndays.group(1)) is not None:
            s.update(day_ref="in_n_days", n=_num(ndays.group(1)))
        elif ref == "none":
            if "day after tomorrow" in w or "parso" in w:
                s["day_ref"] = "day_after_tomorrow"
            elif "tomorrow" in w or re.search(r"\bkal\b", w):
                s["day_ref"] = "tomorrow"
            elif re.search(r"\b(today|tonight|this evening|this afternoon|this morning|aaj)\b", w):
                s["day_ref"] = "today"
            elif re.fullmatch(r"\s*(on\s+)?next week\s*", w):
                s["day_ref"] = "next_week"

    if s.get("part_of_day") is None:
        for pat, part in ((r"morning|subah", "morning"), (r"afternoon|dopahar", "afternoon"),
                          (r"evening|shaam|sham\b", "evening"), (r"tonight|night|raat", "night"), (r"lunch", "lunch")):
            if re.search(pat, w):
                s["part_of_day"] = part
                break
    if s.get("hour") is None and s.get("relative_minutes") is None:
        m = re.search(r"\b(\d{1,2})(?:[:.](\d{2}))?\s*(a\.?m\.?|p\.?m\.?|o'?clock|baje)", w)
        if m:
            s["hour"] = int(m.group(1))
            s["minute"] = int(m.group(2)) if m.group(2) else s.get("minute")
            if s.get("meridiem") is None and m.group(3)[0] in "ap":
                s["meridiem"] = "am" if m.group(3)[0] == "a" else "pm"
    return s


def resolve_slot(slot: dict | None, call_started_at: str) -> str | None:
    """Resolve a time slot to an ISO timestamp strictly after the call, or None.

    None means: no valid specific time (vague, unresolvable or in the past). The caller
    then applies the fallback rules (F7/F8); a past explicit commitment is never repaired (F6).
    """
    if not slot:
        return None
    call = parse_call_time(call_started_at)

    rel = _int(slot.get("relative_minutes"))
    if rel is not None and rel > 0:  # F10: "in N minutes/hours", seconds preserved
        return format_ts(call + timedelta(minutes=rel))

    clock = resolve_clock(slot)
    ref = (slot.get("day_ref") or "none").lower()
    if ref == "none":
        if clock is None:
            return None
        d = call.date()  # F5: time only -> today if still future, else tomorrow
        if datetime.combine(d, time(*clock), IST) <= call:
            d += timedelta(days=1)
    else:
        d = resolve_date(slot, call, clock)
        if d is None:
            return None
    hh, mm = clock if clock is not None else DEFAULT_DAY_TIME
    if ref == "next_month" and clock is None:
        hh, mm = DEFAULT_DAY_TIME
    dt = datetime.combine(d, time(hh, mm), IST)
    return format_ts(dt) if dt > call else None  # F6/F9: must be future


def day_offset(slot: dict | None, call_started_at: str) -> int | None:
    """Calendar-date offset of a slot from the call date (0 = same day). Used for lead quality."""
    if not slot:
        return None
    call = parse_call_time(call_started_at)
    rel = _int(slot.get("relative_minutes"))
    if rel is not None and rel > 0:
        return ((call + timedelta(minutes=rel)).date() - call.date()).days
    clock = resolve_clock(slot)
    ref = (slot.get("day_ref") or "none").lower()
    if ref == "none":
        if clock is None:
            return None
        return 0 if datetime.combine(call.date(), time(*clock), IST) > call else 1
    d = resolve_date(slot, call, clock)
    return None if d is None else (d - call.date()).days
