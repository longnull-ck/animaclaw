"""
Anima — Tools（工具执行层）
让 Anima 真正能"动手干活"，不只是"想"。

所有工具函数签名统一：
  async def tool_xxx(args: dict) -> str
  参数是 dict，返回值是执行结果的文本描述。
"""

from anima.tools.dispatcher import ToolDispatcher, get_dispatcher

__all__ = ["ToolDispatcher", "get_dispatcher"]
