"""LLM 适配器单元测试：确认生产环境（DeepSeek / OpenAI 兼容）的请求构造正确。"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.clients.llm import OpenAICompatProvider, OllamaProvider, build_llm
from app.config import Settings


def _settings(**overrides) -> Settings:
    base = {
        "supabase_url": "http://127.0.0.1:54321",
        "supabase_service_role_key": "x",
        "llm_provider": "openai",
        "llm_base_url": "https://api.deepseek.com",
        "llm_model": "deepseek-flash",
        "llm_api_key": "sk-test",
        "llm_timeout": 300.0,
        "llm_temperature": 0.3,
        "llm_think": False,
        "llm_max_tokens": 4096,
    }
    base.update(overrides)
    return Settings(**base)


def test_deepseek_uses_openai_compatible_provider() -> None:
    provider = build_llm(_settings())
    assert isinstance(provider, OpenAICompatProvider)


def test_ollama_provider_selected_for_local_dev() -> None:
    provider = build_llm(
        _settings(
            llm_provider="ollama",
            llm_base_url="http://127.0.0.1:11434",
            llm_model="qwen3.5:9b",
            llm_api_key="",
        )
    )
    assert isinstance(provider, OllamaProvider)


def test_deepseek_payload_uses_chat_completions_and_json_mode() -> None:
    provider = build_llm(_settings())
    payload = provider._build_payload("system text", "user text", None)

    assert payload["model"] == "deepseek-flash"
    assert payload["messages"][0] == {"role": "system", "content": "system text"}
    assert payload["messages"][1] == {"role": "user", "content": "user text"}
    # DeepSeek 的 JSON 模式
    assert payload["response_format"] == {"type": "json_object"}
    assert payload["temperature"] == 0.3
    # 输出上限必须显式给够，否则 JSON 会被截断成空白
    assert payload["max_tokens"] == 4096
    # DeepSeek 思考模式默认开启，结构化任务要显式关掉
    assert payload["thinking"] == {"type": "disabled"}


def test_non_deepseek_openai_compatible_service_gets_no_thinking_field() -> None:
    """thinking 是 DeepSeek 专有字段，发给 OpenAI / vLLM 会被拒。"""
    provider = build_llm(
        _settings(llm_base_url="https://api.openai.com/v1", llm_model="gpt-4o-mini")
    )
    payload = provider._build_payload("s", "u", None)
    assert "thinking" not in payload
    assert payload["response_format"] == {"type": "json_object"}


def test_llm_think_true_keeps_deepseek_thinking_mode() -> None:
    """LLM_THINK=true 表示允许模型先思考，此时不下发关闭指令。"""
    provider = build_llm(_settings(llm_think=True))
    payload = provider._build_payload("s", "u", None)
    assert "thinking" not in payload


def test_deepseek_url_and_auth_header() -> None:
    provider = build_llm(_settings())
    url = f"{provider.settings.llm_base_url.rstrip('/')}{provider._path}"
    assert url == "https://api.deepseek.com/chat/completions"

    headers = provider._headers()
    assert headers["Authorization"] == "Bearer sk-test"
    assert headers["Content-Type"] == "application/json"


def test_unknown_provider_raises() -> None:
    from app.clients.llm import LLMError

    try:
        build_llm(_settings(llm_provider="not-a-provider"))
    except LLMError:
        return
    raise AssertionError("未知 provider 应当抛 LLMError")


def test_ollama_payload_forces_json_and_disables_thinking() -> None:
    provider = build_llm(
        _settings(
            llm_provider="ollama",
            llm_base_url="http://127.0.0.1:11434",
            llm_model="qwen3.5:9b",
            llm_api_key="",
        )
    )
    payload = provider._build_payload("s", "u", None)
    assert payload["format"] == "json"
    assert payload["think"] is False
    assert payload["stream"] is False
