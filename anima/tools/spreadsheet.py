"""
Anima — Spreadsheet Tool
CSV 文件处理（读取、查询、写入）
不依赖 pandas，使用标准库 csv 模块
"""

from __future__ import annotations

import csv
import io
import logging
import os
from pathlib import Path

logger = logging.getLogger("anima.tools.spreadsheet")

WORKSPACE_ROOT = Path(os.getenv("ANIMA_WORKSPACE", "./workspace")).resolve()
MAX_ROWS_DISPLAY = 50


async def tool_spreadsheet(args: dict) -> str:
    """
    处理 CSV/表格文件。
    args:
      action: str  操作类型: "read" | "summary" | "filter" | "write"
      path: str    文件路径（相对于工作目录）
      --- read ---
      max_rows: int  最多显示行数（默认20）
      --- filter ---
      column: str    筛选列名
      value: str     筛选值
      --- write ---
      headers: list[str]  列头
      rows: list[list]    数据行
    """
    action = args.get("action", "read")
    rel_path = args.get("path", "")

    if not rel_path:
        return "[错误] 缺少 path 参数"

    filepath = _resolve_path(rel_path)
    if filepath is None:
        return f"[安全限制] 路径 {rel_path} 不在工作目录内"

    if action == "read":
        return await _read_csv(filepath, int(args.get("max_rows", 20)))
    elif action == "summary":
        return await _summary_csv(filepath)
    elif action == "filter":
        column = args.get("column", "")
        value = args.get("value", "")
        if not column:
            return "[错误] filter 操作需要 column 参数"
        return await _filter_csv(filepath, column, value)
    elif action == "write":
        headers = args.get("headers", [])
        rows = args.get("rows", [])
        if not headers:
            return "[错误] write 操作需要 headers 参数"
        return await _write_csv(filepath, headers, rows)
    else:
        return f"[错误] 未知操作: {action}，支持 read/summary/filter/write"


async def _read_csv(filepath: Path, max_rows: int) -> str:
    """读取 CSV 文件，返回表格文本"""
    if not filepath.exists():
        return f"[文件不存在] {filepath.name}"

    try:
        with open(filepath, "r", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            rows = list(reader)

        if not rows:
            return f"[空文件] {filepath.name}"

        headers = rows[0]
        data_rows = rows[1:max_rows + 1]
        total_rows = len(rows) - 1

        # 格式化为表格
        output = f"文件: {filepath.name}（共 {total_rows} 行，显示前 {len(data_rows)} 行）\n\n"
        output += " | ".join(headers) + "\n"
        output += "-" * (len(output.split('\n')[-2])) + "\n"

        for row in data_rows:
            # 对齐列数
            padded = row + [""] * (len(headers) - len(row))
            output += " | ".join(padded[:len(headers)]) + "\n"

        if total_rows > max_rows:
            output += f"\n... 还有 {total_rows - max_rows} 行未显示"

        return output

    except Exception as e:
        return f"[读取失败] {e}"


async def _summary_csv(filepath: Path) -> str:
    """生成 CSV 文件摘要（行数、列数、列名、数值列统计）"""
    if not filepath.exists():
        return f"[文件不存在] {filepath.name}"

    try:
        with open(filepath, "r", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            rows = list(reader)

        if not rows:
            return "[空文件]"

        headers = rows[0]
        data = rows[1:]

        output = f"文件: {filepath.name}\n"
        output += f"行数: {len(data)}\n"
        output += f"列数: {len(headers)}\n"
        output += f"列名: {', '.join(headers)}\n"

        # 简单数值统计
        for col_idx, col_name in enumerate(headers):
            values = []
            for row in data:
                if col_idx < len(row):
                    try:
                        values.append(float(row[col_idx].replace(",", "")))
                    except ValueError:
                        pass

            if values and len(values) > len(data) * 0.5:
                avg = sum(values) / len(values)
                output += f"\n  {col_name}: 平均={avg:.2f}, 最小={min(values):.2f}, 最大={max(values):.2f}"

        return output

    except Exception as e:
        return f"[摘要失败] {e}"


async def _filter_csv(filepath: Path, column: str, value: str) -> str:
    """筛选 CSV 中特定列等于某值的行"""
    if not filepath.exists():
        return f"[文件不存在] {filepath.name}"

    try:
        with open(filepath, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            headers = reader.fieldnames or []

            if column not in headers:
                return f"[错误] 列 '{column}' 不存在。可用列: {', '.join(headers)}"

            matched = [row for row in reader if row.get(column, "").strip() == value.strip()]

        if not matched:
            return f"未找到 {column}='{value}' 的数据"

        output = f"筛选结果: {column}='{value}'，共 {len(matched)} 行\n\n"
        output += " | ".join(headers) + "\n"
        output += "-" * 40 + "\n"

        for row in matched[:MAX_ROWS_DISPLAY]:
            output += " | ".join(row.get(h, "") for h in headers) + "\n"

        return output

    except Exception as e:
        return f"[筛选失败] {e}"


async def _write_csv(filepath: Path, headers: list, rows: list) -> str:
    """写入 CSV 文件"""
    try:
        filepath.parent.mkdir(parents=True, exist_ok=True)

        with open(filepath, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            writer.writerows(rows)

        return f"[成功] 已写入 {filepath.name}（{len(rows)} 行，{len(headers)} 列）"

    except Exception as e:
        return f"[写入失败] {e}"


def _resolve_path(rel_path: str) -> Path | None:
    WORKSPACE_ROOT.mkdir(parents=True, exist_ok=True)
    try:
        resolved = (WORKSPACE_ROOT / rel_path).resolve()
        if str(resolved).startswith(str(WORKSPACE_ROOT)):
            return resolved
        return None
    except (ValueError, OSError):
        return None
