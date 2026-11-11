"""可插拔 LLM 适配器。

默认走本机 Ollama（离线、免费），通过环境变量即可切换到任何 OpenAI 兼容接口
（MiniMax / OpenAI / vLLM / LM Studio …），两个后端服务的调用方式完全一致。

    LLM_PROVIDER=ollama | openai
    LLM_BASE_URL=...
    LLM_MODEL=...
    LLM_API_KEY=...        # openai 兼容模式必填
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
    """统一的对话补全接口。"""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @abstractmethod
    def _post(self, path: str, payload: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def _extract(self, data: dict[str, Any]) -> str:
        raise NotImplementedError

    def chat_json(self, system: str, user: str, *, temperature: float | None = None) -> str:
        """发起一次对话并要求返回 JSON 文本（不保证是合法 JSON，交给 parse 层兜底）。"""
        payload = self._build_payload(system, user, temperature)
        headers = self._headers()
        data = self._post(self._path, payload, headers)
        return self._extract(data)

    def _build_payload(self, system: str, user: str, temperature: float | None) -> dict[str, Any]:
        return {
            "model": self.settings.llm_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": self.settings.llm_temperature if temperature is None else temperature,
        }

    def _headers(self) -> dict[str, str]:
        return {"Content-Type": "application/json"}

    _path = "/chat/completions"


class OllamaProvider(LLMProvider):
    """本机 Ollama。使用 /api/chat，并强制 JSON 输出模式。"""

    _path = "/api/chat"

    def _build_payload(self, system: str, user: str, temperature: float | None) -> dict[str, Any]:
        payload = {
            "model": self.settings.llm_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "format": "json",
            "options": {
                "temperature": self.settings.llm_temperature if temperature is None else temperature,
            },
        }
        # qwen3 / qwen3.5 等思考型模型会额外输出 reasoning 段，结构化任务需要关闭
        if not self.settings.llm_think:
            payload["think"] = False
        return payload

    def _post(self, path: str, payload: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
        url = f"{self.settings.llm_base_url.rstrip('/')}{path}"
        try:
            with httpx.Client(timeout=self.settings.llm_timeout) as client:
                resp = client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPStatusError as exc:  # pragma: no cover - 依赖外部服务
            body = exc.response.text[:500]
            raise LLMError(f"Ollama 调用失败 HTTP {exc.response.status_code}: {body}") from exc
        except httpx.HTTPError as exc:  # pragma: no cover - 依赖外部服务
            raise LLMError(f"无法连接 Ollama ({url}): {exc}") from exc

    def _extract(self, data: dict[str, Any]) -> str:
        message = data.get("message") or {}
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise LLMError(f"Ollama 返回内容为空: {json.dumps(data, ensure_ascii=False)[:300]}")
        return content


class OpenAICompatProvider(LLMProvider):
    """任何 OpenAI 兼容的 /chat/completions 接口。"""

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.settings.llm_api_key:
            headers["Authorization"] = f"Bearer {self.settings.llm_api_key}"
        return headers

    def _is_deepseek(self) -> bool:
        return "deepseek" in self.settings.llm_base_url.lower()

    def _build_payload(self, system: str, user: str, temperature: float | None) -> dict[str, Any]:
        payload = super()._build_payload(system, user, temperature)
        payload["response_format"] = {"type": "json_object"}
        if self.settings.llm_max_tokens > 0:
            # 云端接口的默认输出上限可能不够长，JSON 模式被截断会返回一片空白
            payload["max_tokens"] = self.settings.llm_max_tokens
        if self._is_deepseek() and not self.settings.llm_think:
            # DeepSeek 的思考模式默认开启（思考模式下 temperature 等参数无效），
            # 结构化任务用非思考模式更稳、更快、更便宜；该字段只有 DeepSeek 认。
            payload["thinking"] = {"type": "disabled"}
        return payload

    def _post(self, path: str, payload: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
        url = f"{self.settings.llm_base_url.rstrip('/')}{path}"
        attempt = dict(payload)
        try:
            with httpx.Client(timeout=self.settings.llm_timeout) as client:
                resp = client.post(url, json=attempt, headers=headers)
                # 部分兼容实现不认识 response_format / thinking，逐级退化为普通调用
                for optional in ("response_format", "thinking"):
                    if resp.status_code != 400:
                        break
                    if optional not in attempt:
                        continue
                    attempt.pop(optional)
                    resp = client.post(url, json=attempt, headers=headers)
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPStatusError as exc:  # pragma: no cover - 依赖外部服务
            body = exc.response.text[:500]
            raise LLMError(f"LLM 调用失败 HTTP {exc.response.status_code}: {body}") from exc
        except httpx.HTTPError as exc:  # pragma: no cover - 依赖外部服务
            raise LLMError(f"无法连接 LLM 服务 ({url}): {exc}") from exc

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
    """按配置构造 LLM 适配器。"""
    provider = settings.llm_provider.strip().lower()
    if provider == "ollama":
        return OllamaProvider(settings)
    if provider in {"openai", "openai-compatible", "compat"}:
        return OpenAICompatProvider(settings)
    raise LLMError(f"未知的 LLM_PROVIDER: {settings.llm_provider}（可选: ollama / openai）")


# ---------------------------------------------------------------------------
# JSON 解析辅助
# ---------------------------------------------------------------------------
_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)


def extract_json(raw: str) -> dict[str, Any]:
    """从 LLM 原始输出中稳健地抠出一个 JSON 对象。

    依次尝试：整体解析 -> 去 markdown 围栏 -> 截取首个 { 到最后一个 }。
    """
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

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        try:
            value = json.loads(text[start : end + 1])
            if isinstance(value, dict):
                return value
        except json.JSONDecodeError as exc:
            raise LLMError(f"LLM 返回内容不是合法 JSON: {exc}; 原文前 500 字: {text[:500]}") from exc

    raise LLMError(f"LLM 返回内容中找不到 JSON 对象: 原文前 500 字: {text[:500]}")
