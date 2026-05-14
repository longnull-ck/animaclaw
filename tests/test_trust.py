"""
Anima — Trust System Tests
"""

import pytest
from anima.models import TrustLevel, TrustState
from anima.trust.system import TrustSystem, score_to_level, TRUST_DELTAS


class TestScoreToLevel:
    """测试分数到等级的映射"""

    def test_probation_range(self):
        assert score_to_level(0.0) == TrustLevel.PROBATION
        assert score_to_level(0.1) == TrustLevel.PROBATION
        assert score_to_level(0.19) == TrustLevel.PROBATION

    def test_basic_range(self):
        assert score_to_level(0.2) == TrustLevel.BASIC
        assert score_to_level(0.3) == TrustLevel.BASIC
        assert score_to_level(0.39) == TrustLevel.BASIC

    def test_intermediate_range(self):
        assert score_to_level(0.4) == TrustLevel.INTERMEDIATE
        assert score_to_level(0.5) == TrustLevel.INTERMEDIATE

    def test_advanced_range(self):
        assert score_to_level(0.6) == TrustLevel.ADVANCED
        assert score_to_level(0.79) == TrustLevel.ADVANCED

    def test_full_range(self):
        assert score_to_level(0.8) == TrustLevel.FULL
        assert score_to_level(1.0) == TrustLevel.FULL


class TestTrustSystem:
    """测试 TrustSystem 核心功能"""

    def test_initialize_creates_state(self, trust_system: TrustSystem):
        state = trust_system.initialize()
        assert state.score == 0.1
        assert state.level == TrustLevel.PROBATION

    def test_initialize_idempotent(self, trust_system: TrustSystem):
        state1 = trust_system.initialize()
        state2 = trust_system.initialize()
        assert state1.score == state2.score

    def test_adjust_positive(self, trust_system: TrustSystem):
        trust_system.initialize()
        state, changed, old = trust_system.adjust("task_success")
        assert state.score == pytest.approx(0.1 + TRUST_DELTAS["task_success"])
        assert not changed  # 还在 probation 范围内
        assert old == TrustLevel.PROBATION

    def test_adjust_negative(self, trust_system: TrustSystem):
        trust_system.initialize()
        state, _, _ = trust_system.adjust("owner_frustrated")
        expected = max(0.0, 0.1 + TRUST_DELTAS["owner_frustrated"])
        assert state.score == pytest.approx(expected)

    def test_adjust_with_custom_delta(self, trust_system: TrustSystem):
        trust_system.initialize()
        state, _, _ = trust_system.adjust("custom", custom_delta=0.15)
        assert state.score == pytest.approx(0.25)

    def test_level_promotion(self, trust_system: TrustSystem):
        trust_system.initialize()
        # 直接跳到 basic
        state, changed, old = trust_system.adjust("big_jump", custom_delta=0.15)
        assert state.level == TrustLevel.BASIC
        assert changed is True
        assert old == TrustLevel.PROBATION

    def test_score_clamp_max(self, trust_system: TrustSystem):
        trust_system.initialize()
        state, _, _ = trust_system.adjust("huge", custom_delta=5.0)
        assert state.score == 1.0

    def test_score_clamp_min(self, trust_system: TrustSystem):
        trust_system.initialize()
        state, _, _ = trust_system.adjust("crash", custom_delta=-5.0)
        assert state.score == 0.0

    def test_history_recorded(self, trust_system: TrustSystem):
        trust_system.initialize()
        trust_system.adjust("task_success", note="did great")
        trust_system.adjust("minor_mistake", note="oops")
        state = trust_system.load()
        assert len(state.history) == 2
        assert state.history[0].reason == "did great"
        assert state.history[1].reason == "oops"

    def test_permissions_probation(self, trust_system: TrustSystem):
        trust_system.initialize()
        perms = trust_system.get_permissions()
        assert perms.auto_execute_routine is False
        assert perms.auto_message is False
        assert perms.require_approval is True

    def test_permissions_full(self, trust_system: TrustSystem):
        trust_system.initialize()
        trust_system.adjust("jump", custom_delta=0.85)
        perms = trust_system.get_permissions()
        assert perms.auto_execute_routine is True
        assert perms.auto_message is True
        assert perms.auto_install_skill is True
        assert perms.require_approval is False

    def test_progress_summary(self, trust_system: TrustSystem):
        trust_system.initialize()
        summary = trust_system.progress_summary()
        assert summary["score"] == 10
        assert summary["level"] == "probation"
        assert "试用期" in summary["label"]
        assert summary["next_level"] == "basic"
        assert isinstance(summary["points_to_next"], int)

    def test_persistence(self, trust_system: TrustSystem):
        trust_system.initialize()
        trust_system.adjust("task_success")
        # 重新加载
        loaded = trust_system.load()
        expected = 0.1 + TRUST_DELTAS["task_success"]
        assert loaded.score == pytest.approx(expected)
