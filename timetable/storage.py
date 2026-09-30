"""CSV input/output; UTF-8 BOM and Chinese/English headers are supported."""

import csv
import os
import tempfile
from pathlib import Path
from typing import Iterable, List

from .models import Course, ScheduleError, format_time

CSV_HEADERS = ("课程名", "星期几", "开始时间", "结束时间")
_HEADERS = {
    "课程名": "name", "course": "name",
    "星期几": "weekday", "weekday": "weekday",
    "开始时间": "start", "start": "start",
    "结束时间": "end", "end": "end",
}
_REQUIRED = {"name", "weekday", "start", "end"}


def read_csv(path: Path) -> List[Course]:
    reader = None
    try:
        with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle, strict=True)
            headers = next(reader, [])
            fields = [_HEADERS.get(header.strip().casefold()) for header in headers]
            if len(fields) != 4 or set(fields) != _REQUIRED:
                raise ScheduleError("CSV 表头必须是：课程名,星期几,开始时间,结束时间（或 course,weekday,start,end）。")
            courses = []
            for row in reader:
                if not row or all(not field.strip() for field in row):
                    continue
                if len(row) != 4:
                    raise ScheduleError(f"CSV 第 {reader.line_num} 行：需要 4 个字段，实际为 {len(row)} 个。")
                record = dict(zip(fields, row))
                try:
                    courses.append(Course.from_fields(
                        record["name"], record["weekday"], record["start"], record["end"]
                    ))
                except ScheduleError as exc:
                    raise ScheduleError(f"CSV 第 {reader.line_num} 行：{exc}") from None
            return courses
    except (OSError, UnicodeError) as exc:
        raise ScheduleError(f"无法读取 CSV {path}：{exc}") from None
    except csv.Error as exc:
        line = reader.line_num if reader is not None else 1
        raise ScheduleError(f"CSV 第 {line} 行格式错误：{exc}") from None


def write_csv(path: Path, courses: Iterable[Course]) -> None:
    target = Path(path)
    temporary_path = None
    try:
        # Stage beside the destination so replace stays on the same filesystem.
        # The old file remains intact until writing, flushing and closing succeed.
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="", dir=target.parent,
            prefix=".timetable-", suffix=".csv.tmp", delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            writer = csv.writer(handle)
            writer.writerow(CSV_HEADERS)
            for course in courses:
                writer.writerow((course.name, course.weekday, format_time(course.start), format_time(course.end)))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, target)
    except (OSError, UnicodeError, csv.Error) as exc:
        raise ScheduleError(f"无法保存 CSV {path}：{exc}") from None
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink()
            except OSError:
                # Replacement already removes this path; cleanup must also not
                # hide the original failure when the filesystem rejects unlink.
                pass
