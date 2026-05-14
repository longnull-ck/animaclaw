"""
Anima — Knowledge Graph Tests
测试知识图谱的核心功能：节点管理、关系创建、BFS检索、统计。
"""

import pytest
from pathlib import Path
import tempfile
import shutil

from anima.memory.knowledge_graph import (
    KnowledgeGraph, RelationType, KnowledgeNode, KnowledgeEdge,
)


@pytest.fixture
def kg_dir():
    d = Path(tempfile.mkdtemp(prefix="anima_kg_test_"))
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def kg(kg_dir):
    return KnowledgeGraph(kg_dir / "test_kg.db")


class TestKnowledgeGraphBasic:
    """基础：节点创建和查找"""

    def test_learn_creates_nodes_and_edge(self, kg: KnowledgeGraph):
        source, target, edge = kg.learn("Python", "is_a", "编程语言")
        assert source.concept == "Python"
        assert target.concept == "编程语言"
        assert edge.relation == RelationType.IS_A
        assert edge.source_id == source.id
        assert edge.target_id == target.id

    def test_learn_same_concept_reuses_node(self, kg: KnowledgeGraph):
        s1, _, _ = kg.learn("Python", "is_a", "编程语言")
        s2, _, _ = kg.learn("Python", "how_to", "安装pip")
        assert s1.id == s2.id

    def test_learn_with_category(self, kg: KnowledgeGraph):
        source, target, _ = kg.learn(
            "Python", "is_a", "编程语言",
            source_category="language",
            target_category="concept",
        )
        assert source.category == "language"
        assert target.category == "concept"

    def test_learn_updates_category_if_empty(self, kg: KnowledgeGraph):
        # First learn without category
        kg.learn("Python", "is_a", "编程语言")
        # Then learn with category — the DB is updated but the returned node
        # is fetched before update; verify via search
        kg.learn("Python", "has_property", "动态类型", source_category="language")
        # Re-fetch should show updated category
        nodes = kg.search_nodes("Python")
        python_node = next(n for n in nodes if n.concept == "Python")
        assert python_node.category == "language"

    def test_learn_invalid_relation_defaults_to_relates_to(self, kg: KnowledgeGraph):
        _, _, edge = kg.learn("A", "invalid_relation_xyz", "B")
        assert edge.relation == RelationType.RELATES_TO

    def test_learn_with_weight(self, kg: KnowledgeGraph):
        _, _, edge = kg.learn("Python", "is_a", "语言", weight=0.8)
        assert edge.weight == 0.8

    def test_learn_duplicate_edge_updates_weight(self, kg: KnowledgeGraph):
        _, _, e1 = kg.learn("Python", "is_a", "语言", weight=0.5)
        _, _, e2 = kg.learn("Python", "is_a", "语言", weight=0.9)
        # 取更高值
        assert e2.weight == 0.9
        assert e1.id == e2.id


class TestKnowledgeGraphRecall:
    """检索功能：BFS遍历"""

    def test_recall_returns_direct_relations(self, kg: KnowledgeGraph):
        kg.learn("小红书", "is_a", "内容电商平台")
        kg.learn("小红书", "how_to", "发布笔记")
        kg.learn("小红书", "rule", "不能硬广")

        results = kg.recall("小红书")
        assert len(results) == 3
        targets = {r["target"] for r in results}
        assert "内容电商平台" in targets
        assert "发布笔记" in targets
        assert "不能硬广" in targets

    def test_recall_nonexistent_concept_returns_empty(self, kg: KnowledgeGraph):
        results = kg.recall("不存在的概念")
        assert results == []

    def test_recall_respects_max_depth(self, kg: KnowledgeGraph):
        # A -> B -> C -> D
        kg.learn("A", "relates_to", "B")
        kg.learn("B", "relates_to", "C")
        kg.learn("C", "relates_to", "D")

        # depth=1: only A's direct neighbors
        results = kg.recall("A", max_depth=1)
        targets = {r["target"] for r in results}
        assert "B" in targets
        assert "C" not in targets

        # depth=2: A -> B -> C
        results = kg.recall("A", max_depth=2)
        targets = {r["target"] for r in results}
        assert "B" in targets
        assert "C" in targets

    def test_recall_respects_max_results(self, kg: KnowledgeGraph):
        for i in range(10):
            kg.learn("Hub", "relates_to", f"Node_{i}")

        results = kg.recall("Hub", max_results=5)
        assert len(results) == 5

    def test_recall_includes_reverse_relations(self, kg: KnowledgeGraph):
        kg.learn("Python", "is_a", "编程语言")

        results = kg.recall("编程语言")
        assert len(results) >= 1
        # Should find Python via reverse relation
        assert any("Python" in r["target"] for r in results)
        assert any(r["relation"].startswith("reverse_") for r in results)

    def test_recall_sorted_by_weight(self, kg: KnowledgeGraph):
        kg.learn("X", "relates_to", "Low", weight=0.3)
        kg.learn("X", "relates_to", "High", weight=0.9)
        kg.learn("X", "relates_to", "Mid", weight=0.6)

        results = kg.recall("X")
        weights = [r["weight"] for r in results]
        assert weights == sorted(weights, reverse=True)


class TestKnowledgeGraphRecallAsText:
    """文本格式化输出"""

    def test_recall_as_text_formats_properly(self, kg: KnowledgeGraph):
        kg.learn("小红书", "is_a", "内容电商平台")
        kg.learn("小红书", "rule", "不能硬广")

        text = kg.recall_as_text("小红书")
        assert "小红书" in text
        assert "内容电商平台" in text
        assert "不能硬广" in text

    def test_recall_as_text_empty_for_unknown(self, kg: KnowledgeGraph):
        text = kg.recall_as_text("未知概念")
        assert text == ""


class TestKnowledgeGraphSearch:
    """搜索功能"""

    def test_search_nodes_by_concept(self, kg: KnowledgeGraph):
        kg.learn("Python", "is_a", "编程语言")
        kg.learn("JavaScript", "is_a", "编程语言")

        results = kg.search_nodes("Python")
        assert len(results) >= 1
        assert any(n.concept == "Python" for n in results)

    def test_search_nodes_by_description(self, kg: KnowledgeGraph):
        kg.learn("FastAPI", "is_a", "Web框架", target_description="高性能Python Web框架")

        results = kg.search_nodes("高性能")
        assert len(results) >= 1

    def test_find_related_concepts(self, kg: KnowledgeGraph):
        kg.learn("Python", "relates_to", "Django")
        kg.learn("Python", "relates_to", "FastAPI")
        kg.learn("Flask", "relates_to", "Python")

        related = kg.find_related_concepts("Python")
        assert "Django" in related
        assert "FastAPI" in related
        assert "Flask" in related


class TestKnowledgeGraphLearnBatch:
    """批量学习"""

    def test_learn_batch(self, kg: KnowledgeGraph):
        kg.learn_batch("小红书", [
            {"relation": "is_a", "target": "内容电商平台"},
            {"relation": "how_to", "target": "发布笔记", "label": "图文或视频"},
            {"relation": "rule", "target": "不能硬广"},
            {"relation": "relates_to", "target": "抖音"},
        ])

        results = kg.recall("小红书")
        assert len(results) == 4
        targets = {r["target"] for r in results}
        assert targets == {"内容电商平台", "发布笔记", "不能硬广", "抖音"}


class TestKnowledgeGraphDelete:
    """删除功能"""

    def test_forget_concept(self, kg: KnowledgeGraph):
        kg.learn("临时概念", "is_a", "测试")
        assert kg.forget_concept("临时概念") is True
        assert kg.recall("临时概念") == []

    def test_forget_nonexistent_returns_false(self, kg: KnowledgeGraph):
        assert kg.forget_concept("不存在") is False


class TestKnowledgeGraphStats:
    """统计和导出"""

    def test_stats_counts(self, kg: KnowledgeGraph):
        kg.learn("A", "is_a", "B", source_category="cat1")
        kg.learn("C", "relates_to", "D", source_category="cat2")

        stats = kg.stats()
        assert stats["nodes"] == 4  # A, B, C, D
        assert stats["edges"] == 2

    def test_export_all(self, kg: KnowledgeGraph):
        kg.learn("X", "is_a", "Y")
        data = kg.export_all()
        assert len(data["nodes"]) == 2
        assert len(data["edges"]) == 1
        assert data["edges"][0]["relation"] == "is_a"
