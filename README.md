# 课表空闲时间工具

从每周课表计算个人和多人共同空闲时间的 Python 命令行工具。Python 3.9+，运行不需要第三方依赖。

## 快速开始

```bash
git clone https://github.com/zzx86858287-eng/timetable-free-time.git
cd timetable-free-time
python3 -m timetable view --csv examples/alice.csv
```

可选安装：`python3 -m pip install .`，之后用 `timetable` 替代 `python3 -m timetable`。直接从源码运行不需要安装。

## 需求 1：读入和打印课表

CSV 示例（UTF-8 或 UTF-8 BOM）：

```csv
课程名,星期几,开始时间,结束时间
高等数学,周一,09:00,09:45
高等数学,周一,09:55,10:40
大学英语,周一,14:00,15:30
```

- 四个必需表头也可使用 `course,weekday,start,end`，字段顺序不限。
- 星期支持 `1`—`7`（周一—周日）、`周一`、`星期一`、`Mon`、`Monday` 等。
- 时间使用两位小时的 `HH:MM`；结束时间允许 `24:00`。
- 结束时间必须晚于开始时间；跨午夜课程需拆成两天。
- 允许空课表（仅表头）、空白行和符合 CSV 规则的带逗号课程名。
- 无效表头、星期、时间、行字段数量会给出明确错误；行错误包含行号。

交互录入，结束时在课程名提示处直接回车：

```bash
python3 -m timetable view --manual --save my-week.csv
```

也可在命令行手动录入多门课程：

```bash
python3 -m timetable view \
  --course "高等数学" 周一 09:00 09:45 \
  --course "大学英语" 周三 14:00 15:30 \
  --save my-week.csv
```

`--csv`、`--manual`、`--course` 选择一种；`--course` 可重复。`--save` 将手动录入保存为 CSV，会覆盖指定的已有文件。

文本视图按星期和开始时间排列，包含全部七天：

```text
本周课表
星期一
  09:00—10:40  高等数学
  14:00—15:30  大学英语
星期二
  无课程
...
```

## 需求 2：每日空闲时间

```bash
# 每天默认 08:00—22:00
python3 -m timetable free --csv examples/alice.csv

# 统一范围 + 每日覆盖 + 周末不可用
python3 -m timetable free --csv examples/alice.csv \
  --start 08:00 --end 22:00 \
  --day-window 周二 10:00 20:00 \
  --closed 周六 --closed 周日

# free 也支持手动录入
python3 -m timetable free --course "数学" 周一 09:00 10:00
```

`--day-window 星期 开始 结束` 可重复指定不同天，`--closed 星期` 表示当天不可用。同一天重复设置或同时设为可用与关闭会报错。

**连续课程规则**：同一天按时间排序后，相邻记录的课程名相同，且间隔不超过 `--merge-gap` 分钟，就合成一个占用块。默认 `15` 分钟，名称不同或中间插入其他课程不会合并。例如 `09:00—09:45` 和 `09:55—10:40` 合为 `09:00—10:40`，其中十分钟课间也计为占用。因此课表视图和空闲结果都不会产生这段课间碎片。

```bash
# 将阈值改为 10 分钟
python3 -m timetable free --csv examples/alice.csv --merge-gap 10

# 保留正长度课间；重叠或首尾相接的同名记录仍合并
python3 -m timetable view --csv examples/alice.csv --merge-gap 0
```

不同课程的重叠或首尾相接时段先求占用并集，再从每天的可用范围中扣除。可用范围之外的课程会被裁剪，不影响范围内结果。无课程时整段可用范围为空闲，全天占用时显示「无空闲时段」。

示例中星期一的空闲时间：

```text
星期一（08:00—22:00）
  08:00—09:00（60 分钟）
  10:40—14:00（200 分钟）
  15:30—22:00（390 分钟）
```

所有时段采用左闭右开 `[开始, 结束)`，仅保留正长度结果；不产生零分钟空闲。计算精度为分钟。

## 测试

```bash
python3 -m unittest discover -s tests -v
```

GitHub Actions 在 Python 3.9、3.12、3.14 上执行测试。测试覆盖导入与交互、合并边界、重叠/嵌套/裁剪、关闭日和 CLI 错误提示，并用 100 组随机课表对照独立的逐分钟占用计算。输入错误退出码为 `2`，用户取消为 `130`。

## 分阶段交付

| PR | 对应需求 | 状态 |
| --- | --- | --- |
| [#1](https://github.com/zzx86858287-eng/timetable-free-time/pull/1) | 手动录入 / CSV 导入 / 本周课表文本视图 | 已实现 |
| #2 | 每日空闲时间 / 连续同名课程合并 | 本次实现 |
| #3 | 多人共同空闲时间 / 时长降序 | 下一阶段 |

该工具按固定每周课表计算，不读取学校系统，也不推断节假日、单双周或临时调课。
