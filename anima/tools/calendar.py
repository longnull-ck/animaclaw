"""
Anima — Calendar Tool
日历管理工具。本地 JSON 存储日历事件，支持增删改查和提醒。

数据存储在 ANIMA_DATA_DIR/calendar.json 中。
不依赖外部服务，自管理日程。

未来可扩展：对接 Google Calendar / Outlook / CalDAV。
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger("anima.tools.calendar")

DATA_DIR = Path(os.getenv("ANIMA_DATA_DIR", "./data"))
CALENDAR_FILE = DATA_DIR / "calendar.json"


async def tool_calendar(args: dict) -> str:
    """
    日历管理工具。

    args:
      action: str          操作类型（必填）：
                           "add"     — 添加事件
                           "list"    — 列出事件
                           "delete"  — 删除事件
                           "update"  — 更新事件
                           "upcoming" — 查看即将到来的事件

      # 添加/更新事件时的参数：
      title: str           事件标题（必填）
      start: str           开始时间，ISO格式 或 自然描述（如 "2024-03-15 14:00"）
      end: str             结束时间（可选）
      description: str     详细描述（可选）
      remind_before: int   提前提醒分钟数（默认 30）
      recurring: str       重复规则（可选）：daily / weekly / monthly

      # 列出/查看事件时的参数：
      date: str            指定日期（如 "2024-03-15"），默认今天
      days: int            查看未来 N 天（默认 7）

      # 删除/更新时的参数：
      event_id: str        事件 ID
    """
    action = args.get("action", "").lower()

    if action == "add":
        return _add_event(args)
    elif action == "list":
        return _list_events(args)
    elif action == "delete":
        return _delete_event(args)
    elif action == "update":
        return _update_event(args)
    elif action == "upcoming":
        return _upcoming_events(args)
    else:
        return "[错误] action 必须是 add/list/delete/update/upcoming 之一"


# ─── 事件操作 ─────────────────────────────────────────────────

def _add_event(args: dict) -> str:
    """添加日历事件"""
    title = args.get("title", "")
    start = args.get("start", "")

    if not title:
        return "[错误] 缺少事件标题 title"
    if not start:
        return "[错误] 缺少开始时间 start"

    # 解析时间
    start_dt = _parse_datetime(start)
    if not start_dt:
        return f"[错误] 无法解析时间: {start}。请使用 YYYY-MM-DD HH:MM 格式"

    end = args.get("end", "")
    end_dt = _parse_datetime(end) if end else None

    event = {
        "id": str(uuid.uuid4())[:8],
        "title": title,
        "start": start_dt.isoformat(),
        "end": end_dt.isoformat() if end_dt else None,
        "description": args.get("description", ""),
        "remind_before": int(args.get("remind_before", 30)),
        "recurring": args.get("recurring", ""),
        "created_at": datetime.utcnow().isoformat(),
    }

    events = _load_events()
    events.append(event)
    _save_events(events)

    time_str = start_dt.strftime("%Y-%m-%d %H:%M")
    return f"已添加日程：{title}（{time_str}）[ID: {event['id']}]"


def _list_events(args: dict) -> str:
    """列出指定日期的事件"""
    date_str = args.get("date", "")

    if date_str:
        target_date = _parse_datetime(date_str)
        if not target_date:
            return f"[错误] 无法解析日期: {date_str}"
    else:
        target_date = datetime.now()

    events = _load_events()
    day_start = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1)

    day_events = []
    for e in events:
        try:
            event_start = datetime.fromisoformat(e["start"])
            if day_start <= event_start < day_end:
                day_events.append(e)
        except (ValueError, KeyError):
            continue

    if not day_events:
        return f"{target_date.strftime('%Y-%m-%d')} 没有日程安排"

    day_events.sort(key=lambda e: e["start"])

    output = f"📅 {target_date.strftime('%Y-%m-%d')} 的日程：\n\n"
    for e in day_events:
        start_time = datetime.fromisoformat(e["start"]).strftime("%H:%M")
        end_info = ""
        if e.get("end"):
            end_time = datetime.fromisoformat(e["end"]).strftime("%H:%M")
            end_info = f" - {end_time}"
        recurring = f" [{e['recurring']}]" if e.get("recurring") else ""
        output += f"  {start_time}{end_info}  {e['title']}{recurring}\n"
        if e.get("description"):
            output += f"           {e['description'][:60]}\n"

    return output.strip()


def _delete_event(args: dict) -> str:
    """删除事件"""
    event_id = args.get("event_id", "")
    if not event_id:
        return "[错误] 缺少 event_id"

    events = _load_events()
    original_count = len(events)
    events = [e for e in events if e.get("id") != event_id]

    if len(events) == original_count:
        return f"[错误] 未找到事件 ID: {event_id}"

    _save_events(events)
    return f"已删除事件 {event_id}"


def _update_event(args: dict) -> str:
    """更新事件"""
    event_id = args.get("event_id", "")
    if not event_id:
        return "[错误] 缺少 event_id"

    events = _load_events()
    target = None
    for e in events:
        if e.get("id") == event_id:
            target = e
            break

    if not target:
        return f"[错误] 未找到事件 ID: {event_id}"

    # 更新提供的字段
    if "title" in args:
        target["title"] = args["title"]
    if "start" in args:
        dt = _parse_datetime(args["start"])
        if dt:
            target["start"] = dt.isoformat()
    if "end" in args:
        dt = _parse_datetime(args["end"])
        if dt:
            target["end"] = dt.isoformat()
    if "description" in args:
        target["description"] = args["description"]
    if "remind_before" in args:
        target["remind_before"] = int(args["remind_before"])
    if "recurring" in args:
        target["recurring"] = args["recurring"]

    _save_events(events)
    return f"已更新事件 {event_id}：{target['title']}"


def _upcoming_events(args: dict) -> str:
    """查看未来 N 天的事件"""
    days = int(args.get("days", 7))

    events = _load_events()
    now = datetime.now()
    end_range = now + timedelta(days=days)

    upcoming = []
    for e in events:
        try:
            event_start = datetime.fromisoformat(e["start"])
            if now <= event_start <= end_range:
                upcoming.append(e)
        except (ValueError, KeyError):
            continue

    if not upcoming:
        return f"未来 {days} 天没有日程安排"

    upcoming.sort(key=lambda e: e["start"])

    output = f"📅 未来 {days} 天的日程（共 {len(upcoming)} 项）：\n\n"
    current_date = ""
    for e in upcoming:
        event_dt = datetime.fromisoformat(e["start"])
        date_str = event_dt.strftime("%Y-%m-%d")
        time_str = event_dt.strftime("%H:%M")

        if date_str != current_date:
            current_date = date_str
            weekday = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][event_dt.weekday()]
            output += f"\n  ── {date_str}（{weekday}）──\n"

        recurring = f" [{e.get('recurring')}]" if e.get("recurring") else ""
        output += f"    {time_str}  {e['title']}{recurring}\n"

    return output.strip()


# ─── 存储 ─────────────────────────────────────────────────────

def _load_events() -> list[dict]:
    """加载日历数据"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not CALENDAR_FILE.exists():
        return []
    try:
        with open(CALENDAR_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return []


def _save_events(events: list[dict]) -> None:
    """保存日历数据（原子写入）"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp_path = CALENDAR_FILE.with_suffix(".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(events, f, ensure_ascii=False, indent=2)
    tmp_path.replace(CALENDAR_FILE)


def _parse_datetime(s: str) -> datetime | None:
    """尝试解析各种时间格式"""
    if not s:
        return None

    formats = [
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M",
        "%Y-%m-%d",
        "%m/%d %H:%M",
        "%m-%d %H:%M",
    ]

    for fmt in formats:
        try:
            dt = datetime.strptime(s, fmt)
            # 如果没有年份，补充当前年
            if dt.year == 1900:
                dt = dt.replace(year=datetime.now().year)
            return dt
        except ValueError:
            continue

    # 尝试 ISO 格式
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        pass

    return None
