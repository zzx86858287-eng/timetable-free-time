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
  09:00—09:45  高等数学
  09:55—10:40  高等数学
  14:00—15:30  大学英语
星期二
  无课程
...
```

## 测试

```bash
python3 -m unittest discover -s tests -v
```

GitHub Actions 在 Python 3.9、3.12、3.14 上执行测试。测试覆盖字段校验、CSV/BOM/引号、往返保存、排序、交互录入和 CLI 错误提示。输入错误退出码为 `2`，用户取消为 `130`。

## 分阶段交付

| PR | 对应需求 | 状态 |
| --- | --- | --- |
| #1 | 手动录入 / CSV 导入 / 本周课表文本视图 | 本次实现 |
| #2 | 每日空闲时间 / 连续同名课程合并 | 下一阶段 |
| #3 | 多人共同空闲时间 / 时长降序 | 下一阶段 |

该工具按固定每周课表计算，不读取学校系统，也不推断节假日、单双周或临时调课。
