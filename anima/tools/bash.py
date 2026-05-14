"""
Anima — Bash Tool
执行系统命令（带安全限制）
"""

from __future__ import annotations

import asyncio
import logging
import os

logger = logging.getLogger("anima.tools.bash")

# 安全限制
MAX_TIMEOUT = 60  # 最大执行时间（秒）
MAX_OUTPUT = 10_000  # 最大输出长度（字符）

# 危险命令黑名单
BLOCKED_COMMANDS = [
    "rm -rf /",
    "rm -rf /*",
    "mkfs",
    "dd if=/dev",
    ":(){:|:&};:",
    "shutdown",
    "reboot",
    "halt",
    "poweroff",
]


async def tool_bash(args: dict) -> str:
    """
    执行系统命令。
    args:
      command: str  要执行的命令
      timeout: int  超时时间秒（默认30，最大60）
      cwd: str  工作目录（可选，默认 workspace）
    """
    command = args.get("command", "")
    timeout = min(int(args.get("timeout", 30)), MAX_TIMEOUT)
    cwd = args.get("cwd", os.getenv("ANIMA_WORKSPACE", "./workspace"))

    if not command:
        return "[错误] 缺少 command 参数"

    # 安全检查
    cmd_lower = command.lower().strip()
    for blocked in BLOCKED_COMMANDS:
        if blocked in cmd_lower:
            return f"[安全限制] 命令被阻止: {command}"

    # 确保工作目录存在
    os.makedirs(cwd, exist_ok=True)

    try:
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=timeout
            )
        except asyncio.TimeoutError:
            process.kill()
            return f"[超时] 命令执行超过 {timeout} 秒，已终止"

        exit_code = process.returncode
        stdout_text = stdout.decode("utf-8", errors="replace")
        stderr_text = stderr.decode("utf-8", errors="replace")

        # 截断过长输出
        if len(stdout_text) > MAX_OUTPUT:
            stdout_text = stdout_text[:MAX_OUTPUT] + f"\n[已截断，原始输出 {len(stdout.decode())} 字符]"
        if len(stderr_text) > MAX_OUTPUT:
            stderr_text = stderr_text[:MAX_OUTPUT] + "\n[已截断]"

        result = f"$ {command}\n"
        result += f"退出码: {exit_code}\n"

        if stdout_text.strip():
            result += f"\n--- stdout ---\n{stdout_text.strip()}\n"
        if stderr_text.strip():
            result += f"\n--- stderr ---\n{stderr_text.strip()}\n"

        if not stdout_text.strip() and not stderr_text.strip():
            result += "\n（无输出）"

        return result

    except Exception as e:
        logger.error(f"[bash] 执行失败: {e}")
        return f"[执行失败] {e}"
