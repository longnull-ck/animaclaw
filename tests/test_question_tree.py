"""
Anima — Question Tree Tests
"""

import pytest
from anima.models import QuestionStatus, QuestionSource
from anima.question.tree import QuestionTree


class TestQuestionTree:
    """测试问题树引擎"""

    def test_add_root_question(self, question_tree: QuestionTree):
        node = question_tree.add_root(
            "如何提升客户满意度？",
            QuestionSource.OWNER,
            priority=0.8,
        )
        assert node.id
        assert node.question == "如何提升客户满意度？"
        assert node.source == QuestionSource.OWNER
        assert node.priority == 0.8
        assert node.depth == 0
        assert node.status == QuestionStatus.PENDING

    def test_add_child_question(self, question_tree: QuestionTree):
        parent = question_tree.add_root("父问题", QuestionSource.INSTINCT, 0.7)
        child = question_tree.add_child(parent.id, "子问题A")
        assert child is not None
        assert child.parent_id == parent.id
        assert child.depth == 1
        # 子问题优先级 = 父 * 0.85
        assert child.priority == pytest.approx(0.7 * 0.85, abs=0.01)

    def test_max_depth_limit(self, question_tree: QuestionTree):
        """验证最大深度限制"""
        node = question_tree.add_root("d0", QuestionSource.INSTINCT, 0.9)
        for i in range(1, 6):  # MAX_DEPTH = 5
            child = question_tree.add_child(node.id, f"d{i}")
            if child:
                node = child
        # 第 6 层应该被拒绝
        over_limit = question_tree.add_child(node.id, "d6")
        assert over_limit is None

    def test_next_pending_priority_order(self, question_tree: QuestionTree):
        question_tree.add_root("低优先级", QuestionSource.INSTINCT, 0.3)
        question_tree.add_root("高优先级", QuestionSource.OWNER, 0.9)
        question_tree.add_root("中优先级", QuestionSource.SELF_REFLECTION, 0.6)

        node = question_tree.next_pending()
        assert node is not None
        assert node.question == "高优先级"

    def test_start_changes_status(self, question_tree: QuestionTree):
        node = question_tree.add_root("待处理", QuestionSource.INSTINCT, 0.5)
        question_tree.start(node.id)
        # next_pending 不应再返回此节点
        pending = question_tree.next_pending()
        # 只有一个节点且已 in_progress
        assert pending is None

    def test_resolve(self, question_tree: QuestionTree):
        node = question_tree.add_root("要解决的问题", QuestionSource.OWNER, 0.7)
        question_tree.start(node.id)
        question_tree.resolve(node.id, "问题已解决：方案是XYZ")
        stats = question_tree.stats()
        assert stats["resolved"] == 1

    def test_abandon(self, question_tree: QuestionTree):
        node = question_tree.add_root("放弃的问题", QuestionSource.INSTINCT, 0.2)
        question_tree.abandon(node.id, "信任度不足")
        stats = question_tree.stats()
        assert stats["abandoned"] == 1

    def test_boost_priority(self, question_tree: QuestionTree):
        node = question_tree.add_root("可提升", QuestionSource.INSTINCT, 0.5)
        question_tree.boost(node.id, 0.3)
        pending = question_tree.next_pending()
        assert pending.priority == pytest.approx(0.8)

    def test_boost_clamp_max(self, question_tree: QuestionTree):
        node = question_tree.add_root("满分", QuestionSource.OWNER, 0.9)
        question_tree.boost(node.id, 0.5)
        pending = question_tree.next_pending()
        assert pending.priority == 1.0

    def test_stats(self, question_tree: QuestionTree):
        question_tree.add_root("q1", QuestionSource.INSTINCT, 0.5)
        question_tree.add_root("q2", QuestionSource.OWNER, 0.8)
        n3 = question_tree.add_root("q3", QuestionSource.SELF_REFLECTION, 0.3)
        question_tree.resolve(n3.id, "done")

        stats = question_tree.stats()
        assert stats["total"] == 3
        assert stats["pending"] == 2
        assert stats["resolved"] == 1

    def test_all_pending(self, question_tree: QuestionTree):
        for i in range(5):
            question_tree.add_root(f"q{i}", QuestionSource.INSTINCT, i * 0.2)
        pending = question_tree.all_pending(limit=3)
        assert len(pending) == 3
        # 按优先级降序
        assert pending[0].priority >= pending[1].priority >= pending[2].priority

    def test_prune_excess_pending(self, question_tree: QuestionTree):
        """验证同一深度超过限制时自动淘汰"""
        parent = question_tree.add_root("parent", QuestionSource.INSTINCT, 0.9)
        for i in range(15):  # MAX_PENDING_PER_DEPTH = 10
            question_tree.add_child(parent.id, f"child_{i}", priority=i * 0.05)
        stats = question_tree.stats()
        abandoned = stats["abandoned"]
        assert abandoned >= 5  # 至少 5 个被淘汰

    def test_persistence(self, question_tree: QuestionTree):
        node = question_tree.add_root("持久化测试", QuestionSource.OWNER, 0.7)
        # 重新加载
        nodes = question_tree._load()
        assert node.id in nodes
        assert nodes[node.id].question == "持久化测试"
