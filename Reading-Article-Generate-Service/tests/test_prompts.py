"""Prompt 模板渲染的单元测试（不触网）。"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.prompts import PromptError, PromptLibrary


@pytest.fixture(scope="module")
def library() -> PromptLibrary:
    return PromptLibrary()


def test_word_ranges_match_prd(library: PromptLibrary) -> None:
    assert library.word_range("L1") == (80, 120)
    assert library.word_range("L2") == (120, 180)
    assert library.word_range("L3") == (180, 240)


def test_unknown_level_raises(library: PromptLibrary) -> None:
    with pytest.raises(PromptError):
        library.level_config("L9")


def test_expansion_prompt_contains_material_and_limits(library: PromptLibrary) -> None:
    system, user = library.render_expansion(summary="素材梗概正文", level="L2")
    assert "素材梗概正文" in user
    assert "120" in user and "180" in user
    assert "L2" in user
    assert "{{" not in user, "模板占位符应全部被替换"
    assert system


def test_evergreen_prompt_has_no_material_placeholder(library: PromptLibrary) -> None:
    _, user = library.render_expansion(summary="", level="L1", evergreen=True, theme="人与自然")
    assert "人与自然" in user
    assert "{{" not in user


def test_self_check_prompt_contains_both_sides(library: PromptLibrary) -> None:
    _, user = library.render_self_check(
        summary="梗概",
        level="L1",
        title_en="EN",
        title_cn="CN",
        english_paras=["one", "two"],
        chinese_paras=["一", "二"],
    )
    assert "English paragraphs (count = 2)" in user
    assert "Chinese paragraphs (count = 2)" in user
    assert "{{" not in user


def test_taxonomy_has_four_themes(library: PromptLibrary) -> None:
    meta = library.taxonomy_meta()
    assert set(meta["themes"]) == {"人与自我", "人与社会", "人与自然", "人与科技"}


def test_para_min_leaves_margin_above_lower_bound(library: PromptLibrary) -> None:
    """每段下限乘以段落数后必须高于词数区间下限，否则白写。"""
    for level in ("L1", "L2", "L3"):
        low, _ = library.word_range(level)
        total_min = library.para_min(level) * library.para_count(level)
        assert total_min > low, f"{level}: 每段下限撑不满总量下限"


def test_sentences_per_para_is_configured(library: PromptLibrary) -> None:
    """句数约束是小模型唯一稳定生效的长度控制手段，必须每档都配了。"""
    for level in ("L1", "L2", "L3"):
        low, high = library.sentences_per_para(level)
        assert 2 <= low <= high <= 8


def test_rewrite_feedback_names_actual_paragraph_count() -> None:
    """小模型少写段落时，回喂必须点明「你写了 N 段」。"""
    from app.generator import ArticleGenerator
    from app.validate import deterministic_checks

    report = deterministic_checks(
        english_paras=["a few words here", "and another paragraph"],
        chinese_paras=["甲", "乙"],
        min_words=120,
        max_words=180,
        para_range=(3, 5),
    )
    assert report.para_count == 2
    assert report.para_count_ok is False

    gen = ArticleGenerator.__new__(ArticleGenerator)
    from app.prompts import get_prompts

    gen.prompts = get_prompts()
    feedback = gen._rewrite_feedback(report, 120, 180, "L2")
    assert "You wrote 2 paragraphs" in feedback
    assert "3-5 paragraphs" in feedback
