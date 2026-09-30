import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from timetable.models import Course, ScheduleError
from timetable.storage import read_csv, write_csv


class FailingTemporaryFile:
    """A real temporary file with one controlled I/O failure."""

    def __init__(self, handle, failure):
        self.handle = handle
        self.failure = failure
        self.writes = 0

    def __getattr__(self, name):
        return getattr(self.handle, name)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.handle.close()
        if self.failure == "close":
            raise OSError("simulated close failure")

    def write(self, text):
        self.writes += 1
        if self.failure == "write" and self.writes == 2:
            raise OSError(28, "simulated disk full")
        return self.handle.write(text)

    def flush(self):
        if self.failure == "flush":
            raise OSError("simulated flush failure")
        return self.handle.flush()


class AtomicCsvTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.target = self.root / "我的课表.csv"
        self.original = "课程名,星期几,开始时间,结束时间\n原课程,1,09:00,10:00\n".encode("utf-8")
        self.courses = [Course("新课程,进阶", 2, 600, 660)]

    def assert_no_temporary_files(self):
        expected = [self.target] if self.target.exists() else []
        self.assertEqual(list(self.root.iterdir()), expected)

    def failing_file(self, failure):
        factory = tempfile.NamedTemporaryFile

        def create(*args, **kwargs):
            return FailingTemporaryFile(factory(*args, **kwargs), failure)

        return patch("timetable.storage.tempfile.NamedTemporaryFile", side_effect=create)

    def test_successful_overwrite_round_trips_and_cleans_up(self):
        self.target.write_bytes(self.original)
        write_csv(self.target, self.courses)
        self.assertEqual(read_csv(self.target), self.courses)
        self.assert_no_temporary_files()

    def test_successful_new_file_round_trips_and_cleans_up(self):
        write_csv(self.target, self.courses)
        self.assertEqual(read_csv(self.target), self.courses)
        self.assert_no_temporary_files()

    def test_successful_empty_schedule(self):
        self.target.write_bytes(self.original)
        write_csv(self.target, [])
        self.assertEqual(read_csv(self.target), [])
        self.assert_no_temporary_files()

    def test_mid_write_failure_preserves_existing_file(self):
        self.target.write_bytes(self.original)
        with self.failing_file("write"), self.assertRaisesRegex(ScheduleError, "无法保存 CSV"):
            write_csv(self.target, self.courses)
        self.assertEqual(self.target.read_bytes(), self.original)
        self.assert_no_temporary_files()

    def test_failed_first_save_does_not_leave_a_partial_file(self):
        with self.failing_file("write"), self.assertRaises(ScheduleError):
            write_csv(self.target, self.courses)
        self.assertFalse(self.target.exists())
        self.assert_no_temporary_files()

    def test_flush_failure_preserves_existing_file(self):
        self.target.write_bytes(self.original)
        with self.failing_file("flush"), self.assertRaises(ScheduleError):
            write_csv(self.target, self.courses)
        self.assertEqual(self.target.read_bytes(), self.original)
        self.assert_no_temporary_files()

    def test_close_failure_preserves_existing_file(self):
        self.target.write_bytes(self.original)
        with self.failing_file("close"), self.assertRaises(ScheduleError):
            write_csv(self.target, self.courses)
        self.assertEqual(self.target.read_bytes(), self.original)
        self.assert_no_temporary_files()

    def test_fsync_failure_preserves_existing_file(self):
        self.target.write_bytes(self.original)
        with patch("timetable.storage.os.fsync", side_effect=OSError("simulated fsync failure")):
            with self.assertRaises(ScheduleError):
                write_csv(self.target, self.courses)
        self.assertEqual(self.target.read_bytes(), self.original)
        self.assert_no_temporary_files()

    def test_replace_failure_preserves_existing_file(self):
        self.target.write_bytes(self.original)
        with patch("timetable.storage.os.replace", side_effect=OSError("simulated replace failure")):
            with self.assertRaises(ScheduleError):
                write_csv(self.target, self.courses)
        self.assertEqual(self.target.read_bytes(), self.original)
        self.assert_no_temporary_files()

    def test_iterator_failure_preserves_existing_file_and_cleans_up(self):
        def failing_courses():
            yield self.courses[0]
            raise RuntimeError("simulated source failure")

        self.target.write_bytes(self.original)
        with self.assertRaisesRegex(RuntimeError, "simulated source failure"):
            write_csv(self.target, failing_courses())
        self.assertEqual(self.target.read_bytes(), self.original)
        self.assert_no_temporary_files()


if __name__ == "__main__":
    unittest.main()
