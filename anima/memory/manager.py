"""
Anima — Memory Manager（记忆管理器）
对外统一接口，上层只和这个类打交道。

三层记忆 + 知识图谱：
  L1 热记忆：当前对话上下文（运行时）
  L2 温记忆：对话摘要（SQLite warm_memory）
  L3 冷记忆：关键事实（SQLite cold_memory + FTS5）
  KG 知识图谱：概念关联网络（SQLite kg_nodes + kg_edges）

检索优先级：
  1. 知识图谱（关联式，从概念出发沿关系走）
  2. 冷记忆全文检索（关键词匹配）
  3. 温记忆摘要（近期工作上下文）
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Callable, Awaitable, TYPE_CHECKING

from anima.models import MemoryCategory, MemoryEntry, MemorySearchResult, HotContext

if TYPE_CHECKING:
    from anima.memory.store import MemoryStore
    from anima.memory.knowledge_graph import KnowledgeGraph

logger = logging.getLogger("anima.memory")


class MemoryManager:

    def __init__(self, store: "MemoryStore", knowledge_graph: "KnowledgeGraph | None" = None):
        self._store = store
        self._kg = knowledge_graph

    @property
    def knowledge_graph(self) -> "KnowledgeGraph | None":
        return self._kg

    def build_context(self, identity_prompt: str, recent_messages: list[dict],
                      query_hint: str = "") -> HotContext:
        permanent = self._store.get_permanent()
        full_identity = identity_prompt
        if permanent:
            full_identity += "\n\n## 永久记忆（始终有效）\n" + "\n".join(f"- {m.content}" for m in permanent)

        query = query_hint or self._extract_query(recent_messages)

        # ── 知识图谱检索（关联式） ───────────────────────────
        kg_context = ""
        if self._kg and query:
            kg_context = self._recall_from_graph(query)

        # ── 冷记忆全文检索 ───────────────────────────────────
        raw_results = self._store.search(query, top_k=6) if query else []
        for entry, _ in raw_results:
            self._store.touch(entry.id)

        injected = [MemorySearchResult(entry=e, score=s) for e, s in raw_results]

        # ── 温记忆摘要 ───────────────────────────────────────
        warm_entries = self._store.get_recent_warm(3)
        recent_summary = self._format_warm(warm_entries)

        # 将图谱知识注入到 identity prompt
        if kg_context:
            full_identity += f"\n\n{kg_context}"

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

    # ─── 知识图谱：学习 ──────────────────────────────────────

    def learn_knowledge(
        self,
        concept: str,
        relation: str,
        target: str,
        **kwargs,
    ) -> None:
        """
        学习一条结构化知识到图谱。

        示例：
          manager.learn_knowledge("小红书", "is_a", "内容电商平台")
          manager.learn_knowledge("小红书", "how_to", "发布笔记")
          manager.learn_knowledge("小红书", "rule", "不能硬广")
        """
        if self._kg:
            self._kg.learn(concept, relation, target, **kwargs)

    def learn_knowledge_batch(self, concept: str, knowledge: list[dict]) -> None:
        """
        批量学习关于一个概念的知识。

        示例：
          manager.learn_knowledge_batch("小红书", [
              {"relation": "is_a", "target": "内容电商平台"},
              {"relation": "how_to", "target": "发布笔记"},
          ])
        """
        if self._kg:
            self._kg.learn_batch(concept, knowledge)

    # ─── 知识图谱：回忆 ──────────────────────────────────────

    def recall_knowledge(self, concept: str, max_depth: int = 2) -> str:
        """回忆一个概念的所有关联知识（返回自然语言文本）"""
        if not self._kg:
            return ""
        return self._kg.recall_as_text(concept, max_depth=max_depth)

    def _recall_from_graph(self, query: str) -> str:
        """
        从查询文本中提取关键概念，然后在图谱中回忆。
        人的思维：看到"小红书"这个词 → 自动联想到相关知识。
        """
        if not self._kg:
            return ""

        # 提取查询中的关键概念（在图谱中找已知节点）
        concepts_found = []
        # 尝试从查询中找到图谱已有的节点
        words = self._extract_concepts(query)
        for word in words:
            nodes = self._kg.search_nodes(word, limit=2)
            for node in nodes:
                if node.concept.lower() in query.lower() or query.lower() in node.concept.lower():
                    concepts_found.append(node.concept)

        if not concepts_found:
            return ""

        # 对找到的概念进行回忆
        all_text = []
        for concept in concepts_found[:3]:  # 最多回忆3个概念
            text = self._kg.recall_as_text(concept, max_depth=2)
            if text:
                all_text.append(text)

        if all_text:
            return "## 相关知识（知识图谱）\n" + "\n\n".join(all_text)
        return ""

    def _extract_concepts(self, text: str) -> list[str]:
        """从文本中提取可能的概念词（中文分词简化版）"""
        # 按标点分割，取 2-8 字长的片段
        segments = re.split(r'[，。！？、；：""''（）\s,.\-!?;:\'\"()\[\]{}<>的了是在和与]+', text)
        words = [w.strip() for w in segments if 2 <= len(w.strip()) <= 8]
        # 去重保持顺序
        seen = set()
        unique = []
        for w in words:
            if w not in seen:
                seen.add(w)
                unique.append(w)
        return unique[:10]

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
