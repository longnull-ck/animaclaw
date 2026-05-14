"""
Anima — Channel Registry（频道注册表）
自动发现已配置的频道并启动。

类似 ProviderRegistry 的设计：
  - 从环境变量自动检测已配置的频道
  - 统一启动/停止接口
  - 所有频道共享同一个 MessageRouter
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

from anima.channels.base import BaseChannel
from anima.channels.router import MessageRouter

if TYPE_CHECKING:
    from anima.brain import Brain
    from anima.identity.engine import IdentityEngine
    from anima.memory.manager import MemoryManager
    from anima.evolution.engine import EvolutionEngine

logger = logging.getLogger("anima.channels.registry")


class ChannelRegistry:
    """
    频道注册表。
    自动检测环境变量中配置的频道，统一管理生命周期。
    """

    def __init__(
        self,
        *,
        brain: "Brain",
        identity: "IdentityEngine",
        memory: "MemoryManager",
        evolution: "EvolutionEngine",
    ):
        self._router = MessageRouter(
            brain=brain,
            identity=identity,
            memory=memory,
            evolution=evolution,
        )
        self._channels: dict[str, BaseChannel] = {}
        self._brain = brain

    @property
    def router(self) -> MessageRouter:
        return self._router

    @property
    def started_channels(self) -> list[str]:
        return list(self._channels.keys())

    async def auto_start(self) -> list[str]:
        """
        检测环境变量，自动启动所有已配置的频道。
        返回成功启动的频道名列表。
        """
        started = []

        # ── Telegram ──────────────────────────────────────────
        if os.getenv("TELEGRAM_BOT_TOKEN"):
            try:
                from anima.channels.telegram import TelegramChannel
                channel = TelegramChannel(
                    token=os.getenv("TELEGRAM_BOT_TOKEN"),
                    brain=self._brain,
                    owner_chat_id=os.getenv("TELEGRAM_OWNER_CHAT_ID", ""),
                )
                channel.set_router(self._router)
                await channel.start()

                # Register unified message handler
                async def tg_handler(sender_id: str, text: str) -> None:
                    reply = await self._router.route(text, channel="telegram", sender_id=sender_id)
                    await channel.send(sender_id, reply)

                channel.on_message(tg_handler)
                self._channels["telegram"] = channel
                started.append("Telegram")
                logger.info("[ChannelRegistry] Telegram started")
            except Exception as e:
                logger.error(f"[ChannelRegistry] Telegram failed to start: {e}")

        # ── Discord ───────────────────────────────────────────
        if os.getenv("DISCORD_BOT_TOKEN"):
            try:
                from anima.channels.discord import DiscordChannel
                channel = DiscordChannel(
                    token=os.getenv("DISCORD_BOT_TOKEN"),
                    brain=self._brain,
                    owner_user_id=os.getenv("DISCORD_OWNER_USER_ID", ""),
                    guild_id=os.getenv("DISCORD_GUILD_ID"),
                )
                channel.set_router(self._router)
                await channel.start()
                self._channels["discord"] = channel
                started.append("Discord")
                logger.info("[ChannelRegistry] Discord started")
            except Exception as e:
                logger.error(f"[ChannelRegistry] Discord failed to start: {e}")

        # ── Slack ─────────────────────────────────────────────
        if os.getenv("SLACK_BOT_TOKEN") and os.getenv("SLACK_APP_TOKEN"):
            try:
                from anima.channels.slack import SlackChannel
                channel = SlackChannel(
                    bot_token=os.getenv("SLACK_BOT_TOKEN"),
                    app_token=os.getenv("SLACK_APP_TOKEN"),
                    brain=self._brain,
                    owner_user_id=os.getenv("SLACK_OWNER_USER_ID", ""),
                )
                channel.set_router(self._router)
                await channel.start()
                self._channels["slack"] = channel
                started.append("Slack")
                logger.info("[ChannelRegistry] Slack started")
            except Exception as e:
                logger.error(f"[ChannelRegistry] Slack failed to start: {e}")

        return started

    async def stop_all(self) -> None:
        """停止所有频道"""
        for name, channel in self._channels.items():
            try:
                await channel.stop()
                logger.info(f"[ChannelRegistry] {name} stopped")
            except Exception as e:
                logger.error(f"[ChannelRegistry] {name} stop failed: {e}")
        self._channels.clear()

    def get_channel(self, name: str) -> BaseChannel | None:
        """获取指定频道实例"""
        return self._channels.get(name)

    async def send_to_owner(self, text: str) -> None:
        """向主人发送消息（通过第一个可用频道）"""
        for name, channel in self._channels.items():
            try:
                if name == "telegram":
                    owner_id = os.getenv("TELEGRAM_OWNER_CHAT_ID", "")
                    if owner_id:
                        await channel.send(owner_id, text)
                        return
                elif name == "discord":
                    owner_id = os.getenv("DISCORD_OWNER_USER_ID", "")
                    if owner_id:
                        await channel.send(f"user:{owner_id}", text)
                        return
                elif name == "slack":
                    owner_id = os.getenv("SLACK_OWNER_USER_ID", "")
                    if owner_id:
                        await channel.send(f"user:{owner_id}", text)
                        return
            except Exception as e:
                logger.warning(f"[ChannelRegistry] send_to_owner via {name} failed: {e}")
                continue
