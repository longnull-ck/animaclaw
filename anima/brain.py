"""
Anima — Brain（大脑）
统一模型调用层。从 ProviderRegistry 获取配置，自动 failover。

职责：
  1. 统一的 think() 接口，上层模块只调这一个函数
  2. 从 ProviderRegistry 获取 Provider 配置（不自己检测环境变量）
  3. 自动 failover + Anthropic 特殊协议适配
  4. JSON 结构化输出 + 重试
  5. Token 用量同步回 ProviderRegistry
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import AsyncIterator

import httpx

from anima.providers.registry import ProviderRegistry, ProviderConfig, get_provider_registry

logger = logging.getLogger("anima.brain")


class Brain:
    """
    统一大脑接口。
    所有需要调用大模型的地方都通过 Brain.think() 进入。
    Provider 配置完全由 ProviderRegistry 管理。
    """

    def __init__(self, registry: ProviderRegistry | None = None):
        self._registry = registry or get_provider_registry()

    # ── 核心接口：非流式思考 ──────────────────────────────────

    async def think(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """
        调用大模型，返回完整文本回复。
        自动在所有启用的 Provider 中 failover。
        """
        providers = self._registry.enabled_providers
        if not providers:
            raise RuntimeError(
                "没有可用的模型 Provider。\n"
                "请在 .env 中配置 DEEPSEEK_API_KEY 或 OPENAI_API_KEY 等。\n"
                "运行 anima doctor 检查配置。"
            )

        last_error: Exception | None = None

        for provider in providers:
            try:
                result = await self._call_provider(
                    provider,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    temperature=temperature or provider.temperature,
                    max_tokens=max_tokens or provider.max_tokens,
                )
                self._registry.record_usage(provider.name)
                return result

            except Exception as e:
                logger.warning(f"[Brain] provider={provider.name} 失败: {e}")
                self._registry.record_usage(provider.name, is_error=True)
                last_error = e
                # 尝试 failover 到下一个
                self._registry.failover()

        raise RuntimeError(f"所有 Provider 均失败，最后错误: {last_error}")

    # ── JSON 结构化输出 ──────────────────────────────────────

    async def think_json(
        self,
        system_prompt: str,
        user_prompt: str,
        retry: int = 2,
    ) -> dict:
        """
        要求模型返回 JSON，自动解析并重试。
        """
        json_system = system_prompt + "\n\n必须以纯 JSON 格式回复，不要包含任何 markdown 代码块或额外说明。"

        raw = ""
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
                logger.warning(f"[Brain] JSON 解析失败（第 {attempt+1} 次），重试...")
                await asyncio.sleep(1)

        logger.error(f"[Brain] JSON 解析彻底失败，原始: {raw[:200]}")
        return {}

    # ── 流式输出（用于 WebChat 实时返回） ────────────────────

    async def think_stream(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float | None = None,
    ) -> AsyncIterator[str]:
        """流式返回，逐 token 输出。用于 WebChat 实时显示。"""
        provider = self._registry.active
        if not provider:
            yield "[错误: 没有可用的模型 Provider]"
            return

        headers = self._build_headers(provider)
        payload = self._build_payload(
            provider, system_prompt, user_prompt,
            temperature or provider.temperature, provider.max_tokens,
            stream=True,
        )

        try:
            async with httpx.AsyncClient(timeout=provider.timeout) as client:
                async with client.stream(
                    "POST",
                    self._get_endpoint(provider),
                    headers=headers,
                    json=payload,
                ) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        data_str = line[6:].strip()
                        if data_str == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data_str)
                            delta = chunk["choices"][0]["delta"].get("content", "")
                            if delta:
                                yield delta
                        except (json.JSONDecodeError, KeyError, IndexError):
                            continue
        except Exception as e:
            yield f"\n[流式输出错误: {e}]"

    # ── 内部：调用单个 Provider ───────────────────────────────

    async def _call_provider(
        self,
        provider: ProviderConfig,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        max_tokens: int,
    ) -> str:
        # Anthropic 使用不同的 API 格式
        if provider.name == "anthropic":
            return await self._call_anthropic(provider, system_prompt, user_prompt, temperature, max_tokens)

        # Google Gemini 使用不同的 API 格式
        if provider.name == "google":
            return await self._call_google(provider, system_prompt, user_prompt, temperature, max_tokens)

        # OpenAI 兼容接口（DeepSeek / OpenAI / Ollama / Custom）
        headers = self._build_headers(provider)
        payload = self._build_payload(provider, system_prompt, user_prompt, temperature, max_tokens)

        async with httpx.AsyncClient(timeout=provider.timeout) as client:
            resp = await client.post(
                self._get_endpoint(provider),
                headers=headers,
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()

        # 记录 token 用量
        if usage := data.get("usage"):
            self._registry.record_usage(
                provider.name,
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0),
            )

        return data["choices"][0]["message"]["content"].strip()

    # ── Anthropic 适配（不同 API 格式） ──────────────────────

    async def _call_anthropic(
        self, provider: ProviderConfig,
        system_prompt: str, user_prompt: str,
        temperature: float, max_tokens: int,
    ) -> str:
        headers = {
            "x-api-key": provider.api_key,
            "anthropic-version": provider.api_version or "2023-06-01",
            "content-type": "application/json",
        }
        payload = {
            "model": provider.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
        }

        async with httpx.AsyncClient(timeout=provider.timeout) as client:
            resp = await client.post(
                f"{provider.base_url}/messages",
                headers=headers,
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()

        if usage := data.get("usage"):
            self._registry.record_usage(
                provider.name,
                prompt_tokens=usage.get("input_tokens", 0),
                completion_tokens=usage.get("output_tokens", 0),
            )

        # Anthropic 响应格式
        content_blocks = data.get("content", [])
        return "".join(b.get("text", "") for b in content_blocks).strip()

    # ── Google Gemini 适配 ────────────────────────────────────

    async def _call_google(
        self, provider: ProviderConfig,
        system_prompt: str, user_prompt: str,
        temperature: float, max_tokens: int,
    ) -> str:
        url = (
            f"{provider.base_url}/models/{provider.model}:generateContent"
            f"?key={provider.api_key}"
        )
        payload = {
            "contents": [{"parts": [{"text": f"{system_prompt}\n\n{user_prompt}"}]}],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            },
        }

        async with httpx.AsyncClient(timeout=provider.timeout) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()

        self._registry.record_usage(provider.name)

        candidates = data.get("candidates", [])
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            return "".join(p.get("text", "") for p in parts).strip()
        return ""

    # ── 工具方法 ─────────────────────────────────────────────

    def _build_headers(self, provider: ProviderConfig) -> dict:
        return {
            "Authorization": f"Bearer {provider.api_key}",
            "Content-Type": "application/json",
        }

    def _build_payload(
        self, provider: ProviderConfig,
        system_prompt: str, user_prompt: str,
        temperature: float, max_tokens: int,
        stream: bool = False,
    ) -> dict:
        payload: dict = {
            "model": provider.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if stream:
            payload["stream"] = True
        return payload

    def _get_endpoint(self, provider: ProviderConfig) -> str:
        return f"{provider.base_url}/chat/completions"

    # ── 状态 ─────────────────────────────────────────────────

    @property
    def active_provider_name(self) -> str:
        p = self._registry.active
        return p.name if p else "none"

    @property
    def active_model(self) -> str:
        p = self._registry.active
        return p.model if p else "none"

    def stats_summary(self) -> str:
        usage = self._registry.get_all_usage()
        total_calls = sum(u["total_calls"] for u in usage.values())
        total_tokens = sum(u["total_tokens"] for u in usage.values())
        total_errors = sum(u["errors"] for u in usage.values())
        return (
            f"调用: {total_calls} | "
            f"Token: {total_tokens:,} | "
            f"错误: {total_errors} | "
            f"Provider: {self.active_provider_name}"
        )
