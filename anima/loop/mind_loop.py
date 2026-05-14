"""
Anima — Mind Loop（思维心跳循环）
这是整个系统的"生命迹象"——永不停止的感知-思考-行动循环。

透明化：每一步都通过 events 模块广播，前端实时可见。
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Callable, Awaitable

from anima.models import Signal, SignalType, QuestionSource, ExperienceOutcome, AnimaState
from anima.events import (
    emit_system, emit_perception, emit_thinking, emit_action,
    emit_skill, emit_question, emit_evolution, emit_memory,
)
from anima.tools.dispatcher import get_dispatcher

logger = logging.getLogger("anima.loop")

TICK_DEFAULT_S = 5 * 60
TICK_FAST_S    = 1 * 60
TICK_SLOW_S    = 30 * 60
REFLECT_EVERY  = 288
DECAY_EVERY    = 2016


class MindLoop:

    def __init__(self, *, identity_engine, memory_manager, trust_system,
                 skill_registry, question_tree, evolution_engine, brain,
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
        self._get_state   = get_state
        self._save_state  = save_state
        self._notify      = notify_owner
        self._default_interval = tick_interval_s
        self._running = False
        self._tick_count = 0
        self._task: asyncio.Task | None = None
        self._pending_signals: list[Signal] = []
        self._task_processor = None  # 延迟初始化

    @property
    def task_processor(self):
        """延迟初始化通用任务处理器"""
        if self._task_processor is None:
            from anima.task_processor import UniversalTaskProcessor
            from anima.task_templates import TaskTemplateStore
            from anima.tools.dispatcher import get_dispatcher
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

    async def _process_question(self, node, state: AnimaState) -> None:
        perms = self._trust.get_permissions()

        # 权限检查
        if not perms.auto_execute_routine and node.source != QuestionSource.OWNER:
            self._qtree.abandon(node.id, "信任等级不足，等待主人指示")
            await emit_question(
                "问题被搁置",
                f"{node.question[:50]}（信任度不足）",
                data={"reason": "trust_insufficient"},
            )
            return

        self._qtree.start(node.id)
        await emit_question(
            "开始处理问题",
            node.question[:80],
            data={"id": node.id, "priority": node.priority, "source": node.source.value},
        )

        # ── 组装上下文 ───────────────────────────────────────
        await emit_memory("检索相关记忆", f"查询: {node.question[:40]}...")

        ctx = self._memory.build_context(
            identity_prompt=self._identity.build_identity_prompt(state.identity),
            recent_messages=[], query_hint=node.question,
        )
        system_prompt = self._memory.format_context_as_system_prompt(ctx)

        injected_count = len(ctx.injected_memories)
        if injected_count > 0:
            await emit_memory(
                f"注入 {injected_count} 条相关记忆",
                "；".join(m.entry.content[:30] for m in ctx.injected_memories[:3]),
            )

        # ── 查询已有方法论 ───────────────────────────────────
        methodology = self._evo.find_methodology(node.question)
        method_hint = ""
        if methodology:
            method_hint = f"\n\n参考已有方法论：{methodology.method}"
            await emit_evolution(
                "应用已有方法论",
                methodology.scenario[:60],
                data={"effectiveness": methodology.effectiveness},
            )

        # ── 调用大脑思考 ─────────────────────────────────────
        think_prompt = (
            f"当前问题：{node.question}\n"
            f"优先级：{node.priority:.0%}{method_hint}\n\n"
            "请给出简洁行动方案（不超过200字）。"
        )

        await emit_thinking("正在思考...", node.question[:60])

        try:
            thinking = await self._brain.think(system_prompt, think_prompt)
        except Exception as e:
            logger.error(f"[MindLoop] 大脑调用失败: {e}")
            self._qtree.abandon(node.id, f"模型调用失败: {e}")
            await emit_thinking("思考失败", str(e), data={"error": True})
            return

        await emit_thinking(
            "思考完成",
            thinking[:120],
            data={"full_response_length": len(thinking)},
        )

        # ── 判断是否需要执行工具 ─────────────────────────────
        tool_result = await self._maybe_execute_tool(node.question, thinking, system_prompt)
        if tool_result:
            thinking = thinking + f"\n\n[工具执行结果]\n{tool_result}"

        # ── 自动发现并安装技能 ───────────────────────────────
        needed = self._skills.discover_for_task(node.question)
        installed: list[str] = []

        if needed and perms.auto_install_skill:
            for spec in needed:
                skill = self._skills.install(spec["id"])
                if skill:
                    installed.append(skill.name)
                    await emit_skill(
                        f"安装新技能: {skill.name}",
                        skill.description,
                        data={"skill_id": skill.id, "domains": skill.domains},
                    )

        # ── 自动激活新领域 ───────────────────────────────────
        new_domains = self._identity.infer_domains(state.identity, node.question)
        for domain in new_domains:
            domain_skills = self._skills.activate_domain(domain)
            installed.extend(s.name for s in domain_skills)
            from anima.identity.engine import DOMAIN_LABELS
            await emit_action(
                f"激活新领域: {DOMAIN_LABELS.get(domain, domain)}",
                f"自动安装 {len(domain_skills)} 个必备技能",
                data={"domain": domain, "skills_installed": len(domain_skills)},
            )

        # ── 记录经历 ─────────────────────────────────────────
        self._evo.record(
            action=node.question, method=thinking[:200],
            outcome=ExperienceOutcome.PARTIAL, question_id=node.id,
        )

        # ── 标记问题完成 ─────────────────────────────────────
        self._qtree.resolve(node.id, thinking[:300])
        await emit_question(
            "问题已解决",
            node.question[:60],
            data={"resolution_preview": thinking[:100]},
        )

        # ── 衍生子问题 ───────────────────────────────────────
        await self._spawn_children(node.id, thinking, node.priority)

        # ── 通知主人 ─────────────────────────────────────────
        should_notify = (
            perms.auto_message and (
                node.priority > 0.8
                or (node.priority > 0.5 and state.identity.personality.proactivity > 0.7)
                or node.source == QuestionSource.OWNER
                or bool(installed)
            )
        )
        if should_notify:
            msg = f"💡 **{node.question[:50]}**\n\n{thinking[:200]}"
            if installed:
                msg += f"\n\n🔧 已安装新技能：{', '.join(installed)}"
            if new_domains:
                from anima.identity.engine import DOMAIN_LABELS
                msg += f"\n📂 已激活新领域：{'、'.join(DOMAIN_LABELS.get(d, d) for d in new_domains)}"
            await self._notify(msg)
            await emit_action("通知主人", msg[:80])

    async def _maybe_execute_tool(self, question: str, thinking: str, system_prompt: str) -> str | None:
        """
        让大脑判断是否需要执行工具。
        如果需要，调用 dispatcher 执行并返回结果。
        """
        dispatcher = get_dispatcher()
        available = dispatcher.available_tools

        if not available:
            return None

        # 让大脑判断是否需要使用工具
        tool_prompt = f"""你刚才对问题「{question}」做了分析，得出方案：
{thinking[:300]}

你现在可以使用以下工具来执行具体操作：
{chr(10).join(f"- {t}" for t in available)}

如果需要执行工具，请返回 JSON：
{{"use_tool": true, "tool_name": "工具名", "args": {{"参数名": "值"}}}}

如果不需要工具（纯思考/建议类问题），返回：
{{"use_tool": false}}"""

        try:
            result = await self._brain.think_json(system_prompt, tool_prompt)

            if not result.get("use_tool"):
                return None

            tool_name = result.get("tool_name", "")
            tool_args = result.get("args", {})

            if not tool_name or not dispatcher.has_tool(tool_name):
                return None

            # 执行工具
            await emit_action(f"准备执行工具: {tool_name}", str(tool_args)[:60])
            tool_output = await dispatcher.execute(tool_name, tool_args)

            return tool_output

        except Exception as e:
            logger.warning(f"[MindLoop] 工具判断/执行失败: {e}")
            return None

    async def _spawn_children(self, parent_id: str, thinking: str, priority: float) -> None:
        if priority < 0.4:
            return
        try:
            result = await self._brain.think_json(
                "从行动方案中提炼需要进一步处理的子问题，如无则返回空列表。",
                f"行动方案：\n{thinking}\n\n返回JSON：{{\"sub_questions\": [\"子问题1\"]}}",
            )
            for q in result.get("sub_questions", [])[:2]:
                if q and len(q) > 5:
                    self._qtree.add_child(parent_id, q)
                    await emit_question("衍生子问题", q[:60], data={"parent_id": parent_id})
        except Exception:
            pass

    async def _run_scheduled(self, state: AnimaState) -> None:
        if self._tick_count % REFLECT_EVERY == 0 and self._tick_count > 0:
            await self._daily_reflect(state)
        if self._tick_count % DECAY_EVERY == 0 and self._tick_count > 0:
            decayed = self._memory.run_decay()
            await emit_memory(f"记忆衰减完成", f"影响 {decayed} 条记忆")
            self._trust.adjust("week_no_issues")

    async def _daily_reflect(self, state: AnimaState) -> None:
        await emit_evolution("开始每日复盘", "分析近期经历，提炼方法论...")
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
            await self._notify(f"📊 每日复盘完成\n{assessment}")

        except Exception as e:
            logger.error(f"[MindLoop] 复盘失败: {e}", exc_info=True)
            await emit_evolution("复盘失败", str(e), data={"error": True})

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
