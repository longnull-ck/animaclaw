"""
Anima — Discord 渠道适配器
使用 discord.py 接收消息并将响应发回。
"""

from __future__ import annotations
import logging
from datetime import datetime

from .base import BaseChannel
from ..models import Signal, SignalType

logger = logging.getLogger(__name__)


class DiscordChannel(BaseChannel):
    """
    Discord 渠道适配器。
    通过 Discord Bot 接收用户消息，调用 Anima Brain 处理后回复。
    """

    def __init__(self, token: str, brain, owner_user_id: str, guild_id: str | None = None):
        """
        Args:
            token: Discord Bot Token
            brain: Anima Brain 实例（提供 process 方法）
            owner_user_id: 主人的 Discord User ID
            guild_id: 限定响应的 Guild ID（可选，为空则响应所有 Guild）
        """
        self.token = token
        self.brain = brain
        self.owner_user_id = owner_user_id
        self.guild_id = guild_id
        self._client = None
        self._ready = False

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    async def start(self) -> None:
        try:
            import discord
        except ImportError:
            logger.error("discord.py not installed. Run: pip install discord.py")
            return

        intents = discord.Intents.default()
        intents.message_content = True
        intents.guilds = True
        intents.members = True

        self._client = discord.Client(intents=intents)

        @self._client.event
        async def on_ready():
            self._ready = True
            logger.info(f"Discord channel ready: {self._client.user} (ID: {self._client.user.id})")

        @self._client.event
        async def on_message(message: discord.Message):
            await self._on_message(message)

        # 使用 asyncio.create_task 非阻塞启动
        import asyncio
        asyncio.create_task(self._client.start(self.token))
        logger.info("Discord channel starting...")

    async def stop(self) -> None:
        if self._client and not self._client.is_closed():
            await self._client.close()
            self._ready = False
            logger.info("Discord channel stopped.")

    async def send(self, recipient_id: str, text: str) -> None:
        """
        向 Discord 频道或用户发送消息。
        recipient_id 格式:
          - "channel:<channel_id>" — 发送到频道
          - "user:<user_id>" — 发送 DM
          - 纯数字 — 尝试作为 channel_id
        """
        if not self._client or not self._ready:
            logger.warning("Discord client not ready, cannot send message.")
            return

        try:
            if recipient_id.startswith("channel:"):
                channel_id = int(recipient_id.split(":", 1)[1])
                channel = self._client.get_channel(channel_id)
                if channel:
                    # Discord 消息限制 2000 字符，自动分段
                    for chunk in self._split_message(text):
                        await channel.send(chunk)
            elif recipient_id.startswith("user:"):
                user_id = int(recipient_id.split(":", 1)[1])
                user = self._client.get_user(user_id)
                if user:
                    dm = await user.create_dm()
                    for chunk in self._split_message(text):
                        await dm.send(chunk)
            else:
                # 默认尝试作为 channel_id
                channel_id = int(recipient_id)
                channel = self._client.get_channel(channel_id)
                if channel:
                    for chunk in self._split_message(text):
                        await channel.send(chunk)
        except Exception as e:
            logger.error(f"Failed to send Discord message: {e}")

    def to_signal(self, raw_event: dict) -> Signal:
        return Signal(
            type=SignalType.MESSAGE,
            payload={
                "user_id": str(raw_event.get("user_id", "unknown")),
                "user_name": raw_event.get("user_name", ""),
                "text": raw_event.get("text", ""),
                "channel": "discord",
                "channel_id": str(raw_event.get("channel_id", "")),
                "guild_id": str(raw_event.get("guild_id", "")),
                "is_dm": raw_event.get("is_dm", False),
            },
            strength=1.0,
            timestamp=datetime.utcnow().isoformat(),
        )

    # ------------------------------------------------------------------
    # 消息回调
    # ------------------------------------------------------------------

    async def _on_message(self, message) -> None:
        """处理收到的 Discord 消息"""
        import discord

        # 忽略 Bot 自己的消息
        if message.author == self._client.user:
            return

        # 忽略其他 Bot 的消息
        if message.author.bot:
            return

        # 如果限定了 Guild，只响应该 Guild 的消息
        if self.guild_id and message.guild:
            if str(message.guild.id) != self.guild_id:
                return

        text = message.content.strip()
        if not text:
            return

        # 判断是否需要响应：
        # 1. DM（私信）→ 始终响应
        # 2. @提及 Bot → 响应
        # 3. 以 Bot 名字开头 → 响应
        should_respond = False
        if isinstance(message.channel, discord.DMChannel):
            should_respond = True
        elif self._client.user in message.mentions:
            should_respond = True
            # 移除 @mention 部分
            text = text.replace(f"<@{self._client.user.id}>", "").strip()
            text = text.replace(f"<@!{self._client.user.id}>", "").strip()

        if not should_respond:
            return

        # 构造信号
        signal = self.to_signal({
            "user_id": message.author.id,
            "user_name": str(message.author),
            "text": text,
            "channel_id": message.channel.id,
            "guild_id": message.guild.id if message.guild else None,
            "is_dm": isinstance(message.channel, discord.DMChannel),
        })

        try:
            # 发送"正在输入"状态
            async with message.channel.typing():
                response = await self.brain.process(signal)

            if response:
                for chunk in self._split_message(response):
                    await message.channel.send(chunk)
        except Exception as exc:
            logger.error("Error processing Discord message: %s", exc)
            await message.channel.send("抱歉，处理您的消息时出现了错误。")

    # ------------------------------------------------------------------
    # 工具方法
    # ------------------------------------------------------------------

    @staticmethod
    def _split_message(text: str, max_length: int = 2000) -> list[str]:
        """将长消息按 Discord 的 2000 字符限制分段"""
        if len(text) <= max_length:
            return [text]

        chunks = []
        while text:
            if len(text) <= max_length:
                chunks.append(text)
                break
            # 尝试在换行符处分割
            split_at = text.rfind("\n", 0, max_length)
            if split_at == -1 or split_at < max_length // 2:
                # 没有合适的换行符，在空格处分割
                split_at = text.rfind(" ", 0, max_length)
            if split_at == -1 or split_at < max_length // 2:
                # 强制分割
                split_at = max_length
            chunks.append(text[:split_at])
            text = text[split_at:].lstrip()
        return chunks
