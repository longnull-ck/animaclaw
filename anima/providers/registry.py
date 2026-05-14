"""
Anima — Provider Registry（模型提供商注册表）
参考 OpenClaw 的多 Provider 支持，用 Anima 自己的方式重写。

支持：
  - DeepSeek（默认首选）
  - OpenAI（GPT-4o / GPT-4o-mini）
  - Anthropic（Claude 4 / Sonnet）
  - Google（Gemini 2.5）
  - Ollama（本地模型）
  - 任意 OpenAI 兼容接口（自定义）

特点：
  - 自动 failover：主力失败自动切到备用
  - 热切换：运行时可切换 Provider 无需重启
  - Token 用量追踪：每个 Provider 独立统计
"""

from __future__ import annotations

import os
import logging
from dataclasses import dataclass, field

logger = logging.getLogger("anima.providers")


@dataclass
class ProviderConfig:
    name: str
    base_url: str
    api_key: str
    model: str
    max_tokens: int = 4096
    temperature: float = 0.7
    timeout: float = 120.0
    # Anthropic 特殊字段
    api_version: str = ""
    # 是否启用
    enabled: bool = True


@dataclass
class ProviderUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_calls: int = 0
    errors: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


class ProviderRegistry:
    """
    管理所有可用的模型提供商。
    从环境变量自动检测并注册。
    """

    def __init__(self):
        self._providers: list[ProviderConfig] = []
        self._usage: dict[str, ProviderUsage] = {}
        self._active_index: int = 0
        self._auto_detect()

    def _auto_detect(self) -> None:
        """从环境变量自动检测可用的 Provider"""

        # ── DeepSeek ──────────────────────────────────────────
        if key := os.getenv("DEEPSEEK_API_KEY"):
            self._providers.append(ProviderConfig(
                name="deepseek",
                base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"),
                api_key=key,
                model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
                max_tokens=int(os.getenv("DEEPSEEK_MAX_TOKENS", "4096")),
                temperature=float(os.getenv("DEEPSEEK_TEMPERATURE", "0.7")),
            ))

        # ── OpenAI ────────────────────────────────────────────
        if key := os.getenv("OPENAI_API_KEY"):
            self._providers.append(ProviderConfig(
                name="openai",
                base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
                api_key=key,
                model=os.getenv("OPENAI_MODEL", "gpt-4o"),
                max_tokens=int(os.getenv("OPENAI_MAX_TOKENS", "4096")),
            ))

        # ── Anthropic ─────────────────────────────────────────
        if key := os.getenv("ANTHROPIC_API_KEY"):
            self._providers.append(ProviderConfig(
                name="anthropic",
                base_url="https://api.anthropic.com/v1",
                api_key=key,
                model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514"),
                max_tokens=int(os.getenv("ANTHROPIC_MAX_TOKENS", "4096")),
                api_version="2023-06-01",
            ))

        # ── Google Gemini ─────────────────────────────────────
        if key := os.getenv("GOOGLE_API_KEY"):
            self._providers.append(ProviderConfig(
                name="google",
                base_url="https://generativelanguage.googleapis.com/v1beta",
                api_key=key,
                model=os.getenv("GOOGLE_MODEL", "gemini-2.5-flash"),
            ))

        # ── Ollama（本地） ────────────────────────────────────
        if os.getenv("OLLAMA_ENABLED", "").lower() in ("1", "true", "yes"):
            self._providers.append(ProviderConfig(
                name="ollama",
                base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
                api_key="ollama",  # Ollama 不需要真实 key
                model=os.getenv("OLLAMA_MODEL", "llama3.1"),
                timeout=300.0,  # 本地模型可能较慢
            ))

        # ── 自定义 OpenAI 兼容 ────────────────────────────────
        if key := os.getenv("CUSTOM_API_KEY"):
            base_url = os.getenv("CUSTOM_BASE_URL", "")
            model = os.getenv("CUSTOM_MODEL", "")
            if base_url and model:
                self._providers.append(ProviderConfig(
                    name="custom",
                    base_url=base_url,
                    api_key=key,
                    model=model,
                ))

        # 初始化用量统计
        for p in self._providers:
            self._usage[p.name] = ProviderUsage()

        if self._providers:
            logger.info(f"[Providers] 检测到 {len(self._providers)} 个: "
                        f"{', '.join(p.name for p in self._providers)}")
        else:
            logger.warning("[Providers] 未检测到任何模型 API Key！")

    # ── 获取当前活跃 Provider ─────────────────────────────────

    @property
    def active(self) -> ProviderConfig | None:
        enabled = [p for p in self._providers if p.enabled]
        if not enabled:
            return None
        idx = self._active_index % len(enabled)
        return enabled[idx]

    @property
    def all_providers(self) -> list[ProviderConfig]:
        return self._providers

    @property
    def enabled_providers(self) -> list[ProviderConfig]:
        return [p for p in self._providers if p.enabled]

    # ── Failover：切换到下一个 Provider ──────────────────────

    def failover(self) -> ProviderConfig | None:
        enabled = self.enabled_providers
        if len(enabled) <= 1:
            return None
        self._active_index = (self._active_index + 1) % len(enabled)
        new_provider = enabled[self._active_index]
        logger.warning(f"[Providers] failover → {new_provider.name}")
        return new_provider

    # ── 手动切换 Provider ─────────────────────────────────────

    def switch_to(self, name: str) -> bool:
        for i, p in enumerate(self.enabled_providers):
            if p.name == name:
                self._active_index = i
                logger.info(f"[Providers] 手动切换到: {name}")
                return True
        return False

    # ── 用量追踪 ─────────────────────────────────────────────

    def record_usage(self, provider_name: str, prompt_tokens: int = 0,
                     completion_tokens: int = 0, is_error: bool = False) -> None:
        usage = self._usage.get(provider_name)
        if not usage:
            return
        usage.total_calls += 1
        usage.prompt_tokens += prompt_tokens
        usage.completion_tokens += completion_tokens
        if is_error:
            usage.errors += 1

    def get_usage(self, provider_name: str) -> ProviderUsage | None:
        return self._usage.get(provider_name)

    def get_all_usage(self) -> dict[str, dict]:
        return {
            name: {
                "total_calls": u.total_calls,
                "total_tokens": u.total_tokens,
                "errors": u.errors,
            }
            for name, u in self._usage.items()
        }

    # ── 手动注册 Provider ─────────────────────────────────────

    def register(self, config: ProviderConfig) -> None:
        self._providers.append(config)
        self._usage[config.name] = ProviderUsage()
        logger.info(f"[Providers] 手动注册: {config.name}")

    # ── 状态摘要 ─────────────────────────────────────────────

    def summary(self) -> dict:
        active = self.active
        return {
            "total_providers": len(self._providers),
            "enabled": len(self.enabled_providers),
            "active": active.name if active else None,
            "active_model": active.model if active else None,
            "providers": [
                {
                    "name": p.name,
                    "model": p.model,
                    "enabled": p.enabled,
                    "usage": self._usage[p.name].total_calls,
                }
                for p in self._providers
            ],
        }


# ─── 全局单例 ─────────────────────────────────────────────────

_registry: ProviderRegistry | None = None


def get_provider_registry() -> ProviderRegistry:
    global _registry
    if _registry is None:
        _registry = ProviderRegistry()
    return _registry
