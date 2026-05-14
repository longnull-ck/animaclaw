"""
Anima — Events（事件总线）
所有模块的动作都通过事件总线广播，Web 界面实时订阅。

这是"透明化"的核心——没有黑盒，每一步都可见。

事件类型：
  - perception   感知到信号
  - thinking     正在思考
  - action       执行行动
  - memory       记忆操作
  - skill        技能安装/使用
  - trust        信任度变化
  - evolution    进化/复盘
  - question     问题树变化
  - system       系统状态（心跳/启停）
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from collections import deque
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Awaitable

logger = logging.getLogger("anima.events")


class EventType(str, Enum):
    PERCEPTION = "perception"
    THINKING   = "thinking"
    ACTION     = "action"
    MEMORY     = "memory"
    SKILL      = "skill"
    TRUST      = "trust"
    EVOLUTION  = "evolution"
    QUESTION   = "question"
    SYSTEM     = "system"
    MESSAGE    = "message"


@dataclass
class AnimaEvent:
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    type: EventType = EventType.SYSTEM
    title: str = ""
    detail: str = ""
    icon: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type.value,
            "title": self.title,
            "detail": self.detail,
            "icon": self.icon,
            "data": self.data,
            "timestamp": self.timestamp,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)


# ─── 事件总线 ─────────────────────────────────────────────────

EventHandler = Callable[[AnimaEvent], Awaitable[None]]

# 历史事件缓存（新客户端连接时回放）
MAX_HISTORY = 200


class EventBus:
    """
    全局事件总线。
    所有模块 emit 事件，WebSocket 服务器 subscribe 后推送给前端。
    """

    def __init__(self):
        self._handlers: list[EventHandler] = []
        self._history: deque[AnimaEvent] = deque(maxlen=MAX_HISTORY)

    def subscribe(self, handler: EventHandler) -> None:
        self._handlers.append(handler)

    def unsubscribe(self, handler: EventHandler) -> None:
        self._handlers = [h for h in self._handlers if h is not handler]

    async def emit(self, event: AnimaEvent) -> None:
        """广播事件给所有订阅者"""
        self._history.append(event)
        for handler in self._handlers:
            try:
                await handler(event)
            except Exception as e:
                logger.error(f"[EventBus] handler error: {e}")

    def emit_sync(self, event: AnimaEvent) -> None:
        """同步版本（在非 async 上下文中使用）"""
        self._history.append(event)
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._broadcast(event))
        except RuntimeError:
            pass  # 没有 event loop 时忽略

    async def _broadcast(self, event: AnimaEvent) -> None:
        for handler in self._handlers:
            try:
                await handler(event)
            except Exception:
                pass

    def get_history(self, limit: int = 50) -> list[dict]:
        """获取最近事件（新客户端连接时回放用）"""
        events = list(self._history)[-limit:]
        return [e.to_dict() for e in events]

    @property
    def subscriber_count(self) -> int:
        return len(self._handlers)


# ─── 全局单例 ─────────────────────────────────────────────────

_bus: EventBus | None = None


def get_event_bus() -> EventBus:
    global _bus
    if _bus is None:
        _bus = EventBus()
    return _bus


# ─── 快捷 emit 函数（各模块直接调用） ─────────────────────────

async def emit_perception(title: str, detail: str = "", data: dict | None = None) -> None:
    await get_event_bus().emit(AnimaEvent(
        type=EventType.PERCEPTION, title=title, detail=detail,
        icon="👁️", data=data or {},
    ))


async def emit_thinking(title: str, detail: str = "", data: dict | None = None) -> None:
    await get_event_bus().emit(AnimaEvent(
        type=EventType.THINKING, title=title, detail=detail,
        icon="🧠", data=data or {},
    ))


async def emit_action(title: str, detail: str = "", data: dict | None = None) -> None:
    await get_event_bus().emit(AnimaEvent(
        type=EventType.ACTION, title=title, detail=detail,
        icon="⚡", data=data or {},
    ))


async def emit_memory(title: str, detail: str = "", data: dict | None = None) -> None:
    await get_event_bus().emit(AnimaEvent(
        type=EventType.MEMORY, title=title, detail=detail,
        icon="💾", data=data or {},
    ))


async def emit_skill(title: str, detail: str = "", data: dict | None = None) -> None:
    await get_event_bus().emit(AnimaEvent(
        type=EventType.SKILL, title=title, detail=detail,
        icon="🔧", data=data or {},
    ))


async def emit_trust(title: str, detail: str = "", data: dict | None = None) -> None:
    await get_event_bus().emit(AnimaEvent(
        type=EventType.TRUST, title=title, detail=detail,
        icon="🛡️", data=data or {},
    ))


async def emit_evolution(title: str, detail: str = "", data: dict | None = None) -> None:
    await get_event_bus().emit(AnimaEvent(
        type=EventType.EVOLUTION, title=title, detail=detail,
        icon="🧬", data=data or {},
    ))


async def emit_question(title: str, detail: str = "", data: dict | None = None) -> None:
    await get_event_bus().emit(AnimaEvent(
        type=EventType.QUESTION, title=title, detail=detail,
        icon="❓", data=data or {},
    ))


async def emit_system(title: str, detail: str = "", data: dict | None = None) -> None:
    await get_event_bus().emit(AnimaEvent(
        type=EventType.SYSTEM, title=title, detail=detail,
        icon="⚙️", data=data or {},
    ))


async def emit_message(title: str, detail: str = "", data: dict | None = None) -> None:
    await get_event_bus().emit(AnimaEvent(
        type=EventType.MESSAGE, title=title, detail=detail,
        icon="💬", data=data or {},
    ))
