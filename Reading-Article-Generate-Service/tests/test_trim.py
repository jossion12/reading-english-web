"""app/trim.py 的单元测试：超长稿件裁剪到难度上限。"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.trim import (  # noqa: E402
    split_en_sentences,
    split_zh_sentences,
    trim_to_max_words,
)
from app.validate import count_words  # noqa: E402


def test_split_en_sentences_basic() -> None:
    text = "He went home. She stayed behind! Did they agree? Yes."
    assert split_en_sentences(text) == [
        "He went home.",
        "She stayed behind!",
        "Did they agree?",
        "Yes.",
    ]


def test_split_en_sentences_keeps_abbrev() -> None:
    text = "Dr. Smith came in. The U.S. team waited."
    sentences = split_en_sentences(text)
    assert sentences == ["Dr. Smith came in.", "The U.S. team waited."]


def test_split_zh_sentences() -> None:
    text = "他回到了家。她留了下来！你同意吗？"
    assert split_zh_sentences(text) == ["他回到了家。", "她留了下来！", "你同意吗？"]


def test_trim_leaves_in_band_untouched() -> None:
    en = ["A short one. And another."]
    zh = ["短句。另一句。"]
    result = trim_to_max_words(en, zh, max_words=100)
    assert not result.trimmed
    assert result.english_paras == en
    assert result.words_before == result.words_after


def test_trim_cuts_to_max_words() -> None:
    en = [
        "The team helped many old people every week. They bought food and medicine. "
        "The community also built a response team. Everyone joined the work.",
        "A second paragraph here. It has two sentences too. And a third one.",
    ]
    zh = [
        "志愿者每周帮助多位老人。他们买菜并取药。社区还建立了响应队伍。每个人都参加了这项工作。",
        "第二段内容。这里也有两句。还有第三句。",
    ]
    result = trim_to_max_words(en, zh, max_words=20)
    assert result.trimmed
    assert count_words("\n".join(result.english_paras)) <= 20
    # 段落数量不变，中英仍一一对应
    assert len(result.english_paras) == len(en) == len(result.chinese_paras)
    # 没有空段落
    assert all(p.strip() for p in result.english_paras)
    assert all(p.strip() for p in result.chinese_paras)


def test_trim_never_empties_paragraph() -> None:
    en = ["Only one sentence here."]
    zh = ["只有一句话。"]
    result = trim_to_max_words(en, zh, max_words=1)
    # 只有一句的段落无法再裁，保持原样而不是产出空段落
    assert result.english_paras == en
    assert all(p.strip() for p in result.english_paras)


def test_trim_keeps_chinese_when_single_sentence() -> None:
    en = ["One. Two. Three.", "Only one sentence."]
    zh = ["只有一句话。", "只有一句话。"]
    result = trim_to_max_words(en, zh, max_words=2)
    assert all(p.strip() for p in result.chinese_paras)


def test_trim_paragraph_count_preserved() -> None:
    en = [f"Sentence one here. Sentence two here. Sentence three here." for _ in range(3)]
    zh = ["第一句。第二句。第三句。" for _ in range(3)]
    result = trim_to_max_words(en, zh, max_words=15)
    assert len(result.english_paras) == 3
    assert len(result.chinese_paras) == 3
    assert count_words("\n".join(result.english_paras)) <= 15
