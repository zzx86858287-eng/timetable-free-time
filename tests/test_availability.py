import random
import subprocess
import sys
import unittest
from pathlib import Path

from timetable.availability import Interval, daily_free_time, default_windows, merge_courses, merge_intervals
from timetable.models import Course, ScheduleError

ROOT = Path(__file__).resolve().parents[1]


class MergeTests(unittest.TestCase):
    def test_two_lessons_join_including_the_break(self):
        courses = [Course("数学", 1, 595, 640), Course("数学", 1, 540, 585)]
        self.assertEqual(merge_courses(courses), [Course("数学", 1, 540, 640)])

    def test_chain_and_duplicate_lessons(self):
        courses = [Course("数学", 1, 540, 585), Course("数学", 1, 540, 585), Course("数学", 1, 595, 640), Course("数学", 1, 650, 695)]
        self.assertEqual(merge_courses(courses), [Course("数学", 1, 540, 695)])

    def test_gap_boundary_and_zero(self):
        first = Course("数学", 1, 540, 585)
        at_boundary = Course("数学", 1, 600, 645)
        beyond = Course("数学", 1, 601, 646)
        self.assertEqual(merge_courses([first, at_boundary]), [Course("数学", 1, 540, 645)])
        self.assertEqual(merge_courses([first, beyond]), [first, beyond])
        self.assertEqual(merge_courses([first, at_boundary], 0), [first, at_boundary])
        self.assertEqual(merge_courses([first, Course("数学", 1, 585, 600)], 0), [Course("数学", 1, 540, 600)])

    def test_different_courses_days_and_intervening_courses(self):
        cases = [
            [Course("数学", 1, 540, 585), Course("英语", 1, 595, 640)],
            [Course("数学", 1, 540, 585), Course("数学", 2, 595, 640)],
            [Course("数学", 1, 540, 585), Course("英语", 1, 587, 590), Course("数学", 1, 595, 640)],
        ]
        for courses in cases:
            with self.subTest(courses=courses):
                self.assertEqual(merge_courses(courses), courses)

    def test_occupied_union_handles_overlap_nesting_and_touching(self):
        intervals = [Interval(600, 620), Interval(540, 600), Interval(570, 580), Interval(700, 720)]
        self.assertEqual(merge_intervals(intervals), [Interval(540, 620), Interval(700, 720)])

    def test_invalid_merge_gap(self):
        for gap in (-1, 1441, 1.5, True):
            with self.subTest(gap=gap), self.assertRaises(ScheduleError):
                merge_courses([], gap)


class FreeTimeTests(unittest.TestCase):
    def test_example_math_break_is_not_free(self):
        courses = [Course("数学", 1, 540, 585), Course("数学", 1, 595, 640), Course("英语", 1, 840, 930)]
        free = daily_free_time(courses)
        self.assertEqual(free[1], [Interval(480, 540), Interval(640, 840), Interval(930, 1320)])
        self.assertEqual(free[2], [Interval(480, 1320)])

    def test_distinct_course_break_stays_free(self):
        courses = [Course("数学", 1, 540, 585), Course("英语", 1, 595, 640)]
        self.assertIn(Interval(585, 595), daily_free_time(courses)[1])

    def test_clip_courses_to_window(self):
        courses = [Course("早课", 1, 400, 500), Course("晚课", 1, 1300, 1400), Course("窗外", 1, 60, 120)]
        self.assertEqual(daily_free_time(courses)[1], [Interval(500, 1300)])

    def test_full_occupation_and_no_zero_length_gaps(self):
        courses = [Course("A", 1, 480, 900), Course("B", 1, 900, 1320)]
        self.assertEqual(daily_free_time(courses)[1], [])
        self.assertEqual(daily_free_time([Course("A", 1, 0, 1440)])[1], [])

    def test_per_day_windows_closed_days_and_midnight(self):
        windows = default_windows()
        windows[1] = Interval(600, 720)
        windows[2] = None
        windows[7] = Interval(1380, 1440)
        free = daily_free_time([], windows)
        self.assertEqual(free[1], [Interval(600, 720)])
        self.assertEqual(free[2], [])
        self.assertEqual(free[7], [Interval(1380, 1440)])

    def test_invalid_windows(self):
        with self.assertRaises(ScheduleError):
            daily_free_time([], {1: Interval(480, 1320)})
        for start, end in ((600, 600), (700, 600), (-1, 100), (0, 1441)):
            with self.subTest(start=start, end=end), self.assertRaises(ScheduleError):
                Interval(start, end)

    def test_randomized_minute_occupancy_oracle(self):
        # Compare interval subtraction to a separate minute-by-minute oracle.
        rng = random.Random(20260930)
        for case in range(100):
            courses = []
            for index in range(rng.randrange(20)):
                start = rng.randrange(1440)
                end = rng.randrange(start + 1, 1441)
                courses.append(Course(str(index), rng.randrange(1, 8), start, end))
            free = daily_free_time(courses, merge_gap=0)
            for day in range(1, 8):
                expected = {minute for minute in range(480, 1320) if not any(course.weekday == day and course.start <= minute < course.end for course in courses)}
                actual = {minute for interval in free[day] for minute in range(interval.start, interval.end)}
                self.assertEqual(actual, expected, (case, day))


class FreeCliTests(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run([sys.executable, "-m", "timetable", *args], cwd=ROOT, text=True, capture_output=True)

    def test_view_merges_and_can_show_original_lessons(self):
        merged = self.run_cli("view", "--csv", "examples/alice.csv")
        self.assertEqual(merged.returncode, 0, merged.stderr)
        self.assertIn("09:00—10:40  高等数学", merged.stdout)
        self.assertNotIn("09:55—10:40", merged.stdout)
        original = self.run_cli("view", "--csv", "examples/alice.csv", "--merge-gap", "0")
        self.assertEqual(original.returncode, 0, original.stderr)
        self.assertIn("09:55—10:40", original.stdout)

    def test_free_with_daily_override_and_closed_weekend(self):
        result = self.run_cli("free", "--csv", "examples/alice.csv", "--start", "08:00", "--end", "22:00", "--day-window", "周二", "10:00", "20:00", "--closed", "周六", "--closed", "周日")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("10:40—14:00（200 分钟）", result.stdout)
        self.assertNotIn("09:45—09:55", result.stdout)
        self.assertIn("星期二（10:00—20:00）", result.stdout)
        self.assertEqual(result.stdout.count("当天不可用"), 2)

    def test_free_accepts_manual_arguments(self):
        result = self.run_cli("free", "--course", "数学", "1", "09:00", "10:00")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("10:00—22:00", result.stdout)

    def test_invalid_options_report_errors(self):
        base = ("free", "--csv", "examples/empty.csv")
        cases = [
            ("--start", "22:00", "--end", "08:00"),
            ("--merge-gap", "-1"),
            ("--day-window", "8", "09:00", "10:00"),
            ("--day-window", "1", "09:00", "10:00", "--day-window", "周一", "11:00", "12:00"),
            ("--day-window", "1", "09:00", "10:00", "--closed", "1"),
        ]
        for options in cases:
            result = self.run_cli(*base, *options)
            with self.subTest(options=options):
                self.assertEqual(result.returncode, 2)
                self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
