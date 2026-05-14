"""
Anima — Tool Dispatcher（工具统一调度器）
所有工具通过这个调度器注册和调用。
mind_loop 和 server 都通过 dispatcher.execute(tool_name, args) 执行工具。
"""

from __future__ import annotations

import logging
from typing import Callable, Awaitable

from anima.events import emit_action, emit_skill

logger = logging.getLogger("anima.tools")

# 工具函数签名：接收 dict 参数，返回 str 结果
ToolFunction = Callable[[dict], Awaitable[str]]


class ToolDispatcher:
    """统一工具调度器"""

    def __init__(self):
        self._tools: dict[str, ToolFunction] = {}
        self._register_builtins()

    def _register_builtins(self) -> None:
        """注册所有内置工具"""
        from anima.tools.web_search import tool_web_search
        from anima.tools.web_read import tool_web_read
        from anima.tools.file_ops import tool_file_read, tool_file_write
        from anima.tools.bash import tool_bash
        from anima.tools.spreadsheet import tool_spreadsheet

        self.register("tool_web_search", tool_web_search)
        self.register("tool_web_read", tool_web_read)
        self.register("tool_file_read", tool_file_read)
        self.register("tool_file_write", tool_file_write)
        self.register("tool_bash", tool_bash)
        self.register("tool_spreadsheet", tool_spreadsheet)

    def register(self, name: str, fn: ToolFunction) -> None:
        """注册一个工具"""
        self._tools[name] = fn
        logger.debug(f"[Tools] 注册工具: {name}")

    def has_tool(self, name: str) -> bool:
        return name in self._tools

    @property
    def available_tools(self) -> list[str]:
        return list(self._tools.keys())

    async def execute(self, tool_name: str, args: dict) -> str:
        """
        执行工具。
        成功返回结果文本，失败返回错误描述。
        每次执行都通过事件总线广播。
        """
        fn = self._tools.get(tool_name)
        if not fn:
            msg = f"工具 {tool_name} 未注册"
            logger.warning(f"[Tools] {msg}")
            return f"[错误] {msg}"

        await emit_action(f"执行工具: {tool_name}", str(args)[:80])

        try:
            result = await fn(args)
            await emit_skill(f"工具完成: {tool_name}", result[:80])
            logger.info(f"[Tools] {tool_name} 执行成功，结果长度: {len(result)}")
            return result
        except Exception as e:
            error_msg = f"[工具执行失败] {tool_name}: {e}"
            logger.error(error_msg)
            await emit_action(f"工具失败: {tool_name}", str(e)[:80], data={"error": True})
            return error_msg


# ─── 全局单例 ─────────────────────────────────────────────────

_dispatcher: ToolDispatcher | None = None


def get_dispatcher() -> ToolDispatcher:
    global _dispatcher
    if _dispatcher is None:
        _dispatcher = ToolDispatcher()
    return _dispatcher
