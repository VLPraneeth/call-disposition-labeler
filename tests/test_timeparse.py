"""Unit tests for callback time resolution (policy rules F1-F12, boundary example EX1).

Run: python -m unittest discover -s tests -v
"""
import unittest

from labeler.timeparse import day_offset, resolve_clock, resolve_slot

MON_1400 = "2026-11-09T14:00:00+05:30"  # Monday, as in the rulebook boundary examples


def slot(**kw):
    base = {"relative_minutes": None, "day_ref": "none", "n": None, "weekday": None, "day": None,
            "month": None, "year": None, "hour": None, "minute": None, "meridiem": None, "part_of_day": None}
    base.update(kw)
    return base


class TestClock(unittest.TestCase):
    def test_bare_hours_1_to_7_are_pm(self):
        self.assertEqual(resolve_clock(slot(hour=4)), (16, 0))
        self.assertEqual(resolve_clock(slot(hour=7, minute=30)), (19, 30))

    def test_bare_hours_8_to_11_are_am_and_12_is_noon(self):
        self.assertEqual(resolve_clock(slot(hour=8)), (8, 0))
        self.assertEqual(resolve_clock(slot(hour=11)), (11, 0))
        self.assertEqual(resolve_clock(slot(hour=12)), (12, 0))

    def test_explicit_meridiem_and_part_of_day_win(self):
        self.assertEqual(resolve_clock(slot(hour=4, meridiem="am")), (4, 0))
        self.assertEqual(resolve_clock(slot(hour=9, meridiem="pm")), (21, 0))
        self.assertEqual(resolve_clock(slot(hour=6, part_of_day="morning")), (6, 0))
        self.assertEqual(resolve_clock(slot(hour=8, part_of_day="evening")), (20, 0))

    def test_named_parts_of_day(self):
        self.assertEqual(resolve_clock(slot(part_of_day="morning")), (10, 0))
        self.assertEqual(resolve_clock(slot(part_of_day="afternoon")), (15, 0))
        self.assertEqual(resolve_clock(slot(part_of_day="evening")), (18, 0))
        self.assertEqual(resolve_clock(slot(part_of_day="lunch")), (13, 0))

    def test_24h_clock_passthrough(self):
        self.assertEqual(resolve_clock(slot(hour=16, minute=15)), (16, 15))


class TestRelativeDays(unittest.TestCase):
    def test_ex1_tomorrow_at_4(self):
        self.assertEqual(resolve_slot(slot(day_ref="tomorrow", hour=4), MON_1400), "2026-11-10T16:00:00+05:30")

    def test_day_without_time_defaults_to_11(self):
        self.assertEqual(resolve_slot(slot(day_ref="tomorrow"), MON_1400), "2026-11-10T11:00:00+05:30")
        self.assertEqual(resolve_slot(slot(day_ref="day_after_tomorrow"), MON_1400), "2026-11-11T11:00:00+05:30")
        self.assertEqual(resolve_slot(slot(day_ref="in_n_days", n=5), MON_1400), "2026-11-14T11:00:00+05:30")

    def test_this_evening_same_day(self):
        self.assertEqual(resolve_slot(slot(day_ref="today", part_of_day="evening"), "2026-10-15T10:39:36+05:30"),
                         "2026-10-15T18:00:00+05:30")

    def test_today_in_the_past_is_rejected(self):
        self.assertIsNone(resolve_slot(slot(day_ref="today", hour=11, meridiem="am"), MON_1400))


class TestWeekdays(unittest.TestCase):
    def test_bare_weekday_is_strictly_future(self):
        self.assertEqual(resolve_slot(slot(day_ref="weekday", weekday="wednesday"), MON_1400), "2026-11-11T11:00:00+05:30")
        # same weekday as the call -> one week later
        self.assertEqual(resolve_slot(slot(day_ref="weekday", weekday="monday"), MON_1400), "2026-11-16T11:00:00+05:30")

    def test_this_weekday_today_if_time_still_future(self):
        self.assertEqual(resolve_slot(slot(day_ref="this_weekday", weekday="monday", hour=6), MON_1400),
                         "2026-11-09T18:00:00+05:30")
        self.assertEqual(resolve_slot(slot(day_ref="this_weekday", weekday="monday", hour=10, meridiem="am"), MON_1400),
                         "2026-11-16T10:00:00+05:30")

    def test_next_weekday_is_in_following_week(self):
        # Call on Monday 9th: "next Wednesday" is in the week of Mon 16th -> Wed 18th
        self.assertEqual(resolve_slot(slot(day_ref="next_weekday", weekday="wednesday"), MON_1400), "2026-11-18T11:00:00+05:30")
        # Call on Saturday 2026-10-17: "next Monday" -> 2026-10-19
        self.assertEqual(resolve_slot(slot(day_ref="next_weekday", weekday="monday"), "2026-10-17T12:36:14+05:30"),
                         "2026-10-19T11:00:00+05:30")

    def test_next_week_alone_is_next_monday(self):
        self.assertEqual(resolve_slot(slot(day_ref="next_week"), "2026-10-17T12:36:14+05:30"), "2026-10-19T11:00:00+05:30")


class TestAbsoluteDatesAndMonths(unittest.TestCase):
    def test_day_number_only_this_month(self):
        self.assertEqual(resolve_slot(slot(day_ref="explicit_date", day=26), "2026-10-15T18:28:03+05:30"),
                         "2026-10-26T11:00:00+05:30")

    def test_day_number_already_passed_rolls_to_next_month(self):
        self.assertEqual(resolve_slot(slot(day_ref="explicit_date", day=3), "2026-10-15T18:28:03+05:30"),
                         "2026-11-03T11:00:00+05:30")

    def test_month_day_without_year_is_next_future_occurrence(self):
        self.assertEqual(resolve_slot(slot(day_ref="explicit_date", day=5, month=1), MON_1400), "2027-01-05T11:00:00+05:30")

    def test_explicit_past_full_date_is_rejected(self):
        self.assertIsNone(resolve_slot(slot(day_ref="explicit_date", day=1, month=11, year=2026), MON_1400))

    def test_in_one_month_same_day_clamped(self):
        self.assertEqual(resolve_slot(slot(day_ref="in_n_months", n=1), "2026-01-31T10:00:00+05:30"), "2026-02-28T11:00:00+05:30")

    def test_bare_next_month_is_first_day(self):
        self.assertEqual(resolve_slot(slot(day_ref="next_month"), MON_1400), "2026-12-01T11:00:00+05:30")


class TestIntervalsAndTimeOnly(unittest.TestCase):
    def test_in_minutes_preserves_seconds(self):
        self.assertEqual(resolve_slot(slot(relative_minutes=15), "2026-10-15T14:11:01+05:30"), "2026-10-15T14:26:01+05:30")

    def test_in_two_hours(self):
        self.assertEqual(resolve_slot(slot(relative_minutes=120), MON_1400), "2026-11-09T16:00:00+05:30")

    def test_time_only_future_today_else_tomorrow(self):
        self.assertEqual(resolve_slot(slot(hour=5), MON_1400), "2026-11-09T17:00:00+05:30")
        self.assertEqual(resolve_slot(slot(hour=11), MON_1400), "2026-11-10T11:00:00+05:30")

    def test_vague_is_none(self):
        self.assertIsNone(resolve_slot(slot(), MON_1400))
        self.assertIsNone(resolve_slot(None, MON_1400))


class TestDayOffset(unittest.TestCase):
    def test_offsets(self):
        self.assertEqual(day_offset(slot(day_ref="tomorrow", hour=3), MON_1400), 1)
        self.assertEqual(day_offset(slot(day_ref="in_n_days", n=7), MON_1400), 7)
        self.assertEqual(day_offset(slot(day_ref="weekday", weekday="sunday"), "2026-10-14T16:38:32+05:30"), 4)


if __name__ == "__main__":
    unittest.main()
