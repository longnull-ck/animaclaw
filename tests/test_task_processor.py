"""
Anima — Task Processor Tests
测试通用任务处理器的数据模型和6步闭环流程。
使用 Mock 替代 Brain 和其他依赖。
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from anima.task_processor import (
    UniversalTaskProcessor, GenericTask, TaskStatus, TaskStep, TaskPlan,
)


def run_async(coro):
    """Helper to run async tests without pytest-asyncio."""
    return asyncio.run(coro)


# ─── Fixtures ────────────────────────────────────────────────

@pytest.fixture
def mock_brain():
    brain = MagicMock()
    brain.think = AsyncMock(return_value="模拟回复结果")
    brain.think_json = AsyncMock(return_value={})
    return brain


@pytest.fixture
def mock_skills():
    skills = MagicMock()
    skills.install = MagicMock(return_value=None)
    return skills


@pytest.fixture
def mock_tools():
    tools = MagicMock()
    tools.has_tool = MagicMock(return_value=False)
    tools.execute = AsyncMock(return_value="工具执行结果")
    return tools


@pytest.fixture
def mock_evo():
    evo = MagicMock()
    evo.record = MagicMock()
    return evo


@pytest.fixture
def mock_memory():
    memory = MagicMock()
    memory.remember = MagicMock()
    return memory


@pytest.fixture
def mock_identity():
    identity = MagicMock()
    return identity


@pytest.fixture
def processor(mock_brain, mock_skills, mock_tools, mock_evo, mock_memory, mock_identity):
    return UniversalTaskProcessor(
        brain=mock_brain,
        skill_registry=mock_skills,
        tool_dispatcher=mock_tools,
        evolution_engine=mock_evo,
        memory_manager=mock_memory,
        identity_engine=mock_identity,
        template_store=None,
        notify_fn=None,
    )


# ─── Data Model Tests ────────────────────────────────────────

class TestDataModels:
    """测试数据模型"""

    def test_generic_task_defaults(self):
        task = GenericTask(description="测试任务")
        assert task.description == "测试任务"
        assert task.status == TaskStatus.PENDING
        assert task.decomposed_steps == []
        assert task.plan is None
        assert task.final_result == ""
        assert task.quality_score == 0.0
        assert task.corrections_made == 0
        assert task.id  # auto-generated

    def test_task_step_creation(self):
        step = TaskStep(
            id="step_1",
            description="搜索信息",
            required_skills=["tool_web_search"],
            acceptance_criteria="找到至少3个结果",
        )
        assert step.id == "step_1"
        assert step.status == "pending"
        assert step.retry_count == 0

    def test_task_plan_creation(self):
        steps = [
            TaskStep(id="s1", description="搜索"),
            TaskStep(id="s2", description="分析"),
        ]
        plan = TaskPlan(
            steps=steps,
            execution_order=["s1", "s2"],
            estimated_time="5分钟",
            fallback_strategy="用大模型兜底",
        )
        assert len(plan.steps) == 2
        assert plan.execution_order == ["s1", "s2"]

    def test_task_status_enum(self):
        assert TaskStatus.PENDING.value == "pending"
        assert TaskStatus.COMPLETED.value == "completed"
        assert TaskStatus.FAILED.value == "failed"


# ─── Processor Lifecycle Tests ────────────────────────────────

class TestProcessorBasic:
    """测试处理器基本功能"""

    def test_active_task_count_initial(self, processor):
        assert processor.active_task_count == 0

    def test_get_active_tasks_empty(self, processor):
        assert processor.get_active_tasks() == []


# ─── Full Pipeline Tests (mocked) ────────────────────────────

class TestProcessorPipeline:
    """测试完整的6步闭环流程（使用mock）"""

    def test_process_task_success(self, processor, mock_brain):
        """测试任务成功完成"""
        mock_brain.think_json = AsyncMock(side_effect=[
            # Step 1: decompose
            {"steps": [
                {"description": "搜索信息", "required_skills": ["llm_generate"], "acceptance_criteria": "完成搜索"},
            ]},
            # Step 3: plan
            {"execution_order": ["step_1"], "estimated_time": "1分钟", "fallback_strategy": "兜底"},
            # Step 5: check
            {"quality_score": 85, "needs_correction": False, "corrections": [], "overall_assessment": "好"},
        ])
        mock_brain.think = AsyncMock(side_effect=[
            "搜索步骤的执行结果",  # Step 4: execute
            "任务完成报告",        # Step 6: report
        ])

        task = run_async(processor.process_task("搜索关于Python的信息"))

        assert task.status == TaskStatus.COMPLETED
        assert task.quality_score == 0.85
        assert task.final_result == "任务完成报告"
        assert task.completed_at is not None
        assert len(task.decomposed_steps) == 1

    def test_process_task_with_correction(self, processor, mock_brain):
        """测试任务需要修正"""
        mock_brain.think_json = AsyncMock(side_effect=[
            # Step 1: decompose
            {"steps": [
                {"description": "写报告", "required_skills": ["llm_generate"], "acceptance_criteria": "完整"},
            ]},
            # Step 3: plan
            {"execution_order": ["step_1"], "estimated_time": "2分钟", "fallback_strategy": "重试"},
            # Step 5: first check - needs correction
            {
                "quality_score": 50,
                "needs_correction": True,
                "corrections": [{"step_id": "step_1", "issue": "不够详细", "fix_instruction": "添加更多细节"}],
                "overall_assessment": "需要修正",
            },
            # Step 5: second check - passes
            {"quality_score": 80, "needs_correction": False, "corrections": [], "overall_assessment": "通过"},
        ])
        mock_brain.think = AsyncMock(side_effect=[
            "初始结果",    # Step 4: execute
            "修正后结果",  # Step 5: re-execute after correction
            "最终报告",    # Step 6: report
        ])

        task = run_async(processor.process_task("写一份市场报告"))

        assert task.status == TaskStatus.COMPLETED
        assert task.corrections_made == 1
        assert task.quality_score == 0.8

    def test_process_task_failure(self, processor, mock_brain):
        """测试任务失败"""
        mock_brain.think_json = AsyncMock(side_effect=RuntimeError("模型不可用"))

        task = run_async(processor.process_task("这个任务会失败"))

        assert task.status == TaskStatus.FAILED
        assert "失败" in task.final_result

    def test_process_task_empty_decompose_creates_fallback(self, processor, mock_brain):
        """当大模型返回空步骤时，创建兜底步骤"""
        mock_brain.think_json = AsyncMock(side_effect=[
            # Step 1: empty decompose
            {"steps": []},
            # Step 3: plan
            {"execution_order": ["step_1"], "estimated_time": "1分钟", "fallback_strategy": ""},
            # Step 5: check
            {"quality_score": 70, "needs_correction": False, "corrections": [], "overall_assessment": "OK"},
        ])
        mock_brain.think = AsyncMock(return_value="兜底结果")

        task = run_async(processor.process_task("简单任务"))

        assert task.status == TaskStatus.COMPLETED
        assert len(task.decomposed_steps) == 1
        assert task.decomposed_steps[0].id == "step_1"


class TestProcessorStepExecution:
    """测试单步执行逻辑"""

    def test_execute_with_tool(self, processor, mock_brain, mock_tools):
        """测试使用工具执行步骤"""
        mock_tools.has_tool = MagicMock(return_value=True)
        mock_tools.execute = AsyncMock(return_value="网页搜索结果")
        mock_brain.think_json = AsyncMock(return_value={"args": {"query": "Python"}})

        step = TaskStep(
            id="s1", description="搜索Python", required_skills=["tool_web_search"]
        )
        result = run_async(processor._execute_single_step(step, "", "搜索任务"))

        assert result == "网页搜索结果"
        assert step.tool_used == "tool_web_search"
        mock_tools.execute.assert_awaited_once_with("tool_web_search", {"query": "Python"})

    def test_execute_without_tool_uses_llm(self, processor, mock_brain, mock_tools):
        """测试没有工具时用LLM兜底"""
        mock_tools.has_tool = MagicMock(return_value=False)
        mock_brain.think = AsyncMock(return_value="AI生成的内容")

        step = TaskStep(
            id="s1", description="写文案", required_skills=["llm_generate"]
        )
        result = run_async(processor._execute_single_step(step, "", "写文案任务"))

        assert result == "AI生成的内容"
        assert step.tool_used == "llm_generate"


class TestProcessorSkillPreparation:
    """测试技能准备（Step 2）"""

    def test_prepare_skills_llm_always_available(self, processor, mock_skills, mock_tools):
        """LLM技能不需要安装"""
        task = GenericTask(description="test")
        task.decomposed_steps = [
            TaskStep(id="s1", description="生成", required_skills=["llm_generate", "llm_analyze"]),
        ]

        run_async(processor._step2_prepare_skills(task))

        # Should not try to install llm_ skills
        mock_skills.install.assert_not_called()

    def test_prepare_skills_installed_tools_skip(self, processor, mock_skills, mock_tools):
        """已注册的工具不需要安装"""
        mock_tools.has_tool = MagicMock(return_value=True)

        task = GenericTask(description="test")
        task.decomposed_steps = [
            TaskStep(id="s1", description="搜索", required_skills=["tool_web_search"]),
        ]

        run_async(processor._step2_prepare_skills(task))

        mock_skills.install.assert_not_called()

    def test_prepare_skills_tries_install(self, processor, mock_skills, mock_tools):
        """缺少的技能尝试从目录安装"""
        mock_tools.has_tool = MagicMock(return_value=False)
        mock_skills.install = MagicMock(return_value=MagicMock(name="新技能", description="desc"))

        task = GenericTask(description="test")
        task.decomposed_steps = [
            TaskStep(id="s1", description="发邮件", required_skills=["tool_email"]),
        ]

        run_async(processor._step2_prepare_skills(task))

        mock_skills.install.assert_called_once_with("tool_email")
