"""Command-line interface; input errors exit with status 2."""

import argparse
import sys
from pathlib import Path
from typing import List, Optional, Sequence

from . import __version__
from .models import Course, ScheduleError, format_week
from .storage import read_csv, write_csv


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="从每周课表计算空闲时间")
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)
    view = commands.add_parser("view", help="录入或读取课表，打印本周课表")
    source = view.add_mutually_exclusive_group(required=True)
    source.add_argument("--csv", type=Path, help="读取 UTF-8 CSV 文件")
    source.add_argument("--manual", action="store_true", help="交互录入课程")
    source.add_argument("--course", nargs=4, action="append", metavar=("课程名", "星期", "开始", "结束"), help="手动录入一门课程；可重复")
    view.add_argument("--save", type=Path, help="将手动录入的课表保存为 CSV")
    return parser


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


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        print(format_week(read_source(args)))
    except ScheduleError as exc:
        parser.error(str(exc))
    except KeyboardInterrupt:
        print("\n已取消。", file=sys.stderr)
        return 130
    return 0
