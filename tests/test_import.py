import codecs
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from timetable.models import Course, ScheduleError, format_week, parse_time, parse_weekday
from timetable.storage import read_csv, write_csv

ROOT = Path(__file__).resolve().parents[1]


class CourseTests(unittest.TestCase):
    def test_weekday_aliases(self):
        for value in ("1", " 周一 ", "星期一", "MON", "Monday"):
            self.assertEqual(parse_weekday(value), 1)
        for value in ("7", "周日", "星期天", "Sunday"):
            self.assertEqual(parse_weekday(value), 7)
        with self.assertRaises(ScheduleError):
            parse_weekday("0")

    def test_time_boundaries(self):
        self.assertEqual(parse_time("00:00"), 0)
        self.assertEqual(parse_time("23:59"), 1439)
        self.assertEqual(parse_time("24:00", allow_end_of_day=True), 1440)
        for value in ("9:00", "09:60", "25:00", "24:00", "foo"):
            with self.subTest(value=value), self.assertRaises(ScheduleError):
                parse_time(value)

    def test_invalid_course(self):
        for fields in (("", "1", "09:00", "10:00"), ("数学", "1", "10:00", "09:00"), ("数学", "1", "09:00", "09:00")):
            with self.subTest(fields=fields), self.assertRaises(ScheduleError):
                Course.from_fields(*fields)

    def test_week_is_sorted_and_includes_empty_days(self):
        courses = [Course.from_fields("英语", "1", "14:00", "15:00"), Course.from_fields("数学", "1", "09:00", "10:00")]
        view = format_week(courses)
        self.assertTrue(view.startswith("本周课表\n星期一\n"))
        self.assertLess(view.index("数学"), view.index("英语"))
        self.assertIn("星期日\n  无课程", view)
        self.assertEqual(view.count("无课程"), 6)


class CsvTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "schedule.csv"

    def put(self, content):
        self.path.write_text(content, encoding="utf-8")

    def test_chinese_and_bom(self):
        self.path.write_bytes(codecs.BOM_UTF8 + "课程名,星期几,开始时间,结束时间\n数学,1,09:00,10:00\n".encode("utf-8"))
        self.assertEqual(read_csv(self.path), [Course("数学", 1, 540, 600)])

    def test_english_reordered_and_quoted_name(self):
        self.put('end,course,start,weekday\n10:00,"Math, advanced",09:00,Mon\n\n')
        self.assertEqual(read_csv(self.path), [Course("Math, advanced", 1, 540, 600)])

    def test_round_trip(self):
        courses = [Course("数学,进阶", 7, 0, 1440)]
        write_csv(self.path, courses)
        self.assertEqual(read_csv(self.path), courses)

    def test_header_only_is_an_empty_schedule(self):
        self.put("课程名,星期几,开始时间,结束时间\n")
        self.assertEqual(read_csv(self.path), [])

    def test_missing_and_duplicate_headers(self):
        for content in ("", "course,weekday,start\n", "course,weekday,start,start\n"):
            self.put(content)
            with self.subTest(content=content), self.assertRaisesRegex(ScheduleError, "表头"):
                read_csv(self.path)

    def test_bad_record_reports_its_line(self):
        for row in ("数学,1,09:00", "数学,8,09:00,10:00", "数学,1,10:00,09:00"):
            self.put("课程名,星期几,开始时间,结束时间\n" + row + "\n")
            with self.subTest(row=row), self.assertRaisesRegex(ScheduleError, "第 2 行"):
                read_csv(self.path)

    def test_bad_quoting(self):
        self.put('课程名,星期几,开始时间,结束时间\n"数学,1,09:00,10:00\n')
        with self.assertRaisesRegex(ScheduleError, "格式错误"):
            read_csv(self.path)

    def test_missing_file(self):
        with self.assertRaisesRegex(ScheduleError, "无法读取"):
            read_csv(self.path)


class CliTests(unittest.TestCase):
    def run_cli(self, *args, input_text=None):
        return subprocess.run([sys.executable, "-m", "timetable", *args], cwd=ROOT, input=input_text, text=True, capture_output=True)

    def test_csv_view(self):
        result = self.run_cli("view", "--csv", "examples/alice.csv")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("本周课表", result.stdout)
        self.assertIn("高等数学", result.stdout)

    def test_repeated_manual_arguments(self):
        result = self.run_cli("view", "--course", "英语", "2", "14:00", "15:00", "--course", "数学", "1", "09:00", "10:00")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertLess(result.stdout.index("数学"), result.stdout.index("英语"))

    def test_interactive_save_and_reimport(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manual.csv"
            result = self.run_cli("view", "--manual", "--save", str(path), input_text="数学\n周一\n09:00\n10:00\n\n")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(read_csv(path), [Course("数学", 1, 540, 600)])
            self.assertEqual(self.run_cli("view", "--csv", str(path)).returncode, 0)

    def test_interactive_retry(self):
        result = self.run_cli("view", "--manual", input_text="数学\n周一\n10:00\n09:00\n数学\n周一\n09:00\n10:00\n\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("输入错误", result.stderr)
        self.assertIn("09:00—10:00  数学", result.stdout)

    def test_errors_have_no_traceback(self):
        for args in (("view", "--csv", "does-not-exist.csv"), ("view", "--course", "数学", "8", "09:00", "10:00"), ("view", "--csv", "examples/alice.csv", "--save", "ignored.csv")):
            result = self.run_cli(*args)
            with self.subTest(args=args):
                self.assertEqual(result.returncode, 2)
                self.assertNotIn("Traceback", result.stderr)

    def test_eof_during_manual_entry(self):
        result = self.run_cli("view", "--manual", input_text="数学\n")
        self.assertEqual(result.returncode, 2)
        self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
