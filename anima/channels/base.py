"""
Anima — 渠道基类
定义所有通信渠道的统一接口。
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from ..models import Signal

if TYPE_CHECKING:
    from anima.channels.router import MessageRouter


class BaseChannel(ABC):
    """所有渠道适配器的基类。"""

    _router: "MessageRouter | None" = None

    def set_router(self, router: "MessageRouter") -> None:
        """注入消息路由器，让频道通过统一路径处理消息。"""
        self._router = router

    @abstractmethod
    async def start(self) -> None:
        """启动渠道监听。"""
        ...

    @abstractmethod
    async def stop(self) -> None:
        """停止渠道。"""
        ...

    @abstractmethod
    async def send(self, recipient_id: str, text: str) -> None:
        """向指定接收者发送消息。"""
        ...

    @abstractmethod
    def to_signal(self, raw_event: dict) -> Signal:
        """将渠道原始事件转为标准 Signal。"""
        ...
