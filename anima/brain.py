"""
Anima — Brain（大脑）
模型调用层，支持 DeepSeek 及任意 OpenAI 兼容接口

职责：
  1. 统一的 think() 接口，上层模块只调这一个函数
  2. 支持多 Provider 配置，自动 failover
  3. 流式 / 非流式 / JSON 结构化三种模式
  4. Token 用量追踪
"""

from __future__ import annotations

import os
import json
import logging
from dataclasses import dataclass, field

import httpx

logger = logging.getLogger("anima.brain")


@dataclass
class ProviderConfig:
    name: str
    base_url: str
    api_key: str
    model: str
    max_tokens: int = 4096
    temperature: float = 0.7
    timeout: float = 120.0


def _default_providers() -> list[ProviderConfig]:
    providers: list[ProviderConfig] = []

    if key := os.getenv("DEEPSEEK_API_KEY"):
        providers.append(ProviderConfig(
            name="deepseek",
            base_url="https://api.deepseek.com/v1",
            api_key=key,
            model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
            max_tokens=int(os.getenv("DEEPSEEK_MAX_TOKENS", "4096")),
            temperature=float(os.getenv("DEEPSEEK_TEMPERATURE", "0.7")),
        ))

    if key := os.getenv("OPENAI_API_KEY"):
        providers.append(ProviderConfig(
            name="openai",
            base_url="https://api.openai.com/v1",
            api_key=key,
            model=os.getenv("OPENAI_MODEL", "gpt-4o"),
        ))

    if key := os.getenv("CUSTOM_API_KEY"):
        providers.append(ProviderConfig(
            name="custom",
            base_url=os.getenv("CUSTOM_BASE_URL", ""),
            api_key=key,
            model=os.getenv("CUSTOM_MODEL", ""),
        ))

    if not providers:
        raise RuntimeError(
            "没有找到任何模型 API Key。\n"
            "请在 .env 中设置 DEEPSEEK_API_KEY 或 OPENAI_API_KEY。"
        )
    return providers


@dataclass
class UsageStats:
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_calls: int = 0
    total_errors: int = 0
    provider_calls: dict[str, int] = field(default_factory=dict)

    @property
    def total_tokens(self) -> int:
        return self.total_prompt_tokens + self.total_completion_tokens


class Brain:
    """统一大脑接口。所有需要调用大模型的地方都通过 Brain.think() 进入。"""

    def __init__(self, providers: list[ProviderConfig] | None = None):
        self._providers = providers or _default_providers()
        self.usage = UsageStats()

    async def think(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """调用大模型，返回完整文本回复。自动在 Provider 列表中 failover。"""
        last_error: Exception | None = None

        for provider in self._providers:
            try:
                result = await self._call(
                    provider,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    temperature=temperature or provider.temperature,
                    max_tokens=max_tokens or provider.max_tokens,
                )
                self.usage.total_calls += 1
                self.usage.provider_calls[provider.name] = (
                    self.usage.provider_calls.get(provider.name, 0) + 1
                )
                return result
            except Exception as e:
                logger.warning(f"[Brain] provider={provider.name} 失败: {e}，尝试下一个")
                last_error = e
                self.usage.total_errors += 1

        raise RuntimeError(f"所有 Provider 均失败，最后错误: {last_error}")

    async def think_json(
        self,
        system_prompt: str,
        user_prompt: str,
        retry: int = 2,
    ) -> dict:
        """要求模型返回 JSON，自动解析并重试。"""
        json_system = system_prompt + "\n\n必须以纯 JSON 格式回复，不要包含任何 markdown 代码块。"

        import asyncio
        for attempt in range(retry + 1):
            raw = await self.think(json_system, user_prompt, temperature=0.3)
            try:
                start = raw.find("{")
                end = raw.rfind("}") + 1
                if start != -1 and end > start:
                    return json.loads(raw[start:end])
            except json.JSONDecodeError:
                pass
            if attempt < retry:
                await asyncio.sleep(1)

        logger.error(f"[Brain] JSON 解析彻底失败，原始: {raw[:200]}")
        return {}

    async def _call(
        self,
        provider: ProviderConfig,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        max_tokens: int,
    ) -> str:
        headers = {
            "Authorization": f"Bearer {provider.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": provider.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        async with httpx.AsyncClient(timeout=provider.timeout) as client:
            resp = await client.post(
                f"{provider.base_url}/chat/completions",
                headers=headers,
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()

        if usage := data.get("usage"):
            self.usage.total_prompt_tokens     += usage.get("prompt_tokens", 0)
            self.usage.total_completion_tokens += usage.get("completion_tokens", 0)

        return data["choices"][0]["message"]["content"].strip()

    def stats_summary(self) -> str:
        return (
            f"调用: {self.usage.total_calls} | "
            f"Token: {self.usage.total_tokens:,} | "
            f"错误: {self.usage.total_errors}"
        )
