"""
Anima — Events System Tests
"""

import pytest
import asyncio
from anima.events import EventBus, AnimaEvent, EventType


class TestEventBus:
    """测试事件总线"""

    @pytest.fixture
    def bus(self):
        return EventBus()

    @pytest.mark.asyncio
    async def test_emit_and_subscribe(self, bus: EventBus):
        received = []

        async def handler(event: AnimaEvent):
            received.append(event)

        bus.subscribe(handler)
        event = AnimaEvent(type=EventType.SYSTEM, title="test", detail="hello")
        await bus.emit(event)

        assert len(received) == 1
        assert received[0].title == "test"

    @pytest.mark.asyncio
    async def test_multiple_subscribers(self, bus: EventBus):
        counts = [0, 0]

        async def handler1(event):
            counts[0] += 1

        async def handler2(event):
            counts[1] += 1

        bus.subscribe(handler1)
        bus.subscribe(handler2)
        await bus.emit(AnimaEvent(type=EventType.ACTION, title="x"))

        assert counts == [1, 1]

    @pytest.mark.asyncio
    async def test_unsubscribe(self, bus: EventBus):
        received = []

        async def handler(event):
            received.append(event)

        bus.subscribe(handler)
        await bus.emit(AnimaEvent(type=EventType.SYSTEM, title="a"))
        bus.unsubscribe(handler)
        await bus.emit(AnimaEvent(type=EventType.SYSTEM, title="b"))

        assert len(received) == 1
        assert received[0].title == "a"

    @pytest.mark.asyncio
    async def test_history(self, bus: EventBus):
        for i in range(5):
            await bus.emit(AnimaEvent(type=EventType.SYSTEM, title=f"e{i}"))

        history = bus.get_history(3)
        assert len(history) == 3
        assert history[-1]["title"] == "e4"

    @pytest.mark.asyncio
    async def test_history_max_limit(self, bus: EventBus):
        for i in range(250):
            await bus.emit(AnimaEvent(type=EventType.SYSTEM, title=f"e{i}"))

        # MAX_HISTORY = 200
        history = bus.get_history(300)
        assert len(history) == 200

    @pytest.mark.asyncio
    async def test_handler_error_does_not_crash(self, bus: EventBus):
        """即使 handler 抛异常也不影响其他 handler"""
        received = []

        async def bad_handler(event):
            raise ValueError("boom")

        async def good_handler(event):
            received.append(event)

        bus.subscribe(bad_handler)
        bus.subscribe(good_handler)
        await bus.emit(AnimaEvent(type=EventType.SYSTEM, title="safe"))

        assert len(received) == 1

    def test_subscriber_count(self, bus: EventBus):
        async def h1(e): pass
        async def h2(e): pass

        bus.subscribe(h1)
        bus.subscribe(h2)
        assert bus.subscriber_count == 2
        bus.unsubscribe(h1)
        assert bus.subscriber_count == 1


class TestAnimaEvent:
    """测试事件序列化"""

    def test_to_dict(self):
        event = AnimaEvent(
            type=EventType.THINKING,
            title="正在思考",
            detail="用户问了什么",
            icon="🧠",
            data={"key": "value"},
        )
        d = event.to_dict()
        assert d["type"] == "thinking"
        assert d["title"] == "正在思考"
        assert d["icon"] == "🧠"
        assert d["data"] == {"key": "value"}

    def test_to_json(self):
        event = AnimaEvent(type=EventType.ACTION, title="执行")
        j = event.to_json()
        import json
        parsed = json.loads(j)
        assert parsed["type"] == "action"
        assert parsed["title"] == "执行"
