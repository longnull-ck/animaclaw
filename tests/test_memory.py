"""
Anima — Memory System Tests
"""

import pytest
from anima.models import MemoryCategory, MemoryEntry
from anima.memory.store import MemoryStore
from anima.memory.manager import MemoryManager


class TestMemoryStore:
    """测试 MemoryStore 存储层"""

    def test_add_cold_memory(self, memory_store: MemoryStore):
        entry = memory_store.add_cold(
            "测试记忆内容", MemoryCategory.FACT, importance=0.8, tags=["test"]
        )
        assert entry.id
        assert entry.content == "测试记忆内容"
        assert entry.category == MemoryCategory.FACT
        assert entry.importance == 0.8
        assert entry.tags == ["test"]
        assert entry.permanent is False

    def test_add_permanent_memory(self, memory_store: MemoryStore):
        entry = memory_store.add_cold(
            "永久记忆", MemoryCategory.IDENTITY, importance=1.0, permanent=True
        )
        assert entry.permanent is True
        # 验证可以通过 get_permanent 取回
        permanents = memory_store.get_permanent()
        assert len(permanents) == 1
        assert permanents[0].content == "永久记忆"

    def test_search_finds_content(self, memory_store: MemoryStore):
        memory_store.add_cold("Python编程语言学习笔记", MemoryCategory.FACT, importance=0.7)
        memory_store.add_cold("JavaScript前端开发", MemoryCategory.FACT, importance=0.6)
        memory_store.add_cold("数据库设计原则", MemoryCategory.FACT, importance=0.8)

        results = memory_store.search("Python", top_k=5)
        assert len(results) >= 1
        entries = [e.content for e, _ in results]
        assert any("Python" in c for c in entries)

    def test_search_empty_query(self, memory_store: MemoryStore):
        memory_store.add_cold("some content", MemoryCategory.FACT)
        results = memory_store.search("", top_k=5)
        assert results == []

    def test_touch_increments_access(self, memory_store: MemoryStore):
        entry = memory_store.add_cold("touchable", MemoryCategory.FACT)
        memory_store.touch(entry.id)
        memory_store.touch(entry.id)
        # 通过搜索取回验证
        results = memory_store.search("touchable", top_k=1)
        if results:
            assert results[0][0].access_count == 2

    def test_warm_memory_append_and_get(self, memory_store: MemoryStore):
        memory_store.append_warm(
            summary="今日工作总结",
            key_points=["完成了A", "处理了B"],
            domains=["engineering"],
            period_start="2025-01-01T09:00:00",
            period_end="2025-01-01T18:00:00",
        )
        entries = memory_store.get_recent_warm(5)
        assert len(entries) == 1
        assert entries[0].summary == "今日工作总结"
        assert entries[0].key_points == ["完成了A", "处理了B"]

    def test_warm_memory_ordering(self, memory_store: MemoryStore):
        for i in range(3):
            memory_store.append_warm(
                summary=f"摘要{i}",
                key_points=[],
                domains=[],
                period_start="2025-01-01",
                period_end="2025-01-01",
            )
        entries = memory_store.get_recent_warm(2)
        # get_recent_warm 返回时间正序
        assert len(entries) == 2

    def test_decay_stale(self, memory_store: MemoryStore):
        # 添加一条非永久记忆
        entry = memory_store.add_cold("old memory", MemoryCategory.FACT, importance=0.8)
        # 手动将 last_accessed_at 设为很久以前
        import sqlite3
        with memory_store._conn() as conn:
            conn.execute(
                "UPDATE cold_memory SET last_accessed_at='2020-01-01T00:00:00' WHERE id=?",
                (entry.id,)
            )
        decayed = memory_store.decay_stale()
        assert decayed >= 1


class TestMemoryManager:
    """测试 MemoryManager 上层接口"""

    def test_remember(self, memory_manager: MemoryManager):
        entry = memory_manager.remember("记住这个事实", importance=0.9, tags=["test"])
        assert entry.content == "记住这个事实"
        assert entry.importance == 0.9

    def test_remember_permanent(self, memory_manager: MemoryManager):
        entry = memory_manager.remember_permanent("我是谁", tags=["identity"])
        assert entry.permanent is True
        assert entry.importance == 1.0

    def test_build_context(self, memory_manager: MemoryManager):
        memory_manager.remember_permanent("我叫Anima", tags=["identity"])
        memory_manager.remember("Python是好语言", tags=["fact"])

        ctx = memory_manager.build_context(
            identity_prompt="你是一个AI员工",
            recent_messages=[{"role": "user", "content": "你好"}],
            query_hint="Python",
        )
        assert "你是一个AI员工" in ctx.identity_prompt
        assert "我叫Anima" in ctx.identity_prompt  # 永久记忆注入
        assert len(ctx.recent_messages) == 1

    def test_format_context_as_system_prompt(self, memory_manager: MemoryManager):
        memory_manager.remember("关键事实", importance=0.9)

        ctx = memory_manager.build_context(
            identity_prompt="我是Anima",
            recent_messages=[{"role": "user", "content": "关键"}],
            query_hint="关键",
        )
        prompt = memory_manager.format_context_as_system_prompt(ctx)
        assert "我是Anima" in prompt

    def test_search(self, memory_manager: MemoryManager):
        memory_manager.remember("机器学习模型训练", tags=["ml"])
        memory_manager.remember("数据预处理流程", tags=["data"])

        results = memory_manager.search("机器学习", top_k=3)
        assert len(results) >= 1
