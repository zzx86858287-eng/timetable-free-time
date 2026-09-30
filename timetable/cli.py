"""Command-line interface; input errors exit with status 2."""

import argparse
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from . import __version__
from .availability import Interval, daily_free_time, format_free_week, merge_courses
from .common import common_free_time, format_common_time
from .models import Course, ScheduleError, format_week, parse_time, parse_weekday
from .storage import read_csv, write_csv


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="从每周课表计算空闲时间")
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)
    view = commands.add_parser("view", help="录入或读取课表，打印本周课表")
    add_source_arguments(view)
    add_merge_argument(view)
    free = commands.add_parser("free", help="计算每天可用范围内的空闲时段")
    add_source_arguments(free)
    add_window_arguments(free)
    common = commands.add_parser("common", help="计算多人共同空闲时间，按时长降序排列")
    common.add_argument("--person", action="append", required=True, metavar="姓名=CSV路径", help="每人一份 CSV；至少两人，可重复此参数")
    add_window_arguments(common)
    return parser


def add_source_arguments(command: argparse.ArgumentParser) -> None:
    source = command.add_mutually_exclusive_group(required=True)
    source.add_argument("--csv", type=Path, help="读取 UTF-8 CSV 文件")
    source.add_argument("--manual", action="store_true", help="交互录入课程")
    source.add_argument("--course", nargs=4, action="append", metavar=("课程名", "星期", "开始", "结束"), help="手动录入一门课程；可重复")
    command.add_argument("--save", type=Path, help="将手动录入的课表保存为 CSV")


def add_merge_argument(command: argparse.ArgumentParser) -> None:
    command.add_argument("--merge-gap", type=int, default=15, metavar="分钟", help="同日连续同名课程允许的课间间隔（默认 15 分钟）；0 保留正长度课间")


def add_window_arguments(command: argparse.ArgumentParser) -> None:
    command.add_argument("--start", default="08:00", help="每天可用范围的开始时间（默认 08:00）")
    command.add_argument("--end", default="22:00", help="每天可用范围的结束时间（默认 22:00）")
    command.add_argument("--day-window", nargs=3, action="append", default=[], metavar=("星期", "开始", "结束"), help="覆盖某一天的可用范围；可重复指定不同天")
    command.add_argument("--closed", action="append", default=[], metavar="星期", help="某天完全不可用；可重复")
    add_merge_argument(command)


def read_windows(args: argparse.Namespace) -> Dict[int, Optional[Interval]]:
    base = Interval(parse_time(args.start), parse_time(args.end, allow_end_of_day=True))
    windows: Dict[int, Optional[Interval]] = {day: base for day in range(1, 8)}
    assigned = set()
    for weekday, start, end in args.day_window:
        day = parse_weekday(weekday)
        if day in assigned:
            raise ScheduleError(f"星期 {day} 的 --day-window 重复。")
        windows[day] = Interval(parse_time(start), parse_time(end, allow_end_of_day=True))
        assigned.add(day)
    for weekday in args.closed:
        day = parse_weekday(weekday)
        if day in assigned:
            raise ScheduleError(f"星期 {day} 的可用范围重复或与 --closed 冲突。")
        windows[day] = None
        assigned.add(day)
    return windows


def read_manual() -> List[Course]:
    courses = []
    print("录入课程；课程名直接回车即可结束。")
    while True:
        try:
            name = input("课程名：").strip()
            if not name:
                return courses
            weekday = input("星期几（1—7 / 周一—周日）：")
            start = input("开始时间（HH:MM）：")
            end = input("结束时间（HH:MM）：")
        except EOFError:
            raise ScheduleError("录入中途输入结束；请在课程名提示处回车完成录入。") from None
        try:
            courses.append(Course.from_fields(name, weekday, start, end))
        except ScheduleError as exc:
            print(f"输入错误：{exc} 请重新录入本门课程。", file=sys.stderr)


def read_source(args: argparse.Namespace) -> List[Course]:
    if args.csv is not None:
        if args.save is not None:
            raise ScheduleError("--save 仅用于 --manual 或 --course 手动录入。")
        return read_csv(args.csv)
    courses = read_manual() if args.manual else [Course.from_fields(*fields) for fields in args.course]
    if args.save is not None:
        write_csv(args.save, courses)
    return courses


def read_people(specs: Sequence[str]) -> List[Tuple[str, List[Course]]]:
    if len(specs) < 2:
        raise ScheduleError("共同空闲时间需要至少两个人；请重复使用 --person 姓名=CSV路径。")
    paths = []
    names = set()
    for spec in specs:
        name, separator, path = spec.partition("=")
        name, path = name.strip(), path.strip()
        if not separator or not name or not path:
            raise ScheduleError(f"无效参与者 {spec!r}；请使用 --person 姓名=CSV路径。")
        if any(ord(char) < 32 or ord(char) == 127 for char in name):
            raise ScheduleError("参与者姓名不能包含换行或控制字符。")
        if name in names:
            raise ScheduleError(f"参与者姓名重复：{name}。请使用不同姓名。")
        names.add(name)
        paths.append((name, Path(path)))
    people = []
    for name, path in paths:
        try:
            people.append((name, read_csv(path)))
        except ScheduleError as exc:
            raise ScheduleError(f"{name} 的课表：{exc}") from None
    return people


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        # Validate calculation options before writing a manually entered CSV.
        merge_courses([], args.merge_gap)
        windows = read_windows(args) if args.command in ("free", "common") else None
        if args.command == "common":
            people = read_people(args.person)
            shared = common_free_time([courses for _, courses in people], windows, args.merge_gap)
            print(format_common_time(shared, [name for name, _ in people], args.merge_gap))
        else:
            courses = read_source(args)
            if args.command == "view":
                print(format_week(merge_courses(courses, args.merge_gap)))
            else:
                free = daily_free_time(courses, windows, args.merge_gap)
                print(format_free_week(free, windows, args.merge_gap))
    except ScheduleError as exc:
        parser.error(str(exc))
    except KeyboardInterrupt:
        print("\n已取消。", file=sys.stderr)
        return 130
    return 0
