"""可插拔 LLM 适配器（异步版，与生成服务同构）。

默认本机 Ollama，可切换到任意 OpenAI 兼容接口。
"""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from typing import Any

import httpx

from app.config import Settings


class LLMError(RuntimeError):
    """LLM 调用或返回解析失败。"""


class LLMProvider(ABC):
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    _path = "/chat/completions"

    @abstractmethod
    def _build_payload(self, system: str, user: str, temperature: float | None) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def _extract(self, data: dict[str, Any]) -> str:
        raise NotImplementedError

    def _headers(self) -> dict[str, str]:
        return {"Content-Type": "application/json"}

    async def chat(self, system: str, user: str, *, temperature: float | None = None) -> str:
        payload = self._build_payload(system, user, temperature)
        url = f"{self.settings.llm_base_url.rstrip('/')}{self._path}"
        try:
            async with httpx.AsyncClient(timeout=self.settings.llm_timeout) as client:
                resp = await client.post(url, json=payload, headers=self._headers())
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPStatusError as exc:
            raise LLMError(f"LLM 调用失败 HTTP {exc.response.status_code}: {exc.response.text[:500]}") from exc
        except httpx.HTTPError as exc:
            raise LLMError(f"无法连接 LLM 服务 ({url}): {exc}") from exc
        except ValueError as exc:
            raise LLMError(f"LLM 返回的不是 JSON: {exc}") from exc
        return self._extract(data)

    async def chat_json(self, system: str, user: str, *, temperature: float | None = None) -> dict[str, Any]:
        raw = await self.chat(system, user, temperature=temperature)
        return extract_json(raw)


class OllamaProvider(LLMProvider):
    _path = "/api/chat"

    def _build_payload(self, system: str, user: str, temperature: float | None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.settings.llm_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "options": {
                "temperature": self.settings.llm_temperature if temperature is None else temperature,
            },
        }
        if not self.settings.llm_think:
            payload["think"] = False
        return payload

    def _extract(self, data: dict[str, Any]) -> str:
        message = data.get("message") or {}
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise LLMError(f"Ollama 返回内容为空: {json.dumps(data, ensure_ascii=False)[:300]}")
        return content


class OpenAICompatProvider(LLMProvider):
    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.settings.llm_api_key:
            headers["Authorization"] = f"Bearer {self.settings.llm_api_key}"
        return headers

    def _build_payload(self, system: str, user: str, temperature: float | None) -> dict[str, Any]:
        return {
            "model": self.settings.llm_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": self.settings.llm_temperature if temperature is None else temperature,
        }

    def _extract(self, data: dict[str, Any]) -> str:
        choices = data.get("choices") or []
        if not choices:
            raise LLMError(f"LLM 未返回 choices: {json.dumps(data, ensure_ascii=False)[:300]}")
        message = choices[0].get("message") or {}
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise LLMError(f"LLM 返回内容为空: {json.dumps(data, ensure_ascii=False)[:300]}")
        return content


def build_llm(settings: Settings) -> LLMProvider:
    provider = settings.llm_provider.strip().lower()
    if provider == "ollama":
        return OllamaProvider(settings)
    if provider in {"openai", "openai-compatible", "compat"}:
        return OpenAICompatProvider(settings)
    raise LLMError(f"未知的 LLM_PROVIDER: {settings.llm_provider}（可选: ollama / openai）")


_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)


def extract_json(raw: str) -> dict[str, Any]:
    text = (raw or "").strip()
    if not text:
        raise LLMError("LLM 返回空内容")
    try:
        value = json.loads(text)
        if isinstance(value, dict):
            return value
    except json.JSONDecodeError:
        pass
    fenced = _FENCE_RE.search(text)
    if fenced:
        try:
            value = json.loads(fenced.group(1).strip())
            if isinstance(value, dict):
                return value
        except json.JSONDecodeError:
            pass
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        try:
            value = json.loads(text[start : end + 1])
            if isinstance(value, dict):
                return value
        except json.JSONDecodeError as exc:
            raise LLMError(f"LLM 返回内容不是合法 JSON: {exc}; 原文前 500 字: {text[:500]}") from exc
    raise LLMError(f"LLM 返回内容中找不到 JSON 对象: 原文前 500 字: {text[:500]}")
