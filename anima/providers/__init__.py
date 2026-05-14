"""
Anima — Providers（多模型提供商）
支持 DeepSeek / OpenAI / Anthropic / Google / Ollama / 自定义兼容接口
"""

from anima.providers.registry import ProviderRegistry, get_provider_registry

__all__ = ["ProviderRegistry", "get_provider_registry"]
