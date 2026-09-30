"""Validated weekly courses, weekdays and minute-based times."""

import re
from dataclasses import dataclass
from typing import Iterable

DAY_NAMES = ("星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日")
_DAY_ALIASES = {str(day): day for day in range(1, 8)}
for _day, _suffix in enumerate("一二三四五六日", start=1):
    _DAY_ALIASES["周" + _suffix] = _day
    _DAY_ALIASES["星期" + _suffix] = _day
_DAY_ALIASES.update({"周天": 7, "星期天": 7})
for _day, _english in enumerate(
    ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"),
    start=1,
):
    _DAY_ALIASES[_english] = _day
    _DAY_ALIASES[_english[:3]] = _day


class ScheduleError(ValueError):
    """An actionable timetable input error."""


def parse_weekday(value: str) -> int:
    try:
        return _DAY_ALIASES[value.strip().casefold()]
    except KeyError:
        raise ScheduleError(f"无效星期 {value!r}；请使用 1—7、周一—周日或 Mon—Sun。") from None


def parse_time(value: str, *, allow_end_of_day: bool = False) -> int:
    value = value.strip()
    if value == "24:00" and allow_end_of_day:
        return 1440
    if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value):
        raise ScheduleError(f"无效时间 {value!r}；请使用 HH:MM（24:00 只能用作结束时间）。")
    hour, minute = map(int, value.split(":"))
    return hour * 60 + minute


def format_time(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


@dataclass(frozen=True)
class Course:
    name: str
    weekday: int
    start: int
    end: int

    def __post_init__(self) -> None:
        name = self.name.strip()
        if not name or any(ord(char) < 32 or ord(char) == 127 for char in name):
            raise ScheduleError("课程名不能为空，也不能包含换行或控制字符。")
        if type(self.weekday) is not int or not 1 <= self.weekday <= 7:
            raise ScheduleError("星期必须在 1—7 之间。")
        if (
            type(self.start) is not int
            or type(self.end) is not int
            or not 0 <= self.start < self.end <= 1440
        ):
            raise ScheduleError("结束时间必须晚于开始时间；跨午夜的课程请拆成两天录入。")
        object.__setattr__(self, "name", name)

    @classmethod
    def from_fields(cls, name: str, weekday: str, start: str, end: str) -> "Course":
        return cls(
            name,
            parse_weekday(weekday),
            parse_time(start),
            parse_time(end, allow_end_of_day=True),
        )


def format_week(courses: Iterable[Course]) -> str:
    ordered = sorted(courses, key=lambda course: (course.weekday, course.start, course.end, course.name))
    lines = ["本周课表"]
    for day, day_name in enumerate(DAY_NAMES, start=1):
        lines.append(day_name)
        daily = [course for course in ordered if course.weekday == day]
        if not daily:
            lines.append("  无课程")
        for course in daily:
            lines.append(f"  {format_time(course.start)}—{format_time(course.end)}  {course.name}")
    return "\n".join(lines)
