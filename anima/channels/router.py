"""
Anima — Message Router（消息路由器）
所有频道收到消息后统一走这里处理。

职责：
  1. 构建上下文（identity + memory）
  2. 调用 Brain 生成回复
  3. 记录经历到 Evolution
  4. 广播事件到 EventBus
  5. 返回回复文本

频道适配器只负责收发消息，不关心处理逻辑。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from anima.events import emit_message, emit_thinking, emit_action
from anima.models import ExperienceOutcome

if TYPE_CHECKING:
    from anima.brain import Brain
    from anima.identity.engine import IdentityEngine
    from anima.memory.manager import MemoryManager
    from anima.evolution.engine import EvolutionEngine

logger = logging.getLogger("anima.channels.router")


class MessageRouter:
    """
    统一消息处理路由器。
    所有频道（Telegram/Discord/Slack/Web）收到消息后都调用 route()。
    """

    def __init__(
        self,
        *,
        brain: "Brain",
        identity: "IdentityEngine",
        memory: "MemoryManager",
        evolution: "EvolutionEngine",
    ):
        self._brain = brain
        self._identity = identity
        self._memory = memory
        self._evo = evolution
        self._history: dict[str, list[dict]] = {}  # per-channel history

    async def route(
        self,
        text: str,
        channel: str = "unknown",
        sender_id: str = "unknown",
    ) -> str:
        """
        处理一条消息，返回回复文本。

        Args:
            text: 用户消息内容
            channel: 来源频道名 (telegram/discord/slack/webchat)
            sender_id: 发送者 ID

        Returns:
            回复文本
        """
        await emit_message(
            f"收到消息 [{channel}]",
            text[:60],
            data={"channel": channel, "sender_id": sender_id},
        )

        # 获取/初始化该频道的对话历史
        history_key = f"{channel}:{sender_id}"
        if history_key not in self._history:
            self._history[history_key] = []
        history = self._history[history_key]

        try:
            # 构建上下文
            identity = self._identity.load()
            history.append({"role": "user", "content": text})

            ctx = self._memory.build_context(
                identity_prompt=self._identity.build_identity_prompt(identity),
                recent_messages=history[-10:],
                query_hint=text,
            )
            system_prompt = self._memory.format_context_as_system_prompt(ctx)

            await emit_thinking("正在思考回复...", text[:40])

            # 调用大脑
            reply = await self._brain.think(system_prompt, text)

            await emit_action(
                f"回复 [{channel}]",
                reply[:80],
                data={"channel": channel},
            )

            # 更新对话历史（保留最近20轮）
            history.append({"role": "assistant", "content": reply})
            if len(history) > 40:
                self._history[history_key] = history[-40:]

            # 记录经历
            self._evo.record(
                action=text,
                method=f"{channel}对话",
                outcome=ExperienceOutcome.SUCCESS,
            )

            return reply

        except Exception as e:
            logger.error(f"[Router] 处理失败 [{channel}]: {e}")
            # 移除失败的 user message from history
            if history and history[-1].get("role") == "user":
                history.pop()
            return f"抱歉，处理您的消息时出现了错误：{e}"

    def clear_history(self, channel: str = "", sender_id: str = "") -> None:
        """清除对话历史"""
        if channel and sender_id:
            key = f"{channel}:{sender_id}"
            self._history.pop(key, None)
        elif channel:
            keys_to_remove = [k for k in self._history if k.startswith(f"{channel}:")]
            for k in keys_to_remove:
                del self._history[k]
        else:
            self._history.clear()
