"""Unit tests for label combination (rules D1-D6, SUB, LQ, F2/F3/F7/F8, boundary examples EX2-EX6)."""
import copy
import unittest

from labeler.decide import decide
from labeler.schema import EMPTY_SLOT, normalise_facts, validate_output

CALL = "2026-11-09T14:00:00+05:30"  # Monday, as in the rulebook examples


def facts(**over):
    f = normalise_facts({
        "patient_need": {"evidence": "knee pain", "relevant_pain_need": "yes"},
        "assessable": {"evidence": "", "meaningful_conversation": True},
        "lead": {"evidence": "", "interest": "considering", "defers_over_30_days": False},
    })
    for path, val in over.items():
        d = f
        keys = path.split("__")
        for k in keys[:-1]:
            d = d[k]
        d[keys[-1]] = val
    return f


def slot(**kw):
    s = copy.deepcopy(EMPTY_SLOT)
    s.update(kw)
    return s


class TestDecide(unittest.TestCase):
    def check(self, f, disp, sub, lq, nca):
        out = decide(f, CALL)
        self.assertEqual((out["disposition"], out["sub_disposition"], out["lead_quality"], out["next_call_at"]),
                         (disp, sub, lq, nca))
        pred = {"transcript_id": "X", **{k: out[k] for k in ("disposition", "sub_disposition", "lead_quality", "next_call_at")}}
        self.assertEqual(validate_output(pred), [])

    def test_need_no_implies_no_pain_need_invalid(self):
        f = facts(patient_need__relevant_pain_need="no")
        self.check(f, "Invalid Lead", "No Pain Need", "Not Qualified", None)

    def test_f12_next_week_after_event_is_vague(self):
        f = facts(callback__proposal="I'll call you next week after Dussehra", callback__acknowledgement="Okay",
                  callback__agreed=False, callback__slot=slot(words="next week after Dussehra", day_ref="next_week"))
        self.check(f, "Follow-up Required", "Vague Deferral", "Medium", "2026-11-12T11:00:00+05:30")

    def test_plain_next_week_is_specific(self):
        f = facts(callback__proposal="Should I call next week?", callback__acknowledgement="Yes",
                  callback__agreed=True, callback__slot=slot(words="next week", day_ref="next_week"))
        self.check(f, "Follow-up Required", "Specific Callback", "Medium", "2026-11-16T11:00:00+05:30")

    def test_ex1_specific_callback(self):
        f = facts(callback__agreed=True, callback__slot=slot(day_ref="tomorrow", hour=4))
        self.check(f, "Follow-up Required", "Specific Callback", "Medium", "2026-11-10T16:00:00+05:30")

    def test_ex2_vague_deferral_plus_3_days(self):
        f = facts(vague_postponement__present=True)
        self.check(f, "Follow-up Required", "Vague Deferral", "Medium", "2026-11-12T11:00:00+05:30")

    def test_ex3_appointment_is_not_callback(self):
        f = facts(appointment__confirmed=True, appointment__slot=slot(day_ref="tomorrow", hour=3),
                  lead__interest="committed")
        self.check(f, "Appointment Scheduled", "Clinic Visit", "High", None)

    def test_ex4_unspecified_agent_call_plus_1_day(self):
        self.check(facts(), "Follow-up Required", "Further Discussion", "Medium", "2026-11-10T11:00:00+05:30")

    def test_ex5_final_do_not_contact(self):
        f = facts(refusal__final="do_not_contact", callback__agreed=True, callback__slot=slot(day_ref="tomorrow"))
        self.check(f, "Not Interested", "Do Not Contact", "Low", None)

    def test_ex6_family_blocker_is_medium(self):
        f = facts(blockers__open=["family_discussion"], blockers__main="family_discussion", vague_postponement__present=True)
        self.check(f, "Follow-up Required", "Family Discussion", "Medium", "2026-11-12T11:00:00+05:30")

    def test_ex6_consultation_on_day_7_is_medium(self):
        f = facts(appointment__confirmed=True, appointment__slot=slot(day_ref="in_n_days", n=7, hour=11),
                  lead__interest="committed")
        self.check(f, "Appointment Scheduled", "Clinic Visit", "Medium", None)

    def test_ex6_consultation_on_day_6_is_high(self):
        f = facts(appointment__confirmed=True, appointment__slot=slot(day_ref="in_n_days", n=6, hour=11),
                  lead__interest="committed")
        self.check(f, "Appointment Scheduled", "Clinic Visit", "High", None)

    def test_blocker_keeps_sub_but_callback_time_is_still_used(self):
        f = facts(blockers__open=["cost_concern"], blockers__main="cost_concern",
                  callback__agreed=True, callback__slot=slot(day_ref="day_after_tomorrow"))
        self.check(f, "Follow-up Required", "Cost Concern", "Medium", "2026-11-11T11:00:00+05:30")

    def test_distinct_callback_with_appointment(self):
        f = facts(appointment__confirmed=True, appointment__slot=slot(day_ref="weekday", weekday="friday", hour=11),
                  callback__agreed=True, callback__slot=slot(day_ref="weekday", weekday="thursday", part_of_day="evening"),
                  lead__interest="committed")
        self.check(f, "Appointment Scheduled", "Clinic Visit", "High", "2026-11-12T18:00:00+05:30")

    def test_past_callback_is_not_repaired(self):
        f = facts(callback__agreed=True, callback__slot=slot(day_ref="today", hour=10, meridiem="am"))
        self.check(f, "Follow-up Required", "Further Discussion", "Medium", "2026-11-10T11:00:00+05:30")

    def test_reschedule_beats_online(self):
        f = facts(appointment__confirmed=True, appointment__online=True, appointment__reschedule=True,
                  appointment__slot=slot(day_ref="tomorrow", hour=5), lead__interest="committed")
        self.check(f, "Appointment Scheduled", "Rescheduled", "High", None)

    def test_invalid_tie_break_and_suppression(self):
        f = facts(invalid__reasons=["outside_service_area", "wrong_contact"], vague_postponement__present=True)
        self.check(f, "Invalid Lead", "Wrong Contact", "Not Qualified", None)

    def test_under_15_policy_exclusion(self):
        f = facts(invalid__reasons=["policy_exclusion"])
        self.check(f, "Invalid Lead", "Policy Exclusion", "Not Qualified", None)

    def test_no_pain_need_ignored_when_need_established(self):
        f = facts(invalid__reasons=["no_pain_need"])
        self.check(f, "Follow-up Required", "Further Discussion", "Medium", "2026-11-10T11:00:00+05:30")

    def test_invalid_beats_refusal(self):
        f = facts(invalid__reasons=["test_enquiry"], refusal__final="explicit_refusal")
        self.check(f, "Invalid Lead", "Test Enquiry", "Not Qualified", None)

    def test_unable_to_assess(self):
        f = facts(patient_need__relevant_pain_need="unclear", assessable__meaningful_conversation=False,
                  lead__interest="unclear")
        self.check(f, "Unable to Assess", "Incomplete Conversation", "Not Assessable", None)

    def test_long_call_with_known_need_is_follow_up(self):
        f = facts(assessable__meaningful_conversation=False)
        self.check(f, "Follow-up Required", "Further Discussion", "Medium", "2026-11-10T11:00:00+05:30")

    def test_exploratory_is_low(self):
        f = facts(lead__interest="exploratory_only", vague_postponement__present=True,
                  blockers__open=["treatment_concern"], blockers__main="treatment_concern")
        self.check(f, "Follow-up Required", "Treatment Concern", "Low", "2026-11-12T11:00:00+05:30")

    def test_defers_over_30_days_is_low(self):
        f = facts(lead__defers_over_30_days=True, vague_postponement__present=True,
                  blockers__open=["current_treatment"], blockers__main="current_treatment")
        self.check(f, "Follow-up Required", "Current Treatment", "Low", "2026-11-12T11:00:00+05:30")

    def test_tie_break_when_no_main_blocker(self):
        f = facts(blockers__open=["treatment_concern", "cost_concern"], blockers__main="none")
        self.check(f, "Follow-up Required", "Cost Concern", "Medium", "2026-11-10T11:00:00+05:30")

    def test_information_requested(self):
        f = facts(information_review__present=True, vague_postponement__present=True)
        self.check(f, "Follow-up Required", "Information Requested", "Medium", "2026-11-12T11:00:00+05:30")


if __name__ == "__main__":
    unittest.main()
