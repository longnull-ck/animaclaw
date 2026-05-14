"""
Anima — Tool Dispatcher（工具统一调度器）
所有工具通过这个调度器注册和调用。
mind_loop 和 server 都通过 dispatcher.execute(tool_name, args) 执行工具。

安全：执行前检查信任等级，PROBATION 级别禁止执行危险工具。
"""

from __future__ import annotations

import logging
from typing import Callable, Awaitable

from anima.events import emit_action, emit_skill

logger = logging.getLogger("anima.tools")

# 工具函数签名：接收 dict 参数，返回 str 结果
ToolFunction = Callable[[dict], Awaitable[str]]

# 需要更高信任等级才能执行的工具（PROBATION 级别禁止）
DANGEROUS_TOOLS = {
    "tool_bash",
    "tool_file_write",
}


class ToolDispatcher:
    """统一工具调度器"""

    def __init__(self):
        self._tools: dict[str, ToolFunction] = {}
        self._trust_system = None  # 延迟注入
        self._register_builtins()

    def set_trust_system(self, trust_system) -> None:
        """注入信任系统引用（启动时由 Runtime 调用）"""
        self._trust_system = trust_system

    def _register_builtins(self) -> None:
        """注册所有内置工具"""
        from anima.tools.web_search import tool_web_search
        from anima.tools.web_read import tool_web_read
        from anima.tools.file_ops import tool_file_read, tool_file_write
        from anima.tools.bash import tool_bash
        from anima.tools.spreadsheet import tool_spreadsheet
        from anima.tools.summarize import tool_summarize
        from anima.tools.email import tool_email
        from anima.tools.calendar import tool_calendar

        self.register("tool_web_search", tool_web_search)
        self.register("tool_web_read", tool_web_read)
        self.register("tool_file_read", tool_file_read)
        self.register("tool_file_write", tool_file_write)
        self.register("tool_bash", tool_bash)
        self.register("tool_spreadsheet", tool_spreadsheet)
        self.register("tool_summarize", tool_summarize)
        self.register("tool_email", tool_email)
        self.register("tool_calendar", tool_calendar)

    def register(self, name: str, fn: ToolFunction) -> None:
        """注册一个工具"""
        self._tools[name] = fn
        logger.debug(f"[Tools] 注册工具: {name}")

    def has_tool(self, name: str) -> bool:
        return name in self._tools

    @property
    def available_tools(self) -> list[str]:
        return list(self._tools.keys())

    def _check_trust_gate(self, tool_name: str) -> str | None:
        """
        Check if current trust level allows executing this tool.
        Returns error message if blocked, None if allowed.
        """
        if tool_name not in DANGEROUS_TOOLS:
            return None

        if not self._trust_system:
            # No trust system injected = no gate (dev/test mode)
            return None

        try:
            perms = self._trust_system.get_permissions()
            if not perms.auto_execute_routine:
                return (
                    f"[信任限制] 当前信任等级不允许自动执行 {tool_name}。"
                    f"需要至少 BASIC 信任等级。请通过 'anima feedback' 积累信任。"
                )
        except Exception:
            # If trust system fails to load, allow (don't block on infra error)
            pass

        return None

    async def execute(self, tool_name: str, args: dict) -> str:
        """
        执行工具。
        成功返回结果文本，失败返回错误描述。
        每次执行都通过事件总线广播。
        执行前检查信任等级门控。
        """
        fn = self._tools.get(tool_name)
        if not fn:
            msg = f"工具 {tool_name} 未注册"
            logger.warning(f"[Tools] {msg}")
            return f"[错误] {msg}"

        # Trust gate check
        gate_error = self._check_trust_gate(tool_name)
        if gate_error:
            logger.warning(f"[Tools] Trust gate blocked: {tool_name}")
            await emit_action(f"工具被信任门控拦截: {tool_name}", "信任等级不足", data={"blocked": True})
            return gate_error

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
