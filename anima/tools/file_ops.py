"""
Anima — File Operations Tool
读写本地文件
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger("anima.tools.file_ops")

# 安全限制：只允许在工作目录下操作
WORKSPACE_ROOT = Path(os.getenv("ANIMA_WORKSPACE", "./workspace")).resolve()

MAX_READ_SIZE = 100_000  # 100KB


async def tool_file_read(args: dict) -> str:
    """
    读取本地文件内容。
    args:
      path: str  文件路径（相对于工作目录）
      encoding: str  编码（默认 utf-8）
    """
    rel_path = args.get("path", "")
    encoding = args.get("encoding", "utf-8")

    if not rel_path:
        return "[错误] 缺少 path 参数"

    filepath = _resolve_safe_path(rel_path)
    if filepath is None:
        return f"[安全限制] 路径 {rel_path} 不在允许的工作目录内"

    if not filepath.exists():
        return f"[文件不存在] {rel_path}"

    if not filepath.is_file():
        return f"[不是文件] {rel_path}"

    file_size = filepath.stat().st_size
    if file_size > MAX_READ_SIZE:
        return f"[文件过大] {rel_path} ({file_size} bytes > {MAX_READ_SIZE} bytes 限制)"

    try:
        content = filepath.read_text(encoding=encoding)
        return f"文件内容（{rel_path}，{len(content)} 字符）：\n\n{content}"
    except UnicodeDecodeError:
        return f"[编码错误] 无法以 {encoding} 读取 {rel_path}"
    except Exception as e:
        return f"[读取失败] {e}"


async def tool_file_write(args: dict) -> str:
    """
    写入本地文件。
    args:
      path: str  文件路径（相对于工作目录）
      content: str  文件内容
      mode: str  写入模式 "write"（覆盖）或 "append"（追加），默认 write
    """
    rel_path = args.get("path", "")
    content = args.get("content", "")
    mode = args.get("mode", "write")

    if not rel_path:
        return "[错误] 缺少 path 参数"

    if not content:
        return "[错误] 缺少 content 参数"

    filepath = _resolve_safe_path(rel_path)
    if filepath is None:
        return f"[安全限制] 路径 {rel_path} 不在允许的工作目录内"

    try:
        # 确保父目录存在
        filepath.parent.mkdir(parents=True, exist_ok=True)

        if mode == "append":
            with open(filepath, "a", encoding="utf-8") as f:
                f.write(content)
            action = "追加"
        else:
            filepath.write_text(content, encoding="utf-8")
            action = "写入"

        return f"[成功] 已{action}文件 {rel_path}（{len(content)} 字符）"

    except Exception as e:
        return f"[写入失败] {e}"


def _resolve_safe_path(rel_path: str) -> Path | None:
    """解析路径并确保在工作目录内（防止路径遍历攻击）"""
    WORKSPACE_ROOT.mkdir(parents=True, exist_ok=True)

    try:
        resolved = (WORKSPACE_ROOT / rel_path).resolve()
        # 检查解析后的路径是否仍在工作目录内
        if str(resolved).startswith(str(WORKSPACE_ROOT)):
            return resolved
        return None
    except (ValueError, OSError):
        return None
