"""
Anima — Bash Tool
执行系统命令（带安全限制）
"""

from __future__ import annotations

import asyncio
import logging
import os
import platform
import re

logger = logging.getLogger("anima.tools.bash")

# 安全限制
MAX_TIMEOUT = 60  # 最大执行时间（秒）
MAX_OUTPUT = 10_000  # 最大输出长度（字符）

# 危险命令模式（正则，跨平台）
BLOCKED_PATTERNS = [
    r"\brm\s+(-[a-zA-Z]*f[a-zA-Z]*\s+)?/",       # rm -rf /
    r"\bmkfs\b",                                     # format filesystem
    r"\bdd\s+if=/dev/",                              # raw disk write
    r":\(\)\{.*\}",                                  # fork bomb
    r"\b(shutdown|reboot|halt|poweroff)\b",          # system control
    r"\b(format|diskpart)\b",                        # Windows format
    r"\bcurl\b.*\|\s*(bash|sh|python|perl)",         # pipe to shell
    r"\bwget\b.*\|\s*(bash|sh|python|perl)",         # pipe to shell
    r"\b(nc|ncat|netcat)\b.*-[a-z]*[le]",           # reverse shell
    r"\bchmod\s+[0-7]*777\s+/",                     # chmod 777 /
    r"\bchown\s+.*\s+/",                            # chown system dirs
    r">\s*/dev/sd[a-z]",                            # overwrite disk
    r"\bsudo\s+rm\b",                               # sudo rm
    r"\|(bash|sh|zsh|powershell|cmd)\b",            # pipe to shell
]

# 禁止访问的路径前缀
BLOCKED_PATHS = [
    "/etc/shadow", "/etc/passwd", "/etc/sudoers",
    "/root", "/proc/kcore", "/dev/sd", "/dev/nvme",
    "C:\\Windows\\System32\\config",
]


def _is_blocked(command: str) -> str | None:
    """Check if command matches any blocked pattern. Returns reason or None."""
    cmd_lower = command.lower().strip()

    for pattern in BLOCKED_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            return f"Blocked pattern: {pattern}"

    for path in BLOCKED_PATHS:
        if path.lower() in cmd_lower:
            return f"Blocked path: {path}"

    return None


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
    blocked_reason = _is_blocked(command)
    if blocked_reason:
        logger.warning(f"[bash] Command blocked: {command} ({blocked_reason})")
        return f"[安全限制] 命令被阻止: {blocked_reason}"

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
