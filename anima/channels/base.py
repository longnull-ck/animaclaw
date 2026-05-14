"""
Anima — 渠道基类
定义所有通信渠道的统一接口。
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from ..models import Signal


class BaseChannel(ABC):
    """所有渠道适配器的基类。"""

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
