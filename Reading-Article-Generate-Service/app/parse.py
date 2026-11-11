"""结构化解析：把 LLM 返回的 JSON 拆成文章字段（PRD §2.4）。"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.clients.llm import LLMError, extract_json


class ParseError(RuntimeError):
    """LLM 输出无法解析为文章结构。"""


_WS_RE = re.compile(r"[ \t　]+")
_BLANKS_RE = re.compile(r"\n{3,}")


@dataclass
class ParsedArticle:
    title_en: str
    title_cn: str
    english_paras: list[str]
    chinese_paras: list[str]


def _clean_paragraphs(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        if not isinstance(item, str):
            item = str(item) if item is not None else ""
        text = _WS_RE.sub(" ", item).strip()
        text = _BLANKS_RE.sub("\n\n", text)
        if text:
            out.append(text)
    return out


def _clean_title(value: object) -> str:
    if not isinstance(value, str):
        value = "" if value is None else str(value)
    return _WS_RE.sub(" ", value).strip().strip('"“”\'')


def parse_article(raw: str) -> ParsedArticle:
    """解析 LLM 原始输出。

    抛出 LLMError（JSON 不合法）或 ParseError（字段缺失/类型不对）。
    """
    try:
        data = extract_json(raw)
    except LLMError as exc:
        raise ParseError(str(exc)) from exc

    title_en = _clean_title(data.get("title_en"))
    title_cn = _clean_title(data.get("title_cn"))
    english_paras = _clean_paragraphs(data.get("english_paras"))
    chinese_paras = _clean_paragraphs(data.get("chinese_paras"))

    missing: list[str] = []
    if not title_en:
        missing.append("title_en")
    if not title_cn:
        missing.append("title_cn")
    if not english_paras:
        missing.append("english_paras")
    if not chinese_paras:
        missing.append("chinese_paras")
    if missing:
        raise ParseError(f"LLM 返回缺少必要字段: {', '.join(missing)}")

    return ParsedArticle(
        title_en=title_en,
        title_cn=title_cn,
        english_paras=english_paras,
        chinese_paras=chinese_paras,
    )
