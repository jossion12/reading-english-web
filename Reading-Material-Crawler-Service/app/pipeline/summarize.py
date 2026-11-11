"""LLM 标准化梗概提炼（PRD §2.5）。

输出固定模板：新闻标题 / 核心事实 / 背景意义 / 正向导向 / 禁止加入内容。
强制约束：仅使用原文信息，信息不足则省略，禁止编造事实。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from app.clients.llm import LLMError, LLMProvider, build_llm
from app.config import Settings, get_settings


class SummaryError(RuntimeError):
    """梗概提炼失败。"""


_FIELDS = {
    "新闻标题": "title",
    "核心事实": "core_facts",
    "背景意义": "background",
    "正向导向": "positive_direction",
    "禁止加入内容": "forbidden",
}


@dataclass
class MaterialSummary:
    title: str = ""
    core_facts: str = ""
    background: str = ""
    positive_direction: str = ""
    forbidden: str = ""
    negative: bool = False
    negative_reason: str = ""
    raw: str = ""
    extra: dict[str, str] = field(default_factory=dict)

    def to_text(self) -> str:
        """存进 source_log.source_summary 的标准化全文。"""
        lines = [
            f"新闻标题：{self.title}",
            f"核心事实：{self.core_facts}",
            f"背景意义：{self.background}",
            f"正向导向：{self.positive_direction}",
            f"禁止加入内容：{self.forbidden}",
        ]
        if self.negative:
            lines.append(f"负面内容：是（{self.negative_reason}）")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "core_facts": self.core_facts,
            "background": self.background,
            "positive_direction": self.positive_direction,
            "forbidden": self.forbidden,
            "negative": self.negative,
            "negative_reason": self.negative_reason,
            "raw": self.raw,
            "text": self.to_text(),
        }


def _render(template: str, values: dict[str, Any]) -> str:
    out = template
    for key, value in values.items():
        out = out.replace("{{" + key + "}}", str(value))
    return out


def parse_summary(raw: str) -> MaterialSummary:
    """把 LLM 输出解析成结构化梗概。"""
    text = (raw or "").strip()
    if not text:
        raise SummaryError("LLM 返回空内容")

    result = MaterialSummary(raw=text)
    for line in text.splitlines():
        stripped = line.strip().lstrip("-*·• ").strip()
        if not stripped:
            continue
        matched = False
        for prefix, attr in _FIELDS.items():
            if stripped.startswith(prefix):
                value = stripped[len(prefix):].strip().lstrip("：:").strip()
                setattr(result, attr, value)
                matched = True
                break
        if matched:
            continue
        if stripped.startswith("负面内容"):
            body = stripped[len("负面内容"):].strip().lstrip("：:").strip()
            if body.startswith("是"):
                result.negative = True
                result.negative_reason = body[1:].strip().lstrip("（()）").strip()
            continue
        if stripped.startswith(">"):
            continue
        if result.extra:
            key = list(result.extra.keys())[-1]
            result.extra[key] = (result.extra[key] + " " + stripped).strip()
        else:
            result.extra["_tail"] = stripped

    if not result.title:
        raise SummaryError(f"梗概解析失败：未找到「新闻标题」字段；原始输出前 400 字: {text[:400]}")
    if not result.core_facts:
        raise SummaryError(f"梗概解析失败：未找到「核心事实」字段；原始输出前 400 字: {text[:400]}")
    return result


class SummaryPipeline:
    def __init__(self, llm: LLMProvider | None = None, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.llm = llm or build_llm(self.settings)
        self.prompts = self._load_prompts()

    @staticmethod
    def _load_prompts() -> dict[str, Any]:
        path: Path = get_settings().prompts_path
        if not path.exists():
            raise SummaryError(f"Prompt 配置不存在: {path}")
        with path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        if not isinstance(data, dict):
            raise SummaryError(f"Prompt 配置格式错误: {path}")
        return data

    async def summarize(self, content: str) -> MaterialSummary:
        block = self.prompts.get("summary") or {}
        system = str(block.get("system", "")).strip()
        template = str(block.get("template", ""))
        if not template:
            raise SummaryError("Prompt 配置错误：summary.template 为空")
        user = _render(template, {"content": content or ""}).strip()
        try:
            raw = await self.llm.chat(system, user)
        except LLMError as exc:
            raise SummaryError(f"LLM 调用失败: {exc}") from exc
        return parse_summary(raw)

    async def score_candidates(self, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """全自动打分模式（PRD §2.3 预留扩展）。"""
        block = self.prompts.get("scoring") or {}
        system = str(block.get("system", "")).strip()
        template = str(block.get("template", ""))
        if not template:
            raise SummaryError("Prompt 配置错误：scoring.template 为空")
        listing = "\n".join(
            f'- url: {c.get("url")}\n  标题: {c.get("title")}\n  摘要: {c.get("summary", "")[:200]}'
            for c in candidates
        )
        user = _render(template, {"candidates": listing}).strip()
        try:
            return (await self.llm.chat_json(system, user)).get("scores", []) or []
        except LLMError as exc:
            raise SummaryError(f"LLM 打分失败: {exc}") from exc
