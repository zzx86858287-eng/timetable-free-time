"""Merge teaching blocks and subtract occupied intervals from daily windows."""

from dataclasses import dataclass
from typing import Dict, Iterable, List, Mapping, Optional

from .models import Course, DAY_NAMES, ScheduleError, format_time


@dataclass(frozen=True, order=True)
class Interval:
    start: int
    end: int

    def __post_init__(self) -> None:
        if (
            type(self.start) is not int
            or type(self.end) is not int
            or not 0 <= self.start < self.end <= 1440
        ):
            raise ScheduleError("可用范围的结束时间必须晚于开始时间；跨午夜请拆成两天。")

    @property
    def duration(self) -> int:
        return self.end - self.start


DEFAULT_WINDOW = Interval(480, 1320)
Windows = Mapping[int, Optional[Interval]]


def default_windows() -> Dict[int, Optional[Interval]]:
    return {day: DEFAULT_WINDOW for day in range(1, 8)}


def validate_windows(windows: Windows) -> None:
    if set(windows) != set(range(1, 8)) or any(type(day) is not int for day in windows):
        raise ScheduleError("需要为星期 1—7 定义每天的可用范围；不可用日使用 None。")
    if any(window is not None and not isinstance(window, Interval) for window in windows.values()):
        raise ScheduleError("每天的可用范围必须是 Interval 或 None。")


def merge_courses(courses: Iterable[Course], merge_gap: int = 15) -> List[Course]:
    """Join adjacent same-name courses; a joined break counts as occupied.

    Only consecutive entries on the same day are joined. An intervening course
    with a different name prevents joining. Overlapping/touching same-name
    entries still join when merge_gap is zero.
    """
    if type(merge_gap) is not int or not 0 <= merge_gap <= 1440:
        raise ScheduleError("--merge-gap 必须是 0—1440 之间的整数分钟。")
    ordered = sorted(courses, key=lambda course: (course.weekday, course.start, course.end, course.name))
    merged: List[Course] = []
    for course in ordered:
        if (
            merged
            and merged[-1].weekday == course.weekday
            and merged[-1].name == course.name
            and course.start <= merged[-1].end + merge_gap
        ):
            previous = merged[-1]
            merged[-1] = Course(previous.name, previous.weekday, previous.start, max(previous.end, course.end))
        else:
            merged.append(course)
    return merged


def merge_intervals(intervals: Iterable[Interval]) -> List[Interval]:
    """Return the sorted union; overlap/touching endpoints produce no gap."""
    merged: List[Interval] = []
    for interval in sorted(intervals):
        if merged and interval.start <= merged[-1].end:
            merged[-1] = Interval(merged[-1].start, max(merged[-1].end, interval.end))
        else:
            merged.append(interval)
    return merged


def daily_free_time(
    courses: Iterable[Course], windows: Optional[Windows] = None, merge_gap: int = 15
) -> Dict[int, List[Interval]]:
    windows = default_windows() if windows is None else windows
    validate_windows(windows)
    blocks = merge_courses(courses, merge_gap)
    result: Dict[int, List[Interval]] = {day: [] for day in range(1, 8)}
    for day, window in windows.items():
        if window is None:
            continue
        busy = []
        for course in blocks:
            if course.weekday == day:
                start, end = max(course.start, window.start), min(course.end, window.end)
                if start < end:
                    busy.append(Interval(start, end))
        cursor = window.start
        for interval in merge_intervals(busy):
            if cursor < interval.start:
                result[day].append(Interval(cursor, interval.start))
            cursor = interval.end
        if cursor < window.end:
            result[day].append(Interval(cursor, window.end))
    return result


def format_free_week(free: Mapping[int, List[Interval]], windows: Windows, merge_gap: int) -> str:
    lines = [f"本周空闲时间（连续同名课程合并间隔：{merge_gap} 分钟）"]
    for day, day_name in enumerate(DAY_NAMES, start=1):
        window = windows[day]
        if window is None:
            lines.extend((day_name, "  当天不可用"))
            continue
        lines.append(f"{day_name}（{format_time(window.start)}—{format_time(window.end)}）")
        if not free[day]:
            lines.append("  无空闲时段")
        for interval in free[day]:
            lines.append(f"  {format_time(interval.start)}—{format_time(interval.end)}（{interval.duration} 分钟）")
    return "\n".join(lines)
