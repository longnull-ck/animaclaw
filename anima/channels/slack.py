"""
Anima — Slack 渠道适配器
使用 slack-bolt (async) 接收消息并将响应发回。
支持 Socket Mode（无需公网地址）和 Event Subscription 两种模式。
"""

from __future__ import annotations
import logging
from datetime import datetime

from .base import BaseChannel
from ..models import Signal, SignalType

logger = logging.getLogger(__name__)


class SlackChannel(BaseChannel):
    """
    Slack 渠道适配器。
    通过 Slack Bot 接收用户消息（@提及或 DM），调用 Anima Brain 处理后回复。
    默认使用 Socket Mode（只需 App Token + Bot Token，无需暴露公网 URL）。
    """

    def __init__(
        self,
        bot_token: str,
        app_token: str,
        brain,
        owner_user_id: str,
        *,
        use_socket_mode: bool = True,
    ):
        """
        Args:
            bot_token: Slack Bot User OAuth Token (xoxb-...)
            app_token: Slack App-Level Token (xapp-...) — Socket Mode 需要
            brain: Anima Brain 实例（提供 process 方法）
            owner_user_id: 主人的 Slack User ID
            use_socket_mode: 是否使用 Socket Mode（默认 True）
        """
        self.bot_token = bot_token
        self.app_token = app_token
        self.brain = brain
        self.owner_user_id = owner_user_id
        self.use_socket_mode = use_socket_mode
        self._app = None
        self._handler = None
        self._bot_user_id: str | None = None

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    async def start(self) -> None:
        try:
            from slack_bolt.async_app import AsyncApp
            from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler
        except ImportError:
            logger.error(
                "slack-bolt not installed. Run: pip install slack-bolt aiohttp"
            )
            return

        self._app = AsyncApp(token=self.bot_token)

        # 获取 Bot 自身 user_id
        try:
            auth_response = await self._app.client.auth_test()
            self._bot_user_id = auth_response.get("user_id")
            logger.info(f"Slack bot user ID: {self._bot_user_id}")
        except Exception as e:
            logger.warning(f"Could not get bot user ID: {e}")

        # 注册事件监听
        @self._app.event("message")
        async def handle_message_events(event, say, client):
            await self._on_message(event, say, client)

        @self._app.event("app_mention")
        async def handle_app_mention(event, say, client):
            await self._on_mention(event, say, client)

        if self.use_socket_mode:
            self._handler = AsyncSocketModeHandler(self._app, self.app_token)
            import asyncio
            asyncio.create_task(self._handler.start_async())
            logger.info("Slack channel starting (Socket Mode)...")
        else:
            logger.info("Slack channel starting (HTTP mode — requires external server)...")

    async def stop(self) -> None:
        if self._handler:
            await self._handler.close_async()
            logger.info("Slack channel stopped.")

    async def send(self, recipient_id: str, text: str) -> None:
        """
        向 Slack 频道或用户发送消息。
        recipient_id 格式:
          - "channel:<channel_id>" — 发送到频道
          - "user:<user_id>" — 通过 DM 发送
          - 纯字符串 — 当作 channel_id
        """
        if not self._app:
            logger.warning("Slack app not initialized, cannot send message.")
            return

        try:
            if recipient_id.startswith("channel:"):
                channel_id = recipient_id.split(":", 1)[1]
            elif recipient_id.startswith("user:"):
                user_id = recipient_id.split(":", 1)[1]
                # 打开 DM conversation
                resp = await self._app.client.conversations_open(users=[user_id])
                channel_id = resp["channel"]["id"]
            else:
                channel_id = recipient_id

            # Slack 消息限制 ~40000 字符（blocks 有其他限制），分块发送
            for chunk in self._split_message(text):
                await self._app.client.chat_postMessage(
                    channel=channel_id,
                    text=chunk,
                )
        except Exception as e:
            logger.error(f"Failed to send Slack message: {e}")

    def to_signal(self, raw_event: dict) -> Signal:
        return Signal(
            type=SignalType.MESSAGE,
            payload={
                "user_id": str(raw_event.get("user", "unknown")),
                "text": raw_event.get("text", ""),
                "channel": "slack",
                "channel_id": str(raw_event.get("channel", "")),
                "thread_ts": raw_event.get("thread_ts"),
                "is_dm": raw_event.get("is_dm", False),
            },
            strength=1.0,
            timestamp=datetime.utcnow().isoformat(),
        )

    # ------------------------------------------------------------------
    # 消息回调
    # ------------------------------------------------------------------

    async def _on_message(self, event: dict, say, client) -> None:
        """处理 DM 和频道中的直接消息"""
        # 忽略 Bot 自身消息
        if event.get("bot_id") or event.get("user") == self._bot_user_id:
            return

        # 忽略子类型消息（如 message_changed, message_deleted 等）
        if event.get("subtype"):
            return

        text = event.get("text", "").strip()
        if not text:
            return

        # 判断是否是 DM
        channel_type = event.get("channel_type", "")
        is_dm = channel_type == "im"

        if not is_dm:
            # 非 DM 场景：只有在 @提及时才响应（由 app_mention 处理）
            return

        # DM 消息 → 直接响应
        await self._process_and_reply(event, text, say, is_dm=True)

    async def _on_mention(self, event: dict, say, client) -> None:
        """处理 @提及 Bot 的消息"""
        text = event.get("text", "").strip()
        if not text:
            return

        # 移除 @mention 标记
        if self._bot_user_id:
            text = text.replace(f"<@{self._bot_user_id}>", "").strip()

        if not text:
            await say("有什么我可以帮您的吗？", thread_ts=event.get("ts"))
            return

        await self._process_and_reply(event, text, say, is_dm=False)

    async def _process_and_reply(self, event: dict, text: str, say, *, is_dm: bool) -> None:
        """统一处理消息并回复"""
        signal = self.to_signal({
            "user": event.get("user"),
            "text": text,
            "channel": event.get("channel"),
            "thread_ts": event.get("thread_ts") or event.get("ts"),
            "is_dm": is_dm,
        })

        try:
            response = await self.brain.process(signal)
            if response:
                # 在线程中回复（保持上下文）
                thread_ts = event.get("thread_ts") or event.get("ts") if not is_dm else None
                for chunk in self._split_message(response):
                    await say(text=chunk, thread_ts=thread_ts)
        except Exception as exc:
            logger.error("Error processing Slack message: %s", exc)
            thread_ts = event.get("thread_ts") or event.get("ts") if not is_dm else None
            await say(text="抱歉，处理您的消息时出现了错误。", thread_ts=thread_ts)

    # ------------------------------------------------------------------
    # 工具方法
    # ------------------------------------------------------------------

    @staticmethod
    def _split_message(text: str, max_length: int = 3000) -> list[str]:
        """将长消息分段（Slack 限制较宽松，但为了可读性按 3000 字符分割）"""
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
                split_at = text.rfind(" ", 0, max_length)
            if split_at == -1 or split_at < max_length // 2:
                split_at = max_length
            chunks.append(text[:split_at])
            text = text[split_at:].lstrip()
        return chunks
