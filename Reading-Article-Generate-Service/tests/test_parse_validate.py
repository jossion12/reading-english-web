"""结构化解析与词数校验的单元测试。"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.parse import ParseError, parse_article
from app.validate import count_words, deterministic_checks, merge_llm_check


def test_parse_plain_json() -> None:
    raw = '{"title_en": "A Rainy Day", "title_cn": "雨天", "english_paras": ["It rained.", "We stayed."], "chinese_paras": ["下雨了。", "我们待着。"]}'
    parsed = parse_article(raw)
    assert parsed.title_en == "A Rainy Day"
    assert parsed.title_cn == "雨天"
    assert parsed.english_paras == ["It rained.", "We stayed."]
    assert parsed.chinese_paras == ["下雨了。", "我们待着。"]


def test_parse_with_markdown_fence() -> None:
    raw = '```json\n{"title_en": "T", "title_cn": "C", "english_paras": ["a"], "chinese_paras": ["b"]}\n```'
    parsed = parse_article(raw)
    assert parsed.title_en == "T"


def test_parse_with_surrounding_prose() -> None:
    raw = 'Sure! Here is the passage:\n{"title_en": "T", "title_cn": "C", "english_paras": ["a"], "chinese_paras": ["b"]}\nHope it helps.'
    parsed = parse_article(raw)
    assert parsed.english_paras == ["a"]


def test_parse_missing_field_raises() -> None:
    raw = '{"title_en": "T", "english_paras": ["a"], "chinese_paras": ["b"]}'
    with pytest.raises(ParseError) as exc:
        parse_article(raw)
    assert "title_cn" in str(exc.value)


def test_parse_invalid_json_raises() -> None:
    with pytest.raises(ParseError):
        parse_article("not json at all")


def test_count_words_handles_contractions() -> None:
    # It / doesn't / matter, / well-known / facts.  -> 5
    assert count_words("It doesn't matter, well-known facts.") == 5


def test_deterministic_checks_word_range() -> None:
    paras = ["word " * 100]
    report = deterministic_checks(
        english_paras=paras,
        chinese_paras=["中文", "第二段"],
        min_words=80,
        max_words=120,
    )
    assert report.word_count == 100
    assert report.word_count_ok is True
    assert report.para_match is False
    assert not report.passed


def test_deterministic_checks_paragraph_mismatch() -> None:
    report = deterministic_checks(
        english_paras=["a", "b"],
        chinese_paras=["甲"],
        min_words=1,
        max_words=100,
    )
    assert report.para_match is False
    assert any("段落数不一致" in i for i in report.issues)


def test_merge_llm_check_flags_fabrication() -> None:
    base = deterministic_checks(
        english_paras=["word " * 90],
        chinese_paras=["中文"],
        min_words=80,
        max_words=120,
    )
    merged = merge_llm_check(
        base,
        {"word_count": 90, "word_count_ok": True, "no_fabrication": False, "issues": ["编造了数字"]},
        min_words=80,
        max_words=120,
    )
    assert merged.no_fabrication is False
    assert not merged.passed
    assert any("编造" in i for i in merged.issues)


def test_merge_llm_check_keeps_deterministic_issues() -> None:
    base = deterministic_checks(
        english_paras=["word " * 10],
        chinese_paras=["中文"],
        min_words=80,
        max_words=120,
    )
    merged = merge_llm_check(base, {"word_count_ok": True}, min_words=80, max_words=120)
    assert merged.word_count_ok is False
    assert any("词数" in i for i in merged.issues)


def test_merge_llm_check_ignores_llm_word_count_miscount() -> None:
    """LLM 少算词数不应把合格稿件判为不合格（词数以代码计数为准）。"""
    base = deterministic_checks(
        english_paras=["word " * 100],
        chinese_paras=["中文"],
        min_words=80,
        max_words=120,
    )
    merged = merge_llm_check(
        base,
        {"word_count": 69, "word_count_ok": False, "issues": ["Word count is 69"]},
        min_words=80,
        max_words=120,
    )
    assert merged.word_count == 100
    assert merged.word_count_ok is True
    assert merged.llm_word_count == 69
