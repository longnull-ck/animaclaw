"""
Anima — Mind Loop（思维心跳循环）
这是整个系统的"生命迹象"——永不停止的感知-思考-行动循环。
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Callable, Awaitable

from anima.models import Signal, SignalType, QuestionSource, ExperienceOutcome, AnimaState

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
        while self._running:
            try:
                external = self._pending_signals.copy()
                self._pending_signals.clear()
                await self._tick(external)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[MindLoop] tick 异常: {e}", exc_info=True)
            await asyncio.sleep(self._calc_interval())

    async def _tick(self, external_signals: list[Signal]) -> None:
        self._tick_count += 1
        state = await self._get_state()

        signals = external_signals + self._gen_internal_signals(state)
        for sig in signals:
            if sig.strength < 0.3:
                continue
            q = self._signal_to_question(sig, state)
            if q:
                self._qtree.add_root(q, QuestionSource.INSTINCT, sig.strength)

        node = self._qtree.next_pending()
        if node:
            await self._process_question(node, state)

        await self._run_scheduled(state)

        state.tick_count = self._tick_count
        state.last_tick_at = datetime.utcnow().isoformat()
        await self._save_state(state)

    async def _process_question(self, node, state: AnimaState) -> None:
        perms = self._trust.get_permissions()
        if not perms.auto_execute_routine and node.source != QuestionSource.OWNER:
            self._qtree.abandon(node.id, "信任等级不足，等待主人指示")
            return

        self._qtree.start(node.id)
        ctx = self._memory.build_context(
            identity_prompt=self._identity.build_identity_prompt(state.identity),
            recent_messages=[], query_hint=node.question,
        )
        system_prompt = self._memory.format_context_as_system_prompt(ctx)
        methodology = self._evo.find_methodology(node.question)
        method_hint = f"\n\n参考已有方法论：{methodology.method}" if methodology else ""

        think_prompt = f"当前问题：{node.question}\n优先级：{node.priority:.0%}{method_hint}\n\n请给出简洁行动方案（不超过200字）。"

        try:
            thinking = await self._brain.think(system_prompt, think_prompt)
        except Exception as e:
            logger.error(f"[MindLoop] 大脑调用失败: {e}")
            self._qtree.abandon(node.id, f"模型调用失败: {e}")
            return

        needed = self._skills.discover_for_task(node.question)
        installed: list[str] = []
        if needed and perms.auto_install_skill:
            for spec in needed:
                skill = self._skills.install(spec["id"])
                if skill:
                    installed.append(skill.name)

        new_domains = self._identity.infer_domains(state.identity, node.question)
        for domain in new_domains:
            domain_skills = self._skills.activate_domain(domain)
            installed.extend(s.name for s in domain_skills)

        self._evo.record(action=node.question, method=thinking[:200],
                         outcome=ExperienceOutcome.PARTIAL, question_id=node.id)
        self._qtree.resolve(node.id, thinking[:300])

        # 衍生子问题
        await self._spawn_children(node.id, thinking, node.priority)

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
        except Exception:
            pass

    async def _run_scheduled(self, state: AnimaState) -> None:
        if self._tick_count % REFLECT_EVERY == 0:
            await self._daily_reflect(state)
        if self._tick_count % DECAY_EVERY == 0:
            decayed = self._memory.run_decay()
            logger.info(f"[MindLoop] 记忆衰减: {decayed} 条")
            self._trust.adjust("week_no_issues")

    async def _daily_reflect(self, state: AnimaState) -> None:
        logger.info("[MindLoop] 开始每日复盘")
        try:
            result = await self._evo.reflect(state, self._brain.think_json)
            adj = result.get("personality_adjustments", {})
            if adj.get("proactivity_delta") or adj.get("risk_tolerance_delta"):
                self._identity.update_personality(
                    state.identity,
                    proactivity_delta=float(adj.get("proactivity_delta", 0)),
                    risk_tolerance_delta=float(adj.get("risk_tolerance_delta", 0)),
                )
            for gap in result.get("skill_gaps", []):
                self._qtree.add_root(f"我在「{gap}」方面能力不足，需要学习提升",
                                     QuestionSource.SELF_REFLECTION, priority=0.55)
            await self._notify(f"📊 每日复盘完成\n{result.get('assessment', '复盘完成')}")
        except Exception as e:
            logger.error(f"[MindLoop] 复盘失败: {e}", exc_info=True)

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
