"""
Anima — Universal Task Processor（通用任务处理元框架）

核心理念：一套代码处理所有任务。
不管任务是什么——客户跟进、内容生产、数据处理、行政事务——
都自动套用同一个 6 步闭环流程，不需要写一行新业务代码。

6 步闭环：
  1. 任务理解与拆解（大模型）
  2. 能力自检与技能准备（自动）
  3. 生成执行计划（大模型）
  4. 自动执行与技能调用（自动）
  5. 结果自检与修正（大模型）
  6. 结果汇报与归档（自动）

所有业务逻辑由大模型完成，代码只提供执行骨架和调用接口。
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from anima.events import (
    emit_action, emit_thinking, emit_skill, emit_system, emit_evolution,
)

logger = logging.getLogger("anima.task_processor")


# ─── 数据模型 ─────────────────────────────────────────────────

class TaskStatus(str, Enum):
    PENDING = "pending"
    DECOMPOSING = "decomposing"
    PREPARING = "preparing"
    PLANNING = "planning"
    EXECUTING = "executing"
    CHECKING = "checking"
    CORRECTING = "correcting"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class TaskStep:
    id: str
    description: str
    required_skills: list[str] = field(default_factory=list)
    acceptance_criteria: str = ""
    status: str = "pending"  # pending / executing / done / failed
    result: str = ""
    tool_used: str = ""
    retry_count: int = 0


@dataclass
class TaskPlan:
    steps: list[TaskStep]
    execution_order: list[str]  # step ids in order
    estimated_time: str = ""
    fallback_strategy: str = ""


@dataclass
class GenericTask:
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    description: str = ""
    status: TaskStatus = TaskStatus.PENDING
    decomposed_steps: list[TaskStep] = field(default_factory=list)
    plan: TaskPlan | None = None
    execution_log: list[dict] = field(default_factory=list)
    final_result: str = ""
    quality_score: float = 0.0
    corrections_made: int = 0
    template_id: str | None = None
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    completed_at: str | None = None


# ─── 通用任务处理器 ───────────────────────────────────────────

class UniversalTaskProcessor:
    """
    万能任务处理器。
    接收任意自然语言描述的任务，自动走完 6 步闭环。
    """

    MAX_CORRECTIONS = 2
    MAX_STEP_RETRIES = 3

    def __init__(
        self,
        brain,
        skill_registry,
        tool_dispatcher,
        evolution_engine,
        memory_manager,
        identity_engine,
        template_store=None,
        notify_fn=None,
    ):
        self._brain = brain
        self._skills = skill_registry
        self._tools = tool_dispatcher
        self._evo = evolution_engine
        self._memory = memory_manager
        self._identity = identity_engine
        self._templates = template_store  # TaskTemplateStore
        self._notify = notify_fn
        self._active_tasks: dict[str, GenericTask] = {}

    # ─── 唯一公开入口 ────────────────────────────────────────

    async def process_task(self, task_description: str, context: str = "") -> GenericTask:
        """
        处理任何任务的唯一入口。
        传入自然语言描述，自动完成全部 6 步。
        """
        task = GenericTask(description=task_description)
        self._active_tasks[task.id] = task

        await emit_system(
            "收到新任务",
            task_description[:80],
            data={"task_id": task.id},
        )

        try:
            # ── Step 0: 检查任务模板 ─────────────────────────
            template = None
            if self._templates:
                template = self._templates.find_matching(task_description)
                if template:
                    task.template_id = template["id"]
                    await emit_thinking(
                        "匹配到已有任务模板",
                        f"模板: {template['name']}",
                        data={"template_id": template["id"]},
                    )

            # ── Step 1: 任务理解与拆解 ───────────────────────
            task.status = TaskStatus.DECOMPOSING
            await emit_thinking("Step 1/6: 理解与拆解任务", task_description[:60])
            task.decomposed_steps = await self._step1_decompose(task_description, context, template)

            # ── Step 2: 能力自检与技能准备 ───────────────────
            task.status = TaskStatus.PREPARING
            await emit_skill("Step 2/6: 能力自检", f"检查 {len(task.decomposed_steps)} 个步骤所需技能")
            await self._step2_prepare_skills(task)

            # ── Step 3: 生成执行计划 ─────────────────────────
            task.status = TaskStatus.PLANNING
            await emit_thinking("Step 3/6: 生成执行计划", "")
            task.plan = await self._step3_generate_plan(task)

            # ── Step 4: 自动执行 ─────────────────────────────
            task.status = TaskStatus.EXECUTING
            await emit_action("Step 4/6: 开始执行", f"共 {len(task.plan.steps)} 步")
            await self._step4_execute(task)

            # ── Step 5: 结果自检与修正 ───────────────────────
            task.status = TaskStatus.CHECKING
            await emit_thinking("Step 5/6: 结果自检", "")
            await self._step5_check_and_correct(task)

            # ── Step 6: 汇报与归档 ──────────────────────────
            task.status = TaskStatus.COMPLETED
            task.completed_at = datetime.utcnow().isoformat()
            await emit_system("Step 6/6: 汇报归档", "")
            await self._step6_report_and_archive(task)

            # ── 自动生成任务模板 ─────────────────────────────
            if self._templates and not template:
                self._templates.generate_from_task(task)
                await emit_evolution("生成新任务模板", task_description[:40])

        except Exception as e:
            task.status = TaskStatus.FAILED
            task.final_result = f"任务执行失败: {e}"
            logger.error(f"[TaskProcessor] 任务失败: {e}", exc_info=True)
            await emit_system("任务失败", str(e)[:80], data={"error": True})

            # 记录失败经历
            from anima.models import ExperienceOutcome
            self._evo.record(
                action=task_description[:200],
                method="通用任务处理器",
                outcome=ExperienceOutcome.FAILURE,
                lesson=str(e)[:200],
            )

        finally:
            del self._active_tasks[task.id]

        return task

    # ─── Step 1: 任务理解与拆解 ──────────────────────────────

    async def _step1_decompose(
        self, description: str, context: str, template: dict | None
    ) -> list[TaskStep]:
        """让大模型拆解任务为可执行步骤"""

        template_hint = ""
        if template:
            template_hint = f"""
参考已有任务模板（可根据需要调整）：
模板名称: {template['name']}
模板步骤: {json.dumps(template.get('steps', []), ensure_ascii=False)}
"""

        prompt = f"""你是一个高效的任务分析专家。请将以下任务拆解为3-7个可执行的子步骤。

任务描述: {description}
{f'额外上下文: {context}' if context else ''}
{template_hint}

要求：
1. 每个步骤必须是一个具体的、可执行的操作
2. 明确每个步骤需要的技能/工具
3. 给出每个步骤的验收标准
4. 步骤之间要有逻辑顺序

可用的技能/工具列表：
- tool_web_search: 搜索互联网
- tool_web_read: 读取网页
- tool_file_read: 读取文件
- tool_file_write: 写入文件
- tool_bash: 执行命令
- tool_spreadsheet: 处理表格
- llm_generate: 用AI生成内容（文案、邮件、报告等）
- llm_analyze: 用AI分析数据/文本
- llm_summarize: 用AI做摘要

返回纯JSON，格式：
{{
  "steps": [
    {{
      "description": "步骤描述",
      "required_skills": ["skill_name"],
      "acceptance_criteria": "怎么算完成"
    }}
  ]
}}"""

        result = await self._brain.think_json(
            "你是任务分析专家，只返回JSON。",
            prompt,
        )

        steps = []
        for i, s in enumerate(result.get("steps", [])):
            steps.append(TaskStep(
                id=f"step_{i+1}",
                description=s.get("description", f"步骤 {i+1}"),
                required_skills=s.get("required_skills", []),
                acceptance_criteria=s.get("acceptance_criteria", ""),
            ))

        if not steps:
            # 如果大模型没返回有效步骤，创建一个兜底步骤
            steps = [TaskStep(
                id="step_1",
                description=description,
                required_skills=["llm_generate"],
                acceptance_criteria="任务完成",
            )]

        await emit_thinking(
            f"拆解完成: {len(steps)} 个步骤",
            " → ".join(s.description[:20] for s in steps),
        )

        return steps

    # ─── Step 2: 能力自检与技能准备 ─────────────────────────

    async def _step2_prepare_skills(self, task: GenericTask) -> None:
        """
        检查所有步骤需要的技能，自动安装或自造缺少的。

        策略（按优先级）：
        1. 已有工具 → 直接用
        2. 技能目录有 → 安装
        3. 技能目录没有 → 调用 ToolForge 自造！
        4. 造不出来 → 标记为用大模型兜底
        """
        all_skills = set()
        for step in task.decomposed_steps:
            all_skills.update(step.required_skills)

        missing = []
        forged = []

        for skill_name in all_skills:
            # 检查 tool dispatcher 是否已有该工具
            if skill_name.startswith("tool_") and self._tools.has_tool(skill_name):
                continue
            # LLM 技能始终可用
            if skill_name.startswith("llm_"):
                continue
            # 尝试从技能目录安装
            installed = self._skills.install(skill_name)
            if installed:
                await emit_skill(f"安装技能: {installed.name}", installed.description)
                continue

            # ── 技能目录也没有 → 尝试自造！──────────────────
            if skill_name.startswith("tool_"):
                # 找到需要这个技能的步骤描述，作为造工具的需求
                need_description = self._describe_skill_need(skill_name, task)
                forge_result = await self._try_forge_tool(skill_name, need_description)
                if forge_result:
                    forged.append(skill_name)
                    continue

            missing.append(skill_name)

        if forged:
            await emit_skill(
                f"自造了 {len(forged)} 个新工具！",
                ", ".join(forged),
                data={"forged_tools": forged},
            )

        if missing:
            await emit_skill(
                f"部分技能无法自造",
                f"缺少: {', '.join(missing)}，将用大模型兜底",
                data={"missing_skills": missing},
            )

    async def _try_forge_tool(self, tool_name: str, need_description: str) -> bool:
        """尝试用 ToolForge 自造一个工具"""
        try:
            from anima.tools.forge import ToolForge
            import os
            from pathlib import Path

            data_dir = Path(os.getenv("ANIMA_DATA_DIR", "./data"))
            forge = ToolForge(data_dir, self._brain, self._tools)

            result = await forge.forge_tool(need_description, tool_name=tool_name)
            return result.get("success", False)

        except Exception as e:
            logger.warning(f"[TaskProcessor] ToolForge 失败: {e}")
            return False

    def _describe_skill_need(self, skill_name: str, task: GenericTask) -> str:
        """根据步骤描述，生成造工具的需求说明"""
        descriptions = []
        for step in task.decomposed_steps:
            if skill_name in step.required_skills:
                descriptions.append(step.description)

        if descriptions:
            return f"需要一个工具来完成以下操作：{'; '.join(descriptions)}"
        else:
            # 从工具名推断
            clean_name = skill_name.replace("tool_", "").replace("_", " ")
            return f"需要一个工具来执行: {clean_name}"

    # ─── Step 3: 生成执行计划 ────────────────────────────────

    async def _step3_generate_plan(self, task: GenericTask) -> TaskPlan:
        """让大模型为拆解好的步骤生成执行计划"""
        steps_desc = json.dumps(
            [{"id": s.id, "desc": s.description, "skills": s.required_skills}
             for s in task.decomposed_steps],
            ensure_ascii=False,
        )

        prompt = f"""基于以下任务步骤，生成执行计划：

步骤列表：{steps_desc}

请确定：
1. 执行顺序（哪些可以并行，哪些有依赖）
2. 每个步骤失败时的降级方案
3. 预计完成时间

返回JSON：
{{
  "execution_order": ["step_1", "step_2", ...],
  "estimated_time": "预计时间",
  "fallback_strategy": "整体降级方案"
}}"""

        result = await self._brain.think_json(
            "你是执行计划专家，只返回JSON。",
            prompt,
        )

        order = result.get("execution_order", [s.id for s in task.decomposed_steps])

        plan = TaskPlan(
            steps=task.decomposed_steps,
            execution_order=order,
            estimated_time=result.get("estimated_time", "未知"),
            fallback_strategy=result.get("fallback_strategy", "失败则用大模型兜底"),
        )

        await emit_thinking(
            f"执行计划就绪",
            f"顺序: {' → '.join(order)}，预计: {plan.estimated_time}",
        )

        return plan

    # ─── Step 4: 自动执行 ────────────────────────────────────

    async def _step4_execute(self, task: GenericTask) -> None:
        """按计划顺序执行每个步骤"""
        plan = task.plan
        accumulated_context = ""  # 累积上下文，传递给后续步骤

        for step_id in plan.execution_order:
            step = next((s for s in plan.steps if s.id == step_id), None)
            if not step:
                continue

            step.status = "executing"
            await emit_action(
                f"执行: {step.description[:40]}",
                f"技能: {', '.join(step.required_skills)}",
            )

            try:
                result = await self._execute_single_step(step, accumulated_context, task.description)
                step.result = result
                step.status = "done"
                accumulated_context += f"\n[{step.description}的结果]: {result[:500]}"

                task.execution_log.append({
                    "step_id": step_id,
                    "status": "done",
                    "result_preview": result[:200],
                    "timestamp": datetime.utcnow().isoformat(),
                })

            except Exception as e:
                step.retry_count += 1
                if step.retry_count <= self.MAX_STEP_RETRIES:
                    # 重试
                    await emit_action(f"步骤失败，重试 ({step.retry_count}/{self.MAX_STEP_RETRIES})", str(e)[:60])
                    try:
                        result = await self._execute_single_step(step, accumulated_context, task.description)
                        step.result = result
                        step.status = "done"
                        accumulated_context += f"\n[{step.description}的结果]: {result[:500]}"
                    except Exception as e2:
                        step.status = "failed"
                        step.result = f"执行失败: {e2}"
                        logger.warning(f"[TaskProcessor] Step {step_id} failed: {e2}")
                else:
                    step.status = "failed"
                    step.result = f"执行失败（已重试 {self.MAX_STEP_RETRIES} 次）: {e}"

    async def _execute_single_step(
        self, step: TaskStep, context: str, task_description: str
    ) -> str:
        """执行单个步骤：优先使用工具，兜底用大模型"""

        # 如果步骤需要工具执行
        for skill in step.required_skills:
            if skill.startswith("tool_") and self._tools.has_tool(skill):
                # 让大模型决定工具参数
                args_prompt = f"""你需要执行以下步骤：
步骤描述: {step.description}
可用工具: {skill}
前序步骤结果: {context[-1000:] if context else '无'}
整体任务: {task_description}

请返回调用这个工具时的参数，JSON格式：
{{"args": {{"参数名": "值"}}}}"""

                args_result = await self._brain.think_json(
                    "返回工具调用参数，纯JSON。", args_prompt
                )
                tool_args = args_result.get("args", {})

                result = await self._tools.execute(skill, tool_args)
                step.tool_used = skill
                return result

        # 兜底：用大模型直接完成
        llm_prompt = f"""请执行以下任务步骤并给出结果：

整体任务: {task_description}
当前步骤: {step.description}
验收标准: {step.acceptance_criteria}
前序步骤结果: {context[-2000:] if context else '无'}

请直接给出这个步骤的执行结果（内容、分析、文案等）。"""

        result = await self._brain.think(
            "你是一个高效的执行者，直接给出步骤的执行结果。",
            llm_prompt,
        )
        step.tool_used = "llm_generate"
        return result

    # ─── Step 5: 结果自检与修正 ──────────────────────────────

    async def _step5_check_and_correct(self, task: GenericTask) -> None:
        """让大模型检查执行结果，必要时修正"""

        # 汇总所有步骤结果
        results_summary = "\n".join(
            f"- {s.description}: {'✅' if s.status == 'done' else '❌'} {s.result[:200]}"
            for s in task.decomposed_steps
        )

        check_prompt = f"""请检查以下任务的执行结果是否达标：

任务目标: {task.description}

执行结果：
{results_summary}

请评估：
1. 总体质量分（0-100）
2. 是否需要修正？
3. 如果需要修正，具体修正哪些步骤、怎么修正？

返回JSON：
{{
  "quality_score": 85,
  "needs_correction": false,
  "corrections": [
    {{"step_id": "step_1", "issue": "问题", "fix_instruction": "修正方法"}}
  ],
  "overall_assessment": "总评"
}}"""

        check_result = await self._brain.think_json(
            "你是质量检查专家，只返回JSON。",
            check_prompt,
        )

        task.quality_score = float(check_result.get("quality_score", 70)) / 100.0
        needs_correction = check_result.get("needs_correction", False)
        corrections = check_result.get("corrections", [])

        if needs_correction and corrections and task.corrections_made < self.MAX_CORRECTIONS:
            task.status = TaskStatus.CORRECTING
            task.corrections_made += 1

            await emit_thinking(
                f"需要修正（第 {task.corrections_made} 次）",
                f"质量分: {int(task.quality_score * 100)}，修正 {len(corrections)} 个步骤",
            )

            for correction in corrections:
                step_id = correction.get("step_id", "")
                fix_instruction = correction.get("fix_instruction", "")
                step = next((s for s in task.decomposed_steps if s.id == step_id), None)
                if step and fix_instruction:
                    # 重新执行该步骤
                    step.description = f"{step.description}（修正: {fix_instruction}）"
                    context = "\n".join(s.result[:200] for s in task.decomposed_steps if s.result)
                    new_result = await self._execute_single_step(step, context, task.description)
                    step.result = new_result
                    step.status = "done"

            # 修正后再次自检（递归，但有次数限制）
            await self._step5_check_and_correct(task)
        else:
            assessment = check_result.get("overall_assessment", "任务完成")
            await emit_thinking(
                f"质检通过: {int(task.quality_score * 100)}分",
                assessment[:80],
            )

    # ─── Step 6: 汇报与归档 ──────────────────────────────────

    async def _step6_report_and_archive(self, task: GenericTask) -> None:
        """生成报告、归档、记录经历"""

        # 汇总最终结果
        all_results = "\n\n".join(
            f"### {s.description}\n{s.result}"
            for s in task.decomposed_steps
            if s.status == "done"
        )

        # 生成报告摘要
        report_prompt = f"""请为以下任务生成一份简洁的完成报告（不超过300字）：

任务: {task.description}
质量分: {int(task.quality_score * 100)}分
执行步骤数: {len(task.decomposed_steps)}
修正次数: {task.corrections_made}

各步骤结果：
{all_results[:3000]}

请给出一段简洁的完成报告。"""

        task.final_result = await self._brain.think(
            "你是一个汇报专家，生成简洁的任务完成报告。",
            report_prompt,
        )

        # 记忆归档
        self._memory.remember(
            content=f"完成任务: {task.description[:100]}，质量: {int(task.quality_score*100)}分",
            importance=0.7,
            tags=["task_completed", "universal_processor"],
        )

        # 记录成功经历
        from anima.models import ExperienceOutcome
        outcome = (
            ExperienceOutcome.SUCCESS if task.quality_score >= 0.7
            else ExperienceOutcome.PARTIAL if task.quality_score >= 0.4
            else ExperienceOutcome.FAILURE
        )
        self._evo.record(
            action=task.description[:200],
            method="通用任务处理器-6步闭环",
            outcome=outcome,
            lesson=f"质量{int(task.quality_score*100)}分，修正{task.corrections_made}次",
        )

        # 通知主人
        if self._notify:
            notification = (
                f"✅ 任务完成\n"
                f"📋 {task.description[:60]}\n"
                f"📊 质量: {int(task.quality_score*100)}分\n"
                f"⏱️ 步骤: {len(task.decomposed_steps)} | 修正: {task.corrections_made}\n\n"
                f"{task.final_result[:300]}"
            )
            await self._notify(notification)

        await emit_system(
            "任务完成",
            f"{task.description[:40]} | 质量: {int(task.quality_score*100)}分",
            data={
                "task_id": task.id,
                "quality_score": task.quality_score,
                "steps_count": len(task.decomposed_steps),
                "corrections": task.corrections_made,
            },
        )

    # ─── 辅助方法 ────────────────────────────────────────────

    @property
    def active_task_count(self) -> int:
        return len(self._active_tasks)

    def get_active_tasks(self) -> list[dict]:
        return [
            {
                "id": t.id,
                "description": t.description[:60],
                "status": t.status.value,
                "created_at": t.created_at,
            }
            for t in self._active_tasks.values()
        ]
