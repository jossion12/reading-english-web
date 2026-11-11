"""素材拆解单元测试：事实句 / 禁止项的切分与逐段派活。"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.material import assign_facts, split_material

SUMMARY = """新闻标题：贵州山区女教师雨雪天徒步翻山到学生家中家访
核心事实：贵州省黔东南某山区小学教师李雨在暴雪天气独自徒步三小时，翻越两座山头，到学生家中进行家访并送上课本。
背景意义：乡村教育工作者在恶劣天气下仍坚持家访，保障了偏远山区学生不因天气缺课。
正向导向：展现教师的责任心与奉献精神，引导学生理解什么是真正的关爱与坚持。
禁止加入内容：不得编造教师姓名、学校名称、受访学生家庭细节；不得夸大或加入伤亡、补助金额等原文没有的信息。"""


def test_split_material_extracts_facts_and_prohibitions() -> None:
    facts, prohibitions = split_material(SUMMARY)

    assert facts, "应当拆出事实句"
    # 标题不进事实清单（标题是压缩句，容易诱导模型造名字）
    assert not any("新闻标题" in f for f in facts)
    # 核心事实被切成独立的事实句
    assert any("独自徒步三小时" in f for f in facts)
    assert any("送上课本" in f for f in facts)
    # 背景意义、正向导向也是素材里的内容，可以写
    assert any("不因天气缺课" in f for f in facts)
    assert any("关爱与坚持" in f for f in facts)
    # 禁止项单独拆出来（整句保留，不能切碎丢掉「不得编造」）
    assert prohibitions
    assert any("不得编造" in p for p in prohibitions)
    assert any("学校名称" in p for p in prohibitions)


def test_split_material_keeps_plain_summary_usable() -> None:
    """没有标签的普通梗概也要能拆出事实（按标点切句）。"""
    facts, prohibitions = split_material("老师在暴雪中走了三小时，翻过两座山，到学生家中家访并送上课本。")
    assert facts
    # 中文摘要里一个句号句常含多个并列事实，逗号处也要切
    assert len(facts) >= 3
    assert any("翻过两座山" in f for f in facts)
    assert prohibitions == []


def test_split_material_ignores_short_fragments() -> None:
    facts, _ = split_material("核心事实：好。\n背景意义：乡村教师在暴雪中独自徒步三小时到学生家中家访。")
    assert all(len(f) >= 5 for f in facts)
    assert not any(f == "好" for f in facts)


def test_assign_facts_gives_narrative_to_front_and_meaning_to_the_end() -> None:
    """按素材段分配：核心事实占前面，背景意义 / 正向导向落到结尾段。"""
    grouped = [
        ("核心事实", ["F1", "F2", "F3"]),
        ("背景意义", ["F4", "F5"]),
        ("正向导向", ["F6", "F7"]),
    ]
    buckets = assign_facts(grouped, 4)

    assert len(buckets) == 4
    assert buckets[0] == ["F1", "F2"]
    assert buckets[1] == ["F3"]
    assert buckets[2] == ["F4", "F5"]
    assert buckets[3] == ["F6", "F7"]
    # 不重不漏
    flat = [f for b in buckets for f in b]
    assert flat == ["F1", "F2", "F3", "F4", "F5", "F6", "F7"]


def test_assign_facts_handles_fewer_facts_than_paragraphs() -> None:
    buckets = assign_facts([("核心事实", ["F1", "F2"])], 4)
    assert len(buckets) == 4
    assert sum(len(b) for b in buckets) == 2


def test_assign_facts_handles_empty_material() -> None:
    buckets = assign_facts([], 4)
    assert buckets == [[], [], [], []]


def test_assign_facts_merges_when_paragraphs_are_too_few() -> None:
    """素材段比段落还多时，多出来的并进最后一段，不能丢事实。"""
    grouped = [("核心事实", ["F1"]), ("背景意义", ["F2"]), ("正向导向", ["F3"])]
    buckets = assign_facts(grouped, 2)
    assert len(buckets) == 2
    flat = [f for b in buckets for f in b]
    assert flat == ["F1", "F2", "F3"]
