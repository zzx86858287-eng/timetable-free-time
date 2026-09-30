"""Synthetic, independent minute-mask checks for interval and weekly algorithms."""

import itertools
import random
import unittest

from timetable.availability import Interval, daily_free_time, merge_courses, merge_intervals
from timetable.common import common_free_time, intersect_intervals
from timetable.models import Course


SEED = 2026093007
RANDOM_CASES = 2000
SMALL_INTERVALS = [Interval(start, end) for start in range(7) for end in range(start + 1, 8)]


def minute_mask(start, end):
    return ((1 << (end - start)) - 1) << start


def intervals_mask(intervals):
    occupied = 0
    for interval in intervals:
        occupied |= minute_mask(interval.start, interval.end)
    return occupied


def oracle_free(courses, windows, gap):
    """Mark original minutes and short breaks inside consecutive same-name runs.

    This oracle does not call the production merging, subtraction or intersection
    functions. Bit operations implement union, subtraction and intersection.
    """
    busy = {day: 0 for day in range(1, 8)}
    ordered = sorted(courses, key=lambda c: (c.weekday, c.start, c.end, c.name))
    for (day, _name), group in itertools.groupby(ordered, key=lambda c: (c.weekday, c.name)):
        run = list(group)
        for course in run:
            busy[day] |= minute_mask(course.start, course.end)
        farthest_end = run[0].end
        for course in run[1:]:
            if 0 < course.start - farthest_end <= gap:
                busy[day] |= minute_mask(farthest_end, course.start)
            farthest_end = max(farthest_end, course.end)
    return {
        day: 0 if window is None else minute_mask(window.start, window.end) & ~busy[day]
        for day, window in windows.items()
    }


def synthetic_scenarios():
    rng = random.Random(SEED)
    for _case in range(RANDOM_CASES):
        schedules = []
        for _person in range(rng.randrange(2, 8)):
            courses = []
            for _entry in range(rng.randrange(25)):
                start = rng.randrange(1440)
                end = rng.randrange(start + 1, 1441)
                courses.append(Course(rng.choice("ABC"), rng.randrange(1, 8), start, end))
            if courses and rng.random() < 0.5:
                courses.append(rng.choice(courses))
            schedules.append(courses)
        gap = rng.choice([0, 1, 10, 15, 30, 90, 1440])
        windows = {}
        for day in range(1, 8):
            start = rng.randrange(1440)
            windows[day] = None if rng.random() < 0.2 else Interval(start, rng.randrange(start + 1, 1441))
        yield schedules, windows, gap


class ExhaustiveIntervalProperties(unittest.TestCase):
    def test_union_matches_minute_masks_for_all_small_interval_triples(self):
        # 28 ** 3 = 21,952 combinations, including nesting and endpoint contact.
        for case, intervals in enumerate(itertools.product(SMALL_INTERVALS, repeat=3)):
            with self.subTest(case=case, intervals=intervals):
                self.assertEqual(intervals_mask(merge_intervals(intervals)), intervals_mask(intervals))

    def test_intersection_matches_minute_masks_for_all_small_interval_triples(self):
        for case, (a, b, c) in enumerate(itertools.product(SMALL_INTERVALS, repeat=3)):
            with self.subTest(case=case, left=(a, b), right=c):
                self.assertEqual(
                    intervals_mask(intersect_intervals([a, b], [c])),
                    intervals_mask([a, b]) & intervals_mask([c]),
                )


class RandomWeeklyProperties(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Both methods examine the same 2,000 synthetic groups.
        cls.scenarios = list(synthetic_scenarios())

    def test_personal_oracle_order_duplicates_idempotence_and_gap_monotonicity(self):
        shuffle_rng = random.Random(SEED + 1)
        for case, (schedules, windows, gap) in enumerate(self.scenarios):
            for person, courses in enumerate(schedules):
                with self.subTest(seed=SEED, case=case, person=person, gap=gap):
                    actual = daily_free_time(courses, windows, gap)
                    truth = oracle_free(courses, windows, gap)
                    self.assertEqual(
                        {day: intervals_mask(intervals) for day, intervals in actual.items()},
                        truth,
                        "personal free minutes differ from independent oracle",
                    )
                    merged = merge_courses(courses, gap)
                    self.assertEqual(merge_courses(merged, gap), merged, "merging is not idempotent")
                    shuffled = list(courses)
                    shuffle_rng.shuffle(shuffled)
                    self.assertEqual(daily_free_time(shuffled, windows, gap), actual, "course order changed free time")
                    self.assertEqual(
                        daily_free_time(list(dict.fromkeys(courses)), windows, gap),
                        actual,
                        "duplicate course entries changed free time",
                    )
                    wider_gap = daily_free_time(courses, windows, min(1440, gap + 20))
                    self.assertEqual(
                        {day: intervals_mask(wider_gap[day]) & ~truth[day] for day in range(1, 8)},
                        dict.fromkeys(range(1, 8), 0),
                        "increasing the merge gap introduced free minutes",
                    )

    def test_group_oracle_person_order_sorting_and_adding_people(self):
        for case, (schedules, windows, gap) in enumerate(self.scenarios):
            with self.subTest(seed=SEED, case=case, people=len(schedules), gap=gap):
                shared = common_free_time(schedules, windows, gap)
                self.assertEqual(shared, common_free_time(list(reversed(schedules)), windows, gap))
                self.assertEqual(
                    shared,
                    sorted(shared, key=lambda slot: (-slot.duration, slot.weekday, slot.interval.start)),
                    "common slots are not sorted by duration, weekday and start",
                )
                truth = {day: None for day in range(1, 8)}
                for courses in schedules:
                    free = oracle_free(courses, windows, gap)
                    for day in range(1, 8):
                        truth[day] = free[day] if truth[day] is None else truth[day] & free[day]
                actual = {
                    day: intervals_mask(slot.interval for slot in shared if slot.weekday == day)
                    for day in range(1, 8)
                }
                self.assertEqual(actual, truth, "common free minutes differ from independent oracle")
                if len(schedules) >= 3:
                    fewer = common_free_time(schedules[:-1], windows, gap)
                    fewer_masks = {
                        day: intervals_mask(slot.interval for slot in fewer if slot.weekday == day)
                        for day in range(1, 8)
                    }
                    self.assertEqual(
                        {day: actual[day] & ~fewer_masks[day] for day in range(1, 8)},
                        dict.fromkeys(range(1, 8), 0),
                        "adding a participant introduced common free minutes",
                    )


class InterveningCourseRule(unittest.TestCase):
    def test_intervening_course_prevents_bridging_even_when_nested(self):
        # Document the existing README rule: another name in the sorted sequence
        # interrupts same-name merging, even if it overlaps the first lesson.
        windows = dict.fromkeys(range(1, 8))
        windows[1] = Interval(540, 640)
        courses = [Course("A", 1, 540, 585), Course("A", 1, 595, 640)]
        self.assertEqual(daily_free_time(courses, windows)[1], [])
        with_intervening = courses + [Course("B", 1, 550, 560)]
        self.assertEqual(daily_free_time(with_intervening, windows)[1], [Interval(585, 595)])


if __name__ == "__main__":
    unittest.main()
