"""
Anima — Provider Registry Tests
"""

import os
import pytest
from unittest.mock import patch
from anima.providers.registry import ProviderRegistry, ProviderConfig


class TestProviderRegistry:
    """测试 Provider 注册表"""

    def test_no_providers_detected(self):
        """无 API Key 时应检测不到 Provider"""
        with patch.dict(os.environ, {}, clear=True):
            # 清除所有相关 env vars
            env_clear = {
                "DEEPSEEK_API_KEY": "",
                "OPENAI_API_KEY": "",
                "ANTHROPIC_API_KEY": "",
                "GOOGLE_API_KEY": "",
                "OLLAMA_ENABLED": "",
                "CUSTOM_API_KEY": "",
            }
            with patch.dict(os.environ, env_clear):
                registry = ProviderRegistry()
                assert len(registry.all_providers) == 0
                assert registry.active is None

    def test_detect_deepseek(self):
        with patch.dict(os.environ, {
            "DEEPSEEK_API_KEY": "sk-test",
            "OPENAI_API_KEY": "",
            "ANTHROPIC_API_KEY": "",
            "GOOGLE_API_KEY": "",
            "OLLAMA_ENABLED": "",
            "CUSTOM_API_KEY": "",
        }):
            registry = ProviderRegistry()
            assert len(registry.enabled_providers) == 1
            assert registry.active.name == "deepseek"
            assert registry.active.model == "deepseek-chat"

    def test_detect_multiple(self):
        with patch.dict(os.environ, {
            "DEEPSEEK_API_KEY": "sk-ds",
            "OPENAI_API_KEY": "sk-oai",
            "ANTHROPIC_API_KEY": "",
            "GOOGLE_API_KEY": "",
            "OLLAMA_ENABLED": "",
            "CUSTOM_API_KEY": "",
        }):
            registry = ProviderRegistry()
            assert len(registry.enabled_providers) == 2
            names = [p.name for p in registry.enabled_providers]
            assert "deepseek" in names
            assert "openai" in names

    def test_failover(self):
        with patch.dict(os.environ, {
            "DEEPSEEK_API_KEY": "sk-ds",
            "OPENAI_API_KEY": "sk-oai",
            "ANTHROPIC_API_KEY": "",
            "GOOGLE_API_KEY": "",
            "OLLAMA_ENABLED": "",
            "CUSTOM_API_KEY": "",
        }):
            registry = ProviderRegistry()
            first = registry.active
            assert first.name == "deepseek"

            switched = registry.failover()
            assert switched.name == "openai"
            assert registry.active.name == "openai"

    def test_failover_single_provider(self):
        with patch.dict(os.environ, {
            "DEEPSEEK_API_KEY": "sk-ds",
            "OPENAI_API_KEY": "",
            "ANTHROPIC_API_KEY": "",
            "GOOGLE_API_KEY": "",
            "OLLAMA_ENABLED": "",
            "CUSTOM_API_KEY": "",
        }):
            registry = ProviderRegistry()
            result = registry.failover()
            assert result is None  # 只有一个，无法切换

    def test_switch_to(self):
        with patch.dict(os.environ, {
            "DEEPSEEK_API_KEY": "sk-ds",
            "OPENAI_API_KEY": "sk-oai",
            "ANTHROPIC_API_KEY": "",
            "GOOGLE_API_KEY": "",
            "OLLAMA_ENABLED": "",
            "CUSTOM_API_KEY": "",
        }):
            registry = ProviderRegistry()
            success = registry.switch_to("openai")
            assert success is True
            assert registry.active.name == "openai"

    def test_switch_to_nonexistent(self):
        with patch.dict(os.environ, {
            "DEEPSEEK_API_KEY": "sk-ds",
            "OPENAI_API_KEY": "",
            "ANTHROPIC_API_KEY": "",
            "GOOGLE_API_KEY": "",
            "OLLAMA_ENABLED": "",
            "CUSTOM_API_KEY": "",
        }):
            registry = ProviderRegistry()
            success = registry.switch_to("nonexistent")
            assert success is False

    def test_record_usage(self):
        with patch.dict(os.environ, {
            "DEEPSEEK_API_KEY": "sk-ds",
            "OPENAI_API_KEY": "",
            "ANTHROPIC_API_KEY": "",
            "GOOGLE_API_KEY": "",
            "OLLAMA_ENABLED": "",
            "CUSTOM_API_KEY": "",
        }):
            registry = ProviderRegistry()
            registry.record_usage("deepseek", prompt_tokens=100, completion_tokens=50)
            registry.record_usage("deepseek", prompt_tokens=200, completion_tokens=100)

            usage = registry.get_usage("deepseek")
            assert usage.total_calls == 2
            assert usage.prompt_tokens == 300
            assert usage.completion_tokens == 150
            assert usage.total_tokens == 450

    def test_record_error(self):
        with patch.dict(os.environ, {
            "DEEPSEEK_API_KEY": "sk-ds",
            "OPENAI_API_KEY": "",
            "ANTHROPIC_API_KEY": "",
            "GOOGLE_API_KEY": "",
            "OLLAMA_ENABLED": "",
            "CUSTOM_API_KEY": "",
        }):
            registry = ProviderRegistry()
            registry.record_usage("deepseek", is_error=True)
            usage = registry.get_usage("deepseek")
            assert usage.errors == 1

    def test_summary(self):
        with patch.dict(os.environ, {
            "DEEPSEEK_API_KEY": "sk-ds",
            "OPENAI_API_KEY": "",
            "ANTHROPIC_API_KEY": "",
            "GOOGLE_API_KEY": "",
            "OLLAMA_ENABLED": "",
            "CUSTOM_API_KEY": "",
        }):
            registry = ProviderRegistry()
            s = registry.summary()
            assert s["total_providers"] == 1
            assert s["enabled"] == 1
            assert s["active"] == "deepseek"
            assert s["active_model"] == "deepseek-chat"
            assert len(s["providers"]) == 1

    def test_manual_register(self):
        with patch.dict(os.environ, {
            "DEEPSEEK_API_KEY": "",
            "OPENAI_API_KEY": "",
            "ANTHROPIC_API_KEY": "",
            "GOOGLE_API_KEY": "",
            "OLLAMA_ENABLED": "",
            "CUSTOM_API_KEY": "",
        }):
            registry = ProviderRegistry()
            assert len(registry.all_providers) == 0

            registry.register(ProviderConfig(
                name="test", base_url="http://localhost", api_key="k", model="m"
            ))
            assert len(registry.all_providers) == 1
            assert registry.active.name == "test"
