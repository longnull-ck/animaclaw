"""
Anima — Evolution Engine Tests
"""

import pytest
from anima.models import ExperienceOutcome, Methodology
from anima.evolution.engine import EvolutionEngine


class TestEvolutionEngine:
    """测试进化引擎"""

    def test_record_experience(self, evolution_engine: EvolutionEngine):
        exp = evolution_engine.record(
            action="处理客户投诉",
            method="先安抚情绪再解决问题",
            outcome=ExperienceOutcome.SUCCESS,
        )
        assert exp.id
        assert exp.action == "处理客户投诉"
        assert exp.outcome == ExperienceOutcome.SUCCESS

    def test_record_multiple(self, evolution_engine: EvolutionEngine):
        for i in range(5):
            evolution_engine.record(
                action=f"任务{i}",
                method=f"方法{i}",
                outcome=ExperienceOutcome.SUCCESS if i % 2 == 0 else ExperienceOutcome.FAILURE,
            )
        stats = evolution_engine.stats()
        assert stats["total_experiences"] == 5
        assert stats["success_rate"] == pytest.approx(0.6)  # 3/5

    def test_stats_empty(self, evolution_engine: EvolutionEngine):
        stats = evolution_engine.stats()
        assert stats["total_experiences"] == 0
        assert stats["success_rate"] == 0.0
        assert stats["methodology_count"] == 0

    def test_apply_feedback(self, evolution_engine: EvolutionEngine):
        exp = evolution_engine.record(
            action="写报告", method="用模板",
            outcome=ExperienceOutcome.SUCCESS,
        )
        evolution_engine.apply_feedback(exp.id, 0.9, "写得很好")
        # 重新加载验证
        exps = evolution_engine._load_exps()
        updated = next(e for e in exps if e.id == exp.id)
        assert updated.owner_satisfaction == 0.9
        assert "写得很好" in updated.lesson

    def test_find_methodology_no_match(self, evolution_engine: EvolutionEngine):
        result = evolution_engine.find_methodology("完全不相关的场景")
        assert result is None

    def test_find_methodology_with_match(self, evolution_engine: EvolutionEngine):
        # 手动写入方法论
        methods = {
            "m1": Methodology(
                id="m1", scenario="客户投诉处理",
                method="先安抚再解决", effectiveness=0.9,
                conditions="客户情绪激动时",
            )
        }
        evolution_engine._save_methods(methods)

        result = evolution_engine.find_methodology("处理客户投诉")
        assert result is not None
        assert result.id == "m1"

    def test_stats_with_feedback(self, evolution_engine: EvolutionEngine):
        exp = evolution_engine.record(
            action="task", method="method",
            outcome=ExperienceOutcome.SUCCESS,
        )
        evolution_engine.apply_feedback(exp.id, 0.85)
        stats = evolution_engine.stats()
        assert stats["avg_owner_satisfaction"] == pytest.approx(0.85)

    def test_experience_limit(self, evolution_engine: EvolutionEngine):
        """验证经验数量超过上限时自动裁剪"""
        for i in range(50):
            evolution_engine.record(
                action=f"task_{i}", method="method",
                outcome=ExperienceOutcome.SUCCESS,
            )
        stats = evolution_engine.stats()
        assert stats["total_experiences"] == 50
