"""
Anima — Telegram 渠道适配器
使用 python-telegram-bot 接收消息并将响应发回。
"""

from __future__ import annotations
import logging
from datetime import datetime

from .base import BaseChannel
from ..models import Signal, SignalType

logger = logging.getLogger(__name__)


class TelegramChannel(BaseChannel):
    def __init__(self, token: str, brain, owner_chat_id: str, **kwargs):
        """
        Args:
            token: Telegram Bot Token
            brain: Anima Brain instance (provides think() method)
            owner_chat_id: Owner's Telegram Chat ID
            **kwargs: Accept extra args for compatibility (e.g. owner_id, inject_signal_fn)
        """
        self.token = token
        self.brain = brain
        self.owner_chat_id = owner_chat_id
        self._app = None
        self._message_callback = None

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    async def start(self) -> None:
        try:
            from telegram.ext import ApplicationBuilder, MessageHandler, filters
        except ImportError:
            logger.error("python-telegram-bot not installed. Run: pip install python-telegram-bot")
            return

        self._app = ApplicationBuilder().token(self.token).build()
        self._app.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self._on_message)
        )
        logger.info("Telegram channel starting...")
        await self._app.initialize()
        await self._app.start()
        await self._app.updater.start_polling()

    async def stop(self) -> None:
        if self._app:
            await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()
            logger.info("Telegram channel stopped.")

    async def send(self, recipient_id: str, text: str) -> None:
        if not self._app:
            logger.warning("Telegram app not initialized, cannot send message.")
            return
        await self._app.bot.send_message(chat_id=recipient_id, text=text)

    def to_signal(self, raw_event: dict) -> Signal:
        return Signal(
            type=SignalType.MESSAGE,
            payload={
                "user_id": str(raw_event.get("chat_id", "unknown")),
                "text": raw_event.get("text", ""),
                "channel": "telegram",
            },
            strength=1.0,
            timestamp=datetime.utcnow().isoformat(),
        )

    # ------------------------------------------------------------------
    # 消息回调
    # ------------------------------------------------------------------

    def on_message(self, callback) -> None:
        """Register a callback for incoming messages: callback(sender_id, text)"""
        self._message_callback = callback

    async def _on_message(self, update, context) -> None:
        if not update.message or not update.message.text:
            return
        chat_id = str(update.message.chat_id)
        text = update.message.text

        # If external callback registered (from run.py/cli.py), use it
        if self._message_callback:
            try:
                await self._message_callback(chat_id, text)
            except Exception as exc:
                logger.error("Error in message callback: %s", exc)
                await self.send(chat_id, "抱歉，处理您的消息时出现了错误。")
            return

        # Fallback: use brain.think() directly
        signal = self.to_signal({"chat_id": chat_id, "text": text})
        try:
            response = await self.brain.think(
                "你是一个全能型AI员工，简洁地回复用户消息。",
                text,
            )
            if response:
                await self.send(chat_id, response)
        except Exception as exc:
            logger.error("Error processing Telegram message: %s", exc)
            await self.send(chat_id, "抱歉，处理您的消息时出现了错误。")
