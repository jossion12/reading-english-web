"""素材拆解单元测试：事实句 / 禁止项 / 读后思考的切分与逐段派活。

P0 语言修复 R3 之后，「正向导向」与「地名清单」都不进事实清单：前者单独
返回给读后思考字段，后者只作备查，否则正文末段必然出现说教段和四级拼音地名。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.material import assign_facts, split_material, split_material_sections

SUMMARY = """新闻标题：贵州山区女教师雨雪天徒步翻山到学生家中家访
核心事实：贵州省黔东南某山区小学教师李雨在暴雪天气独自徒步三小时，翻越两座山头，到学生家中进行家访并送上课本。
背景意义：乡村教育工作者在恶劣天气下仍坚持家访，保障了偏远山区学生不因天气缺课。
正向导向：展现教师的责任心与奉献精神，引导学生理解什么是真正的关爱与坚持。
地名清单：黔东南（省/市/区/街道略）
禁止加入内容：不得编造教师姓名、学校名称、受访学生家庭细节；不得夸大或加入伤亡、补助金额等原文没有的信息。"""

LEGACY_SUMMARY = """新闻标题：贵州山区女教师雨雪天徒步翻山到学生家中家访
核心事实：教师在暴雪天气独自徒步三小时，翻越两座山头，到学生家中家访并送上课本。
背景意义：乡村教育工作者在恶劣天气下仍坚持家访。
正向导向：展现教师的责任心与奉献精神。
禁止加入内容：不得编造教师姓名、学校名称。"""


def test_split_material_extracts_facts_and_prohibitions() -> None:
    facts, prohibitions = split_material(SUMMARY)

    assert facts, "应当拆出事实句"
    # 标题不进事实清单（标题是压缩句，容易诱导模型造名字）
    assert not any("新闻标题" in f for f in facts)
    # 核心事实被切成独立的事实句
    assert any("独自徒步三小时" in f for f in facts)
    assert any("送上课本" in f for f in facts)
    # 背景意义仍是合法事实，作为新闻结尾派给末段
    assert any("不因天气缺课" in f for f in facts)
    # 正向导向与地名清单都不进事实清单
    assert not any("关爱与坚持" in f for f in facts)
    assert not any("省/市/区/街道略" in f for f in facts)
    # 禁止项单独拆出来（整句保留，不能切碎丢掉「不得编造」）
    assert prohibitions
    assert any("不得编造" in p for p in prohibitions)
    assert any("学校名称" in p for p in prohibitions)


def test_reflection_is_separated_from_facts() -> None:
    """正向导向单独返回，既不进 facts 也不参加逐段派活（P0 R3 核心验收）。"""
    grouped, _, reflection = split_material_sections(SUMMARY)
    assert "关爱与坚持" in reflection
    assert "展现教师的责任心" in reflection
    assert all(label != "正向导向" for label, _ in grouped)
    facts = [fact for _, sentences in grouped for fact in sentences]
    assert not any("关爱与坚持" in f for f in facts)


def test_place_name_list_is_reference_only() -> None:
    """地名清单是备查字段，不能混进事实句或禁止项。"""
    grouped, prohibitions, _ = split_material_sections(SUMMARY)
    assert all(label != "地名清单" for label, _ in grouped)
    assert not any("地名清单" in p for p in prohibitions)
    assert any("核心事实" == label for label, _ in grouped)


def test_reflection_ignores_template_meta_instructions() -> None:
    """采集模板里的字段说明若被模型照抄，不能混进读后思考原文。"""
    _, _, reflection = split_material_sections(
        "新闻标题：测试标题内容\n核心事实：志愿者清扫了社区街道。\n"
        "背景意义：社区环境变得更整洁了。\n"
        "正向导向：引导初一学生关心身边的人和事。此字段仅供生成读后思考使用，绝不进入阅读正文。\n"
        "地名清单：河东社区\n禁止加入内容：不得编造具体人名。\n"
    )
    assert "关心身边的人和事" in reflection
    assert "此字段仅供" not in reflection


def test_legacy_five_line_summary_still_parses() -> None:
    """存量素材是 5 行格式，没有地名清单也要能拆，且正向导向仍被剥离。"""
    grouped, prohibitions, reflection = split_material_sections(LEGACY_SUMMARY)
    assert grouped and prohibitions
    assert "责任心与奉献精神" in reflection
    assert not any("责任心与奉献精神" in f for _, s in grouped for f in s)


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
    """按素材段分配：叙事事实占前面，意义类事实落结尾段。"""
    grouped = [
        ("核心事实", ["F1", "F2", "F3"]),
        ("背景意义", ["F4", "F5"]),
        ("细节", ["F6", "F7"]),
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


def test_last_paragraph_gets_background_but_never_reflection() -> None:
    """真实六行梗概派活：末段是背景意义，全篇没有正向导向的句子。"""
    grouped, _, _ = split_material_sections(SUMMARY)
    buckets = assign_facts(grouped, 3)
    assert len(buckets) == 3
    assert any("不因天气缺课" in f for f in buckets[-1])
    flat = [f for bucket in buckets for f in bucket]
    assert not any("关爱与坚持" in f for f in flat)
    assert not any("地名清单" in f for f in flat)


def test_assign_facts_handles_fewer_facts_than_paragraphs() -> None:
    buckets = assign_facts([("核心事实", ["F1", "F2"])], 4)
    assert len(buckets) == 4
    assert sum(len(b) for b in buckets) == 2


def test_assign_facts_handles_empty_material() -> None:
    buckets = assign_facts([], 4)
    assert buckets == [[], [], [], []]


def test_assign_facts_merges_when_paragraphs_are_too_few() -> None:
    """素材段比段落还多时，多出来的并进最后一段，不能丢事实。"""
    grouped = [("核心事实", ["F1"]), ("背景意义", ["F2"]), ("细节", ["F3"])]
    buckets = assign_facts(grouped, 2)
    assert len(buckets) == 2
    flat = [f for b in buckets for f in b]
    assert flat == ["F1", "F2", "F3"]
