import random
import re
import subprocess
import sys
import unittest
from pathlib import Path

from timetable.availability import Interval, default_windows
from timetable.common import CommonSlot, common_free_time, intersect_intervals
from timetable.models import Course, ScheduleError

ROOT = Path(__file__).resolve().parents[1]


def monday_window():
    windows = {day: None for day in range(1, 8)}
    windows[1] = Interval(480, 720)
    return windows


class IntersectionTests(unittest.TestCase):
    def test_overlap_and_endpoint_only_contact(self):
        self.assertEqual(intersect_intervals([Interval(480, 600)], [Interval(540, 660)]), [Interval(540, 600)])
        self.assertEqual(intersect_intervals([Interval(480, 540)], [Interval(540, 600)]), [])

    def test_empty_intersection(self):
        self.assertEqual(intersect_intervals([], [Interval(480, 600)]), [])
        self.assertEqual(intersect_intervals([Interval(480, 600)], []), [])

    def test_normalizes_unsorted_overlapping_inputs(self):
        left = [Interval(540, 700), Interval(500, 600)]
        right = [Interval(600, 720), Interval(450, 520)]
        self.assertEqual(intersect_intervals(left, right), [Interval(500, 520), Interval(600, 700)])


class CommonTimeTests(unittest.TestCase):
    def test_two_people_and_descending_duration(self):
        schedules = [[Course("A", 1, 540, 600)], [Course("B", 1, 570, 630)]]
        self.assertEqual(common_free_time(schedules, monday_window()), [CommonSlot(1, Interval(630, 720)), CommonSlot(1, Interval(480, 540))])

    def test_three_people_all_participate(self):
        schedules = [[Course("A", 1, 540, 600)], [Course("B", 1, 600, 660)], [Course("C", 1, 660, 720)]]
        self.assertEqual(common_free_time(schedules, monday_window()), [CommonSlot(1, Interval(480, 540))])

    def test_empty_schedules_and_chronological_ties(self):
        shared = common_free_time([[], []])
        self.assertEqual(shared, [CommonSlot(day, Interval(480, 1320)) for day in range(1, 8)])

    def test_ties_use_weekday_then_start(self):
        windows = monday_window()
        windows[1] = Interval(480, 630)
        windows[2] = Interval(480, 510)
        schedules = [[Course("A", 1, 510, 540), Course("B", 1, 570, 600)], []]
        self.assertEqual(common_free_time(schedules, windows), [CommonSlot(1, Interval(480, 510)), CommonSlot(1, Interval(540, 570)), CommonSlot(1, Interval(600, 630)), CommonSlot(2, Interval(480, 510))])

    def test_no_common_free_time(self):
        schedules = [[Course("A", 1, 480, 600)], [Course("B", 1, 600, 720)]]
        self.assertEqual(common_free_time(schedules, monday_window()), [])

    def test_one_empty_schedule(self):
        shared = common_free_time([[Course("A", 1, 540, 600)], []], monday_window())
        self.assertEqual(shared, [CommonSlot(1, Interval(600, 720)), CommonSlot(1, Interval(480, 540))])

    def test_merged_break_is_busy_for_the_group(self):
        schedules = [[Course("数学", 1, 540, 585), Course("数学", 1, 595, 640)], []]
        shared = common_free_time(schedules, monday_window())
        self.assertEqual(shared, [CommonSlot(1, Interval(640, 720)), CommonSlot(1, Interval(480, 540))])

    def test_same_named_courses_of_different_people_do_not_join(self):
        schedules = [[Course("数学", 1, 540, 585)], [Course("数学", 1, 595, 640)]]
        shared = common_free_time(schedules, monday_window())
        self.assertIn(CommonSlot(1, Interval(585, 595)), shared)

    def test_closed_days(self):
        windows = default_windows()
        windows[6] = windows[7] = None
        self.assertEqual([slot.weekday for slot in common_free_time([[], []], windows)], [1, 2, 3, 4, 5])

    def test_requires_at_least_two_people(self):
        for schedules in ([], [[]]):
            with self.subTest(schedules=schedules), self.assertRaises(ScheduleError):
                common_free_time(schedules)

    def test_randomized_group_minute_oracle_and_person_order(self):
        rng = random.Random(20261001)
        for case in range(100):
            schedules = []
            for person in range(rng.randrange(2, 6)):
                courses = []
                for index in range(rng.randrange(12)):
                    start = rng.randrange(1440)
                    end = rng.randrange(start + 1, 1441)
                    courses.append(Course(str(index), rng.randrange(1, 8), start, end))
                schedules.append(courses)
            windows = {}
            for day in range(1, 8):
                start = rng.randrange(1000)
                windows[day] = None if rng.random() < 0.2 else Interval(start, rng.randrange(start + 1, 1441))
            shared = common_free_time(schedules, windows, merge_gap=0)
            self.assertEqual(shared, common_free_time(list(reversed(schedules)), windows, merge_gap=0))
            self.assertEqual([slot.duration for slot in shared], sorted((slot.duration for slot in shared), reverse=True))
            for day, window in windows.items():
                expected = set() if window is None else {minute for minute in range(window.start, window.end) if all(not any(course.weekday == day and course.start <= minute < course.end for course in courses) for courses in schedules)}
                actual = {minute for slot in shared if slot.weekday == day for minute in range(slot.interval.start, slot.interval.end)}
                self.assertEqual(actual, expected, (case, day))


class CommonCliTests(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run([sys.executable, "-m", "timetable", *args], cwd=ROOT, text=True, capture_output=True)

    def test_three_people_and_sorted_output(self):
        result = self.run_cli("common", "--person", "小明=examples/alice.csv", "--person", "小红=examples/bob.csv", "--person", "小林=examples/carol.csv", "--closed", "周六", "--closed", "周日")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("3 人", result.stdout)
        self.assertIn("参与者：小明、小红、小林", result.stdout)
        self.assertIn("1. 星期四 11:00—22:00（660 分钟）", result.stdout)
        durations = [int(value) for value in re.findall(r"（(\d+) 分钟）", result.stdout)]
        self.assertTrue(durations)
        self.assertEqual(durations, sorted(durations, reverse=True))
        self.assertNotIn("星期六", result.stdout)

    def test_empty_result_is_successful_and_explicit(self):
        args = ["common", "--person", "小明=examples/alice.csv", "--person", "小红=examples/empty.csv", "--start", "09:00", "--end", "10:00"]
        for day in range(2, 8):
            args.extend(("--closed", str(day)))
        result = self.run_cli(*args)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("无共同空闲时段", result.stdout)

    def test_invalid_people_report_errors(self):
        cases = [
            ("A=examples/alice.csv",),
            ("A=examples/alice.csv", "A=examples/bob.csv"),
            ("A=examples/alice.csv", "examples/bob.csv"),
            ("A=examples/alice.csv", "=examples/bob.csv"),
            ("A=examples/alice.csv", "B="),
        ]
        for specs in cases:
            args = ["common"]
            for spec in specs:
                args.extend(("--person", spec))
            result = self.run_cli(*args)
            with self.subTest(specs=specs):
                self.assertEqual(result.returncode, 2)
                self.assertNotIn("Traceback", result.stderr)

    def test_file_error_identifies_the_person(self):
        result = self.run_cli("common", "--person", "小明=examples/alice.csv", "--person", "小红=does-not-exist.csv")
        self.assertEqual(result.returncode, 2)
        self.assertIn("小红 的课表", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_shared_custom_windows_and_merge_gap(self):
        result = self.run_cli("common", "--person", "A=examples/alice.csv", "--person", "B=examples/empty.csv", "--day-window", "周一", "09:45", "09:55", "--merge-gap", "0")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("星期一 09:45—09:55（10 分钟）", result.stdout)

    def test_help_for_each_command(self):
        for command in ("view", "free", "common"):
            with self.subTest(command=command):
                result = self.run_cli(command, "--help")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("--merge-gap", result.stdout)


if __name__ == "__main__":
    unittest.main()
