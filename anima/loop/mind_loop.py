"""
Anima — Mind Loop（思维心跳循环）

架构：框架是国王，LLM是外交官。

处理流程：
  信号进入 → 规则引擎匹配 →
    命中 → 直接执行（LLM 无权否决）
    未命中 → 知识图扩散激活提供上下文 → LLM 只负责组织语言

每一步通过 events 模块广播，前端实时可见。
行为监控记录每一步的结果，闭环自动生成新规则。
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime
from typing import Callable, Awaitable

from anima.models import Signal, SignalType, QuestionSource, ExperienceOutcome, AnimaState
from anima.events import (
    emit_system, emit_perception, emit_thinking, emit_action,
    emit_skill, emit_question, emit_evolution, emit_memory,
)
from anima.tools.dispatcher import get_dispatcher
from anima.monitor.behavior import BehaviorMonitor, ActionRecord

logger = logging.getLogger("anima.loop")

TICK_DEFAULT_S = 5 * 60
TICK_FAST_S    = 1 * 60
TICK_SLOW_S    = 30 * 60
REFLECT_EVERY  = 288
DECAY_EVERY    = 2016


class MindLoop:

    def __init__(self, *, identity_engine, memory_manager, trust_system,
                 skill_registry, question_tree, evolution_engine, brain,
                 rule_engine, behavior_monitor,
                 get_state: Callable[[], Awaitable[AnimaState]],
                 save_state: Callable[[AnimaState], Awaitable[None]],
                 notify_owner: Callable[[str], Awaitable[None]],
                 tick_interval_s: int = TICK_DEFAULT_S):
        self._identity = identity_engine
        self._memory   = memory_manager
        self._trust    = trust_system
        self._skills   = skill_registry
        self._qtree    = question_tree
        self._evo      = evolution_engine
        self._brain    = brain
        self._rules    = rule_engine
        self._monitor  = behavior_monitor
        self._get_state   = get_state
        self._save_state  = save_state
        self._notify      = notify_owner
        self._default_interval = tick_interval_s
        self._running = False
        self._tick_count = 0
        self._task: asyncio.Task | None = None
        self._pending_signals: list[Signal] = []
        self._task_processor = None
        self._consecutive_errors = 0

    @property
    def task_processor(self):
        """延迟初始化通用任务处理器"""
        if self._task_processor is None:
            from anima.task_processor import UniversalTaskProcessor
            from anima.task_templates import TaskTemplateStore
            import os
            from pathlib import Path

            data_dir = Path(os.getenv("ANIMA_DATA_DIR", "./data"))
            self._task_processor = UniversalTaskProcessor(
                brain=self._brain,
                skill_registry=self._skills,
                tool_dispatcher=get_dispatcher(),
                evolution_engine=self._evo,
                memory_manager=self._memory,
                identity_engine=self._identity,
                template_store=TaskTemplateStore(data_dir, brain=self._brain),
                notify_fn=self._notify,
            )
        return self._task_processor

    async def process_task(self, task_description: str, context: str = ""):
        """公开接口：提交一个通用任务给任务处理器"""
        return await self.task_processor.process_task(task_description, context)

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("[MindLoop] 心跳启动 ✓")

    def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()

    async def tick_once(self, external_signals: list[Signal] | None = None) -> None:
        await self._tick(external_signals or [])

    def inject_signal(self, signal: Signal) -> None:
        self._pending_signals.append(signal)

    async def _loop(self) -> None:
        await emit_system("心跳循环启动", f"间隔: {self._default_interval}s")
        while self._running:
            try:
                external = self._pending_signals.copy()
                self._pending_signals.clear()
                await self._tick(external)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[MindLoop] tick 异常: {e}", exc_info=True)
                await emit_system("心跳异常", str(e), data={"error": True})
            await asyncio.sleep(self._calc_interval())
        await emit_system("心跳循环停止")

    async def _tick(self, external_signals: list[Signal]) -> None:
        self._tick_count += 1
        state = await self._get_state()

        next_interval = self._calc_interval()
        await emit_system(
            f"心跳 #{self._tick_count}",
            f"下次: {next_interval}s 后",
            data={"tick": self._tick_count, "next_interval_s": next_interval},
        )

        # ── Step 1: 收集信号 ─────────────────────────────────
        signals = external_signals + self._gen_internal_signals(state)

        for sig in signals:
            if sig.strength < 0.3:
                continue

            await emit_perception(
                f"感知到 {sig.type.value} 信号",
                f"强度: {sig.strength:.0%} | {sig.payload}",
                data={"signal_type": sig.type.value, "strength": sig.strength},
            )

            # ── 规则引擎先手 ─────────────────────────────────
            rule_action = await self._try_rule_engine(sig, state)
            if rule_action:
                # 规则命中 → 直接执行，不问 LLM
                continue

            # ── 规则未命中 → 生成问题交给后续处理 ────────────
            q = self._signal_to_question(sig, state)
            if q:
                self._qtree.add_root(q, QuestionSource.INSTINCT, sig.strength)
                await emit_question(
                    "新问题产生",
                    q[:80],
                    data={"source": "instinct", "priority": sig.strength},
                )

        # ── Step 2: 处理最高优先级问题 ───────────────────────
        node = self._qtree.next_pending()
        if node:
            await self._process_question(node, state)

        # ── Step 3: 定期任务 ─────────────────────────────────
        await self._run_scheduled(state)

        # ── Step 4: 保存状态 ─────────────────────────────────
        state.tick_count = self._tick_count
        state.last_tick_at = datetime.utcnow().isoformat()
        await self._save_state(state)

    # ═══════════════════════════════════════════════════════════
    # 框架层决策：规则引擎
    # ═══════════════════════════════════════════════════════════

    async def _try_rule_engine(self, sig: Signal, state: AnimaState) -> bool:
        """
        让规则引擎先评估信号。
        如果命中规则 → 直接执行 → 返回 True。
        未命中 → 返回 False，交给 LLM。
        """
        # 构建规则评估上下文
        hour = datetime.utcnow().hour
        context = {
            "signal_type": sig.type.value,
            "message": sig.payload.get("content", ""),
            "question": sig.payload.get("content", sig.payload.get("event", "")),
            "strength": sig.strength,
            "consecutive_errors": self._consecutive_errors,
            "is_quiet_hours": hour >= 22 or hour < 7,
            "trust_level": state.trust.level.value,
            **sig.payload,
        }

        action = self._rules.evaluate(context)
        if not action:
            return False

        # 规则命中 → 执行
        await emit_action(
            "⚡ 规则引擎直接决策",
            f"类型: {action.action_type}",
            data={"action_type": action.action_type, "params": action.params},
        )

        success = await self._execute_rule_action(action, context)

        # 记录到行为监控
        self._monitor.record(ActionRecord(
            id=str(uuid.uuid4())[:12],
            timestamp=datetime.utcnow().isoformat(),
            signal_type=sig.type.value,
            question=context.get("question", ""),
            message=context.get("message", ""),
            decision_source="rule",
            rule_id=None,  # TODO: 从 evaluate 中传出 rule_id
            tool_used=action.tool_name,
            success=success,
        ))

        if success:
            self._consecutive_errors = 0
        else:
            self._consecutive_errors += 1

        return True

    async def _execute_rule_action(self, action, context: dict) -> bool:
        """执行规则引擎返回的 Action"""
        try:
            if action.action_type == "execute_tool":
                return await self._execute_tool_action(action, context)

            elif action.action_type == "respond":
                await self._notify(action.response_text)
                return True

            elif action.action_type == "suppress":
                await emit_action("信号被抑制", action.params.get("reason", "规则抑制"))
                return True

            elif action.action_type == "notify":
                await self._notify(action.params.get("text", ""))
                return True

            elif action.action_type == "modify_state":
                # 修改内部状态（未来扩展）
                logger.info(f"[MindLoop] 状态修改: {action.state_changes}")
                return True

            elif action.action_type == "delegate_llm":
                # 仍交给 LLM，但注入约束
                # 这里不执行，只是标记约束，让后续 _process_question 处理
                return False

            elif action.action_type == "chain":
                # 链式执行
                for sub in action.params.get("actions", []):
                    from anima.rules.engine import RuleAction
                    sub_action = RuleAction(action_type=sub["action_type"], params=sub.get("params", {}))
                    await self._execute_rule_action(sub_action, context)
                return True

            else:
                logger.warning(f"[MindLoop] 未知 action_type: {action.action_type}")
                return False

        except Exception as e:
            logger.error(f"[MindLoop] 规则执行失败: {e}")
            return False

    async def _execute_tool_action(self, action, context: dict) -> bool:
        """执行工具类动作"""
        dispatcher = get_dispatcher()
        tool_name = action.tool_name

        if not tool_name or not dispatcher.has_tool(tool_name):
            logger.warning(f"[MindLoop] 工具不存在: {tool_name}")
            return False

        # 从 context 中提取工具参数
        tool_args = dict(action.tool_args)
        if extract_from := action.params.get("extract_query_from"):
            tool_args["query"] = context.get(extract_from, "")
        if extract_from := action.params.get("extract_content_from"):
            tool_args["content"] = context.get(extract_from, "")

        await emit_action(f"执行工具: {tool_name}", str(tool_args)[:80])

        try:
            result = await dispatcher.execute(tool_name, tool_args)
            await emit_action(f"工具完成: {tool_name}", str(result)[:120])

            # 如果有结果，通知主人
            if result and action.params.get("notify_result", True):
                await self._notify(f"🔧 {tool_name} 执行完成\n\n{str(result)[:500]}")

            return True
        except Exception as e:
            logger.error(f"[MindLoop] 工具执行失败: {tool_name}: {e}")
            return False

    # ═══════════════════════════════════════════════════════════
    # LLM 层：只负责表达（当规则引擎未命中时）
    # ═══════════════════════════════════════════════════════════

    async def _process_question(self, node, state: AnimaState) -> None:
        """
        处理问题。新流程：
          1. 规则引擎二次检查（用问题内容匹配）
          2. 知识图扩散激活（提供联想上下文）
          3. LLM 只负责组织语言表达

        LLM 不再决定"做什么"——框架已经决定了。
        LLM 只回答"怎么说"。
        """
        perms = self._trust.get_permissions()

        # 权限检查
        if not perms.auto_execute_routine and node.source != QuestionSource.OWNER:
            self._qtree.abandon(node.id, "信任等级不足")
            await emit_question("问题被搁置", f"{node.question[:50]}（信任度不足）")
            return

        self._qtree.start(node.id)
        await emit_question(
            "开始处理问题",
            node.question[:80],
            data={"id": node.id, "priority": node.priority, "source": node.source.value},
        )

        # ── Step A: 规则引擎二次匹配（用问题内容） ────────────
        rule_context = {
            "question": node.question,
            "message": node.question,
            "signal_type": "question",
            "priority": node.priority,
            "consecutive_errors": self._consecutive_errors,
            "is_quiet_hours": datetime.utcnow().hour >= 22 or datetime.utcnow().hour < 7,
        }
        rule_action = self._rules.evaluate(rule_context)

        if rule_action and rule_action.action_type != "delegate_llm":
            # 规则直接解决
            await emit_action("⚡ 规则引擎接管问题", f"{rule_action.action_type}")
            success = await self._execute_rule_action(rule_action, rule_context)
            self._qtree.resolve(node.id, f"[规则引擎直接处理: {rule_action.action_type}]")

            self._monitor.record(ActionRecord(
                id=str(uuid.uuid4())[:12],
                timestamp=datetime.utcnow().isoformat(),
                signal_type="question",
                question=node.question,
                decision_source="rule",
                success=success,
            ))
            return

        # ── Step B: 知识图扩散激活（联想上下文） ──────────────
        await emit_memory("知识图扩散激活", f"查询: {node.question[:40]}...")

        kg_context = ""
        if hasattr(self._memory, '_kg') and self._memory._kg:
            # 从问题中提取关键概念，做扩散激活
            kg_results = self._memory._kg.recall(node.question[:30])
            if kg_results:
                kg_context = self._memory._kg.recall_as_text(node.question[:30])
                await emit_memory(
                    f"扩散激活召回 {len(kg_results)} 个关联概念",
                    kg_context[:100],
                )

        # ── Step C: 组装上下文（框架准备好"要说什么"） ─────────
        ctx = self._memory.build_context(
            identity_prompt=self._identity.build_identity_prompt(state.identity),
            recent_messages=[], query_hint=node.question,
        )

        # 框架决定的约束和方向
        framework_directive = self._build_framework_directive(node, state, kg_context, rule_action)

        # ── Step D: LLM 只负责表达 ───────────────────────────
        system_prompt = self._memory.format_context_as_system_prompt(ctx)

        # LLM 的角色被限定为"表达"
        expression_prompt = (
            f"{framework_directive}\n\n"
            f"请用简洁自然的语言表达以上决策结果。不超过200字。"
        )

        await emit_thinking("LLM 组织表达...", node.question[:60])

        try:
            response = await self._brain.think(system_prompt, expression_prompt)
        except Exception as e:
            logger.error(f"[MindLoop] LLM 调用失败: {e}")
            self._qtree.abandon(node.id, f"表达层失败: {e}")
            self._monitor.record(ActionRecord(
                id=str(uuid.uuid4())[:12],
                timestamp=datetime.utcnow().isoformat(),
                signal_type="question",
                question=node.question,
                decision_source="llm",
                success=False,
                error=str(e),
            ))
            self._consecutive_errors += 1
            return

        await emit_thinking("表达完成", response[:120])

        # ── Step E: 工具执行（如果需要） ─────────────────────
        tool_result = await self._maybe_execute_tool(node.question, response, system_prompt)
        if tool_result:
            response = response + f"\n\n[执行结果]\n{tool_result}"

        # ── Step F: 记录 + 通知 ──────────────────────────────
        self._evo.record(
            action=node.question, method=response[:200],
            outcome=ExperienceOutcome.PARTIAL, question_id=node.id,
        )

        self._qtree.resolve(node.id, response[:300])

        # 行为监控记录
        self._monitor.record(ActionRecord(
            id=str(uuid.uuid4())[:12],
            timestamp=datetime.utcnow().isoformat(),
            signal_type="question",
            question=node.question,
            decision_source="llm",
            tool_used=None,
            success=True,
        ))
        self._consecutive_errors = 0

        # 通知主人
        should_notify = (
            perms.auto_message and (
                node.priority > 0.8
                or node.source == QuestionSource.OWNER
                or (node.priority > 0.5 and state.identity.personality.proactivity > 0.7)
            )
        )
        if should_notify:
            await self._notify(f"💡 **{node.question[:50]}**\n\n{response[:300]}")
            await emit_action("通知主人", response[:80])

    def _build_framework_directive(
        self, node, state: AnimaState, kg_context: str, rule_action=None
    ) -> str:
        """
        框架层组装"要表达什么"的指令。
        这不是建议——这是 LLM 必须表达的内容。
        """
        parts = [f"## 框架决策结果\n\n问题：{node.question}"]

        # 知识图上下文
        if kg_context:
            parts.append(f"\n## 相关知识（扩散激活）\n{kg_context}")

        # 如果规则引擎给出了约束（delegate_llm 类型）
        if rule_action and rule_action.action_type == "delegate_llm":
            parts.append(f"\n## 强制约束\n{rule_action.llm_constraints}")

        # 方法论
        methodology = self._evo.find_methodology(node.question)
        if methodology:
            parts.append(f"\n## 已验证方法论\n场景: {methodology.scenario}\n方法: {methodology.method}")

        # 优先级和来源
        parts.append(f"\n优先级: {node.priority:.0%} | 来源: {node.source.value}")

        return "\n".join(parts)

    async def _maybe_execute_tool(self, question: str, thinking: str, system_prompt: str) -> str | None:
        """
        工具执行判断。
        注意：简单的确定性工具调用已被规则引擎处理。
        这里只处理规则未覆盖的、需要 LLM 判断的复杂工具调用。
        """
        dispatcher = get_dispatcher()
        available = dispatcher.available_tools

        if not available:
            return None

        tool_prompt = f"""你刚才对问题「{question}」做了分析，得出方案：
{thinking[:300]}

可用工具：
{chr(10).join(f"- {t}" for t in available)}

如果需要执行工具，返回 JSON：
{{"use_tool": true, "tool_name": "工具名", "args": {{"参数名": "值"}}}}

如果不需要工具，返回：
{{"use_tool": false}}"""

        try:
            result = await self._brain.think_json(system_prompt, tool_prompt)

            if not result.get("use_tool"):
                return None

            tool_name = result.get("tool_name", "")
            tool_args = result.get("args", {})

            if not tool_name or not dispatcher.has_tool(tool_name):
                return None

            await emit_action(f"执行工具: {tool_name}", str(tool_args)[:60])
            tool_output = await dispatcher.execute(tool_name, tool_args)

            # 记录工具使用（供行为监控学习）
            self._monitor.record(ActionRecord(
                id=str(uuid.uuid4())[:12],
                timestamp=datetime.utcnow().isoformat(),
                signal_type="tool_call",
                question=question,
                decision_source="llm",
                tool_used=tool_name,
                success=True,
            ))

            return tool_output

        except Exception as e:
            logger.warning(f"[MindLoop] 工具执行失败: {e}")
            return None

    # ═══════════════════════════════════════════════════════════
    # 定期任务
    # ═══════════════════════════════════════════════════════════

    async def _run_scheduled(self, state: AnimaState) -> None:
        if self._tick_count % REFLECT_EVERY == 0 and self._tick_count > 0:
            await self._daily_reflect(state)
        if self._tick_count % DECAY_EVERY == 0 and self._tick_count > 0:
            await self._run_decay(state)

    async def _run_decay(self, state: AnimaState) -> None:
        """定期衰减：记忆衰减 + 规则置信度衰减 + 知识图边权衰减"""
        # 记忆衰减
        decayed = self._memory.run_decay()
        await emit_memory(f"记忆衰减完成", f"影响 {decayed} 条记忆")

        # 规则置信度衰减
        removed_rules = self._rules.decay_confidence()
        if removed_rules:
            await emit_evolution(f"规则衰减", f"清除 {removed_rules} 条低置信度规则")

        # 知识图边权衰减
        if hasattr(self._memory, '_kg') and self._memory._kg:
            removed_edges = self._memory._kg.decay_all_edges()
            if removed_edges:
                await emit_memory(f"知识图遗忘", f"删除 {removed_edges} 条弱关联")

        # 信任调整
        self._trust.adjust("week_no_issues")

    async def _daily_reflect(self, state: AnimaState) -> None:
        """每日复盘 + 行为监控全量分析"""
        await emit_evolution("开始每日复盘", "分析近期经历 + 行为模式检测...")

        # 行为监控全量分析
        new_patterns = self._monitor.analyze()
        if new_patterns:
            for p in new_patterns:
                await emit_evolution(
                    f"发现新模式: {p.pattern_type}",
                    p.description[:80],
                )

        # Evolution 反思
        try:
            result = await self._evo.reflect(state, self._brain.think_json)

            adj = result.get("personality_adjustments", {})
            if adj.get("proactivity_delta") or adj.get("risk_tolerance_delta"):
                self._identity.update_personality(
                    state.identity,
                    proactivity_delta=float(adj.get("proactivity_delta", 0)),
                    risk_tolerance_delta=float(adj.get("risk_tolerance_delta", 0)),
                )
                await emit_evolution("人格参数微调", f"主动性 Δ{adj.get('proactivity_delta', 0):+.2f}")

            for gap in result.get("skill_gaps", []):
                self._qtree.add_root(
                    f"我在「{gap}」方面能力不足，需要学习提升",
                    QuestionSource.SELF_REFLECTION, priority=0.55,
                )
                await emit_evolution("发现能力短板", gap)

            assessment = result.get("assessment", "复盘完成")
            await emit_evolution("复盘完成", assessment)

            # 附带监控统计
            monitor_stats = self._monitor.stats()
            summary = (
                f"📊 每日复盘完成\n{assessment}\n\n"
                f"📈 行为统计: 总决策 {monitor_stats['total_records']} | "
                f"规则占比 {monitor_stats['rule_ratio']:.0%} | "
                f"新模式 {len(new_patterns)}"
            )
            await self._notify(summary)

        except Exception as e:
            logger.error(f"[MindLoop] 复盘失败: {e}", exc_info=True)
            await emit_evolution("复盘失败", str(e), data={"error": True})

    # ═══════════════════════════════════════════════════════════
    # 信号处理
    # ═══════════════════════════════════════════════════════════

    def _gen_internal_signals(self, state: AnimaState) -> list[Signal]:
        signals: list[Signal] = []
        hour = datetime.utcnow().hour
        if hour == 9 and self._tick_count % 12 == 0:
            signals.append(Signal(type=SignalType.TIME, payload={"event": "work_start"}, strength=0.65))
        if hour == 17 and self._tick_count % 12 == 0:
            signals.append(Signal(type=SignalType.TIME, payload={"event": "work_end"}, strength=0.7))
        if self._tick_count % 10 == 0:
            signals.append(Signal(type=SignalType.INTERNAL, payload={"event": "self_check"}, strength=0.4))
        return signals

    def _signal_to_question(self, sig: Signal, state: AnimaState) -> str | None:
        owner = state.identity.owner_name
        payload = sig.payload
        if sig.type == SignalType.TIME:
            event = payload.get("event")
            if event == "work_start":
                return f"今天工作开始了，{owner} 今天可能需要什么？有什么是我应该主动准备的？"
            if event == "work_end":
                return f"工作即将结束，需要给 {owner} 整理今日工作总结和明日待办吗？"
        if sig.type == SignalType.INTERNAL:
            if payload.get("event") == "self_check":
                return "我最近有哪些任务处理得不够好？是否存在需要安装的新技能？"
        if sig.type == SignalType.MESSAGE:
            return payload.get("content") or None
        if sig.type == SignalType.ENVIRONMENT:
            return f"环境发生变化：{payload}，这对 {owner} 的工作有影响吗？"
        return None

    def _calc_interval(self) -> int:
        hour = datetime.utcnow().hour
        if hour >= 22 or hour < 7:
            return TICK_SLOW_S
        if self._pending_signals:
            if max(s.strength for s in self._pending_signals) > 0.8:
                return TICK_FAST_S
        return self._default_interval
