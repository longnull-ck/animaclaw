"""
Anima — Config（环境配置校验）
启动时检查必要环境变量，缺失给出明确提示。
"""

from __future__ import annotations

import os
import sys
import logging
from dataclasses import dataclass

logger = logging.getLogger("anima.config")


@dataclass
class ConfigCheck:
    key: str
    description: str
    required: bool = False
    group: str = ""


# ── 所有已知配置项 ────────────────────────────────────────────

ALL_CONFIGS = [
    # 模型 Provider（至少需要一个）
    ConfigCheck("DEEPSEEK_API_KEY", "DeepSeek API Key", group="provider"),
    ConfigCheck("OPENAI_API_KEY", "OpenAI API Key", group="provider"),
    ConfigCheck("ANTHROPIC_API_KEY", "Anthropic API Key", group="provider"),
    ConfigCheck("GOOGLE_API_KEY", "Google Gemini API Key", group="provider"),
    ConfigCheck("OLLAMA_ENABLED", "Ollama 本地模型（true/false）", group="provider"),
    ConfigCheck("CUSTOM_API_KEY", "自定义 OpenAI 兼容 API Key", group="provider"),

    # Telegram
    ConfigCheck("TELEGRAM_BOT_TOKEN", "Telegram Bot Token", group="telegram"),
    ConfigCheck("TELEGRAM_OWNER_CHAT_ID", "Telegram Owner Chat ID", group="telegram"),

    # Discord
    ConfigCheck("DISCORD_BOT_TOKEN", "Discord Bot Token", group="discord"),
    ConfigCheck("DISCORD_OWNER_USER_ID", "Discord Owner User ID", group="discord"),
    ConfigCheck("DISCORD_GUILD_ID", "Discord Guild ID（可选）", group="discord"),

    # Slack
    ConfigCheck("SLACK_BOT_TOKEN", "Slack Bot Token (xoxb-...)", group="slack"),
    ConfigCheck("SLACK_APP_TOKEN", "Slack App Token (xapp-...)", group="slack"),
    ConfigCheck("SLACK_OWNER_USER_ID", "Slack Owner User ID", group="slack"),

    # 系统
    ConfigCheck("ANIMA_DATA_DIR", "数据目录（默认 ./data）", group="system"),
]


def validate_config(*, silent: bool = False) -> dict:
    """
    校验环境配置，返回诊断结果。

    Returns:
        {
            "ok": bool,
            "providers_found": int,
            "channels_configured": list[str],
            "warnings": list[str],
            "errors": list[str],
        }
    """
    result = {
        "ok": True,
        "providers_found": 0,
        "channels_configured": [],
        "warnings": [],
        "errors": [],
    }

    # ── 检查 Provider（至少需要一个）──────────────────────────
    provider_keys = [c for c in ALL_CONFIGS if c.group == "provider"]
    provider_count = 0

    for cfg in provider_keys:
        val = os.getenv(cfg.key, "").strip()
        if cfg.key == "OLLAMA_ENABLED":
            if val.lower() in ("1", "true", "yes"):
                provider_count += 1
        elif val:
            provider_count += 1

    result["providers_found"] = provider_count

    if provider_count == 0:
        result["ok"] = False
        result["errors"].append(
            "未检测到任何模型 API Key！\n"
            "  至少配置以下之一：\n"
            "    DEEPSEEK_API_KEY=sk-...\n"
            "    OPENAI_API_KEY=sk-...\n"
            "    ANTHROPIC_API_KEY=sk-ant-...\n"
            "    GOOGLE_API_KEY=AI...\n"
            "    OLLAMA_ENABLED=true\n"
            "  参考 .env.example 文件"
        )

    # ── 检查频道配置 ──────────────────────────────────────────
    # Telegram
    if os.getenv("TELEGRAM_BOT_TOKEN"):
        if not os.getenv("TELEGRAM_OWNER_CHAT_ID"):
            result["warnings"].append(
                "TELEGRAM_BOT_TOKEN 已配置但缺少 TELEGRAM_OWNER_CHAT_ID（主动推送将不可用）"
            )
        result["channels_configured"].append("telegram")

    # Discord
    if os.getenv("DISCORD_BOT_TOKEN"):
        if not os.getenv("DISCORD_OWNER_USER_ID"):
            result["warnings"].append(
                "DISCORD_BOT_TOKEN 已配置但缺少 DISCORD_OWNER_USER_ID"
            )
        result["channels_configured"].append("discord")

    # Slack
    if os.getenv("SLACK_BOT_TOKEN"):
        if not os.getenv("SLACK_APP_TOKEN"):
            result["warnings"].append(
                "SLACK_BOT_TOKEN 已配置但缺少 SLACK_APP_TOKEN（Socket Mode 需要）"
            )
        else:
            result["channels_configured"].append("slack")

    # ── 输出诊断信息 ──────────────────────────────────────────
    if not silent:
        _print_diagnostic(result)

    return result


def _print_diagnostic(result: dict) -> None:
    """打印环境诊断信息"""
    print("\n┌─── Anima 环境检查 ───────────────────────────────┐")

    # Provider 状态
    if result["providers_found"] > 0:
        print(f"│  ✅ 模型 Provider: {result['providers_found']} 个已配置")
    else:
        print(f"│  ❌ 模型 Provider: 未配置（无法启动）")

    # 频道状态
    channels = result["channels_configured"]
    if channels:
        print(f"│  ✅ 消息频道: {', '.join(channels)}")
    else:
        print(f"│  ℹ️  消息频道: 未配置（仅命令行/Web）")

    # 警告
    for w in result["warnings"]:
        print(f"│  ⚠️  {w}")

    # 错误
    for e in result["errors"]:
        for line in e.split("\n"):
            print(f"│  ❌ {line}")

    print("└──────────────────────────────────────────────────┘\n")


def require_config_or_exit() -> dict:
    """
    校验配置，如果有致命错误则退出进程。
    在 run.py start 时调用。
    """
    result = validate_config()
    if not result["ok"]:
        print("\n💀 配置检查失败，无法启动。请修改 .env 文件后重试。\n")
        sys.exit(1)
    return result
