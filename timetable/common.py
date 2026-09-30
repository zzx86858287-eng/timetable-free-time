"""Intersect each person's free intervals and rank the weekly results."""

from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence

from .availability import Interval, Windows, daily_free_time, default_windows, merge_intervals, validate_windows
from .models import Course, DAY_NAMES, ScheduleError, format_time


@dataclass(frozen=True)
class CommonSlot:
    weekday: int
    interval: Interval

    @property
    def duration(self) -> int:
        return self.interval.duration


def intersect_intervals(left: Iterable[Interval], right: Iterable[Interval]) -> List[Interval]:
    """Two-pointer intersection of normalized, nonempty half-open intervals."""
    left_blocks, right_blocks = merge_intervals(left), merge_intervals(right)
    result = []
    i = j = 0
    while i < len(left_blocks) and j < len(right_blocks):
        a, b = left_blocks[i], right_blocks[j]
        start, end = max(a.start, b.start), min(a.end, b.end)
        if start < end:
            result.append(Interval(start, end))
        if a.end < b.end:
            i += 1
        elif b.end < a.end:
            j += 1
        else:
            i += 1
            j += 1
    return result


def common_free_time(
    schedules: Sequence[Iterable[Course]], windows: Optional[Windows] = None, merge_gap: int = 15
) -> List[CommonSlot]:
    if len(schedules) < 2:
        raise ScheduleError("共同空闲时间需要至少两个人的课表。")
    windows = default_windows() if windows is None else windows
    validate_windows(windows)
    # Normalize separately: breaks between different people's classes must not
    # be treated as a consecutive lesson belonging to either person.
    individual = [daily_free_time(courses, windows, merge_gap) for courses in schedules]
    slots = []
    for day in range(1, 8):
        shared = individual[0][day]
        for free in individual[1:]:
            shared = intersect_intervals(shared, free[day])
            if not shared:
                break
        slots.extend(CommonSlot(day, interval) for interval in shared)
    return sorted(slots, key=lambda slot: (-slot.duration, slot.weekday, slot.interval.start))


def format_common_time(slots: Iterable[CommonSlot], names: Sequence[str], merge_gap: int) -> str:
    lines = [
        f"共同空闲时间（{len(names)} 人，按时长从长到短）",
        "参与者：" + "、".join(names),
        f"连续同名课程合并间隔：{merge_gap} 分钟",
    ]
    count = 0
    for count, slot in enumerate(slots, start=1):
        interval = slot.interval
        lines.append(f"{count}. {DAY_NAMES[slot.weekday - 1]} {format_time(interval.start)}—{format_time(interval.end)}（{slot.duration} 分钟）")
    if count == 0:
        lines.append("无共同空闲时段。")
    return "\n".join(lines)
