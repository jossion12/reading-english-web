"""结构化解析与词数校验的单元测试。"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.parse import ParseError, parse_article
from app.validate import (
    ValidationReport,
    count_words,
    deterministic_checks,
    merge_llm_check,
)


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


def test_count_words_counts_numbers_as_words() -> None:
    """数字要算一个词：难度区间照中考计数定，只数字母会让带年份的稿件悄悄超区间。"""
    # In / 2026, / more / than / 10,000 / patients / were / seen.  -> 8
    assert count_words("In 2026, more than 10,000 patients were seen.") == 8


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


# --------------------------------------------------- P0 读后思考 / 语言质量 ---
def test_parse_reads_reflection_fields() -> None:
    """扩写模板新增两个输出字段，解析层要原样带出来（R2-4 / R5）。"""
    raw = (
        '{"title_en": "A Helping Hand", "title_cn": "伸出的手", '
        '"english_paras": ["It rained."], "chinese_paras": ["下雨了。"], '
        '"reflection_en": "Small kind acts can change a day.", '
        '"reflection_cn": "一个小小的善举也能点亮一天。"}'
    )
    parsed = parse_article(raw)
    assert parsed.reflection_en == "Small kind acts can change a day."
    assert parsed.reflection_cn == "一个小小的善举也能点亮一天。"


def test_parse_without_reflection_defaults_to_empty() -> None:
    """常青模板与存量草稿没有这两个字段，不能因此判解析失败。"""
    parsed = parse_article(
        '{"title_en": "T", "title_cn": "C", '
        '"english_paras": ["a"], "chinese_paras": ["甲"]}'
    )
    assert parsed.reflection_en == ""
    assert parsed.reflection_cn == ""


def _clean_base() -> ValidationReport:
    return deterministic_checks(
        english_paras=["word " * 100],
        chinese_paras=["中文"],
        min_words=80,
        max_words=120,
    )


def test_merge_llm_check_flags_language_quality() -> None:
    """判官报中式英语 + 同义反复时，两个布尔位都要落进报告并阻止入库。"""
    merged = merge_llm_check(
        _clean_base(),
        {
            "no_fabrication": True,
            "no_sensitive": True,
            "natural_english": False,
            "repetition_free": False,
            "issues": [
                "Rewrite 'new era civilization practice' in plain English.",
                "Delete this sentence: 'It is meant to let AI better serve people.'",
            ],
        },
        min_words=80,
        max_words=120,
    )
    assert merged.natural_english is False
    assert merged.repetition_free is False
    assert not merged.passed
    assert "LLM 复核判定存在中式英语或回译腔" in merged.issues
    assert "LLM 复核判定存在同义反复" in merged.issues
    # 判官引用的原句要保留，重写时得知道改哪句
    assert any("new era civilization practice" in i for i in merged.issues)
    assert "natural_english" in merged.to_dict()
    assert merged.to_dict()["repetition_free"] is False


def test_merge_llm_check_accepts_alias_and_string_false() -> None:
    """判官可能按检查项名回 no_repetition，或把 false 写成字符串。"""
    merged = merge_llm_check(
        _clean_base(),
        {"natural_english": "false", "no_repetition": False},
        min_words=80,
        max_words=120,
    )
    assert merged.natural_english is False
    assert merged.repetition_free is False


def test_legacy_validation_dict_defaults_language_flags_to_pass() -> None:
    """旧草稿日志里没有新字段，不能因为缺键把历史草稿判成不合格。"""
    report = ValidationReport.from_dict(
        {"word_count": 100, "word_count_ok": True, "issues": []}
    )
    assert report.natural_english is True
    assert report.repetition_free is True
    assert report.passed


def test_validation_report_roundtrip_keeps_language_flags() -> None:
    report = ValidationReport(
        word_count=100,
        word_count_ok=True,
        natural_english=False,
        repetition_free=False,
    )
    restored = ValidationReport.from_dict(report.to_dict())
    assert restored.natural_english is False
    assert restored.repetition_free is False
    assert restored.passed is False
