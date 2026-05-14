"""
Anima — Memory Manager（记忆管理器）
对外统一接口，上层只和这个类打交道
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Callable, Awaitable, TYPE_CHECKING

from anima.models import MemoryCategory, MemoryEntry, MemorySearchResult, HotContext

if TYPE_CHECKING:
    from anima.memory.store import MemoryStore

logger = logging.getLogger("anima.memory")


class MemoryManager:

    def __init__(self, store: "MemoryStore"):
        self._store = store

    def build_context(self, identity_prompt: str, recent_messages: list[dict],
                      query_hint: str = "") -> HotContext:
        permanent = self._store.get_permanent()
        full_identity = identity_prompt
        if permanent:
            full_identity += "\n\n## 永久记忆（始终有效）\n" + "\n".join(f"- {m.content}" for m in permanent)

        query = query_hint or self._extract_query(recent_messages)
        raw_results = self._store.search(query, top_k=6) if query else []
        for entry, _ in raw_results:
            self._store.touch(entry.id)

        injected = [MemorySearchResult(entry=e, score=s) for e, s in raw_results]

        warm_entries = self._store.get_recent_warm(3)
        recent_summary = self._format_warm(warm_entries)

        return HotContext(
            identity_prompt=full_identity,
            recent_messages=recent_messages[-20:],
            injected_memories=injected,
            recent_summary=recent_summary,
        )

    def format_context_as_system_prompt(self, ctx: HotContext) -> str:
        parts = [ctx.identity_prompt]
        if ctx.recent_summary:
            parts.append(f"\n## 近期工作摘要\n{ctx.recent_summary}")
        if ctx.injected_memories:
            parts.append("\n## 相关记忆（从记忆库检索）")
            for r in ctx.injected_memories:
                parts.append(f"- [{r.entry.category.value}|{int(r.score*100)}%] {r.entry.content}")
        return "\n".join(parts)

    async def compress(self, messages: list[dict],
                       summarize_fn: Callable[[list[dict]], Awaitable[dict]]) -> None:
        if len(messages) < 2:
            return
        result = await summarize_fn(messages)
        if not result:
            return
        now = datetime.utcnow().isoformat()
        self._store.append_warm(
            summary=result.get("summary", ""),
            key_points=result.get("key_points", []),
            domains=result.get("domains", []),
            period_start=now, period_end=now,
        )
        for fact in result.get("new_facts", []):
            self._store.add_cold(
                content=fact["content"],
                category=MemoryCategory(fact.get("category", "fact")),
                importance=float(fact.get("importance", 0.6)),
                tags=fact.get("tags", []),
            )

    def remember(self, content: str, category: MemoryCategory = MemoryCategory.FACT,
                 importance: float = 0.7, tags: list[str] | None = None,
                 permanent: bool = False) -> MemoryEntry:
        return self._store.add_cold(content, category, importance, tags or [], permanent)

    def remember_permanent(self, content: str, tags: list[str] | None = None) -> MemoryEntry:
        return self._store.add_cold(content, MemoryCategory.IDENTITY, 1.0, tags or [], True)

    def search(self, query: str, top_k: int = 5):
        return self._store.search(query, top_k)

    def run_decay(self) -> int:
        return self._store.decay_stale()

    def _format_warm(self, entries: list) -> str:
        if not entries:
            return ""
        lines = []
        for e in entries:
            date = e.period_end[:10]
            kp = "；".join(e.key_points) if e.key_points else ""
            lines.append(f"[{date}] {e.summary}" + (f"（要点：{kp}）" if kp else ""))
        return "\n".join(lines)

    def _extract_query(self, messages: list[dict]) -> str:
        for m in reversed(messages):
            if m.get("role") == "user":
                return str(m.get("content", ""))[:200]
        return ""
