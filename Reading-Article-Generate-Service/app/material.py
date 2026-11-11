"""素材梗概解析：把五段式梗概拆成「事实句」与「禁止项」。

采集服务产出的梗概是带标签的分段文本，例如：

    新闻标题：贵州山区女教师雨雪天徒步翻山到学生家中家访
    核心事实：贵州省黔东南某山区小学教师李雨在暴雪天气独自徒步三小时，
               翻越两座山头，到学生家中进行家访并送上课本。
    背景意义：乡村教育工作者在恶劣天气下仍坚持家访，保障了偏远山区学生不因天气缺课。
    正向导向：展现教师的责任心与奉献精神，引导学生理解什么是真正的关爱与坚持。
    禁止加入内容：不得编造教师姓名、学校名称、受访学生家庭细节……

为什么要拆：一条梗概真正能支撑的事实只有 7~8 条，而 L2 要求 4 段 × 4~5 句
（16~20 句）。差额只能靠编造填满 —— 实测模型正是这么干的
（凭空造出「学生需要帮助」「她从学校出发」）。把事实摊开、并按段落派活，
模型就有了明确且有限的活儿，编造率明显下降。
"""

from __future__ import annotations

import re

#: 梗概里承载事实的段落标签
FACT_SECTIONS = ("核心事实", "背景意义", "正向导向", "主题", "细节", "正文")

#: 标题类标签 —— 标题是压缩过的标题句，不进事实清单（容易诱导模型造名字）
TITLE_SECTIONS = ("新闻标题", "标题")

#: 禁止项标签 —— 采集时给出的「不许写什么」，原样传给扩写模型
PROHIBIT_SECTIONS = ("禁止加入内容", "禁止内容", "注意事项")

#: 句子切分（中英文标点都算）
_SENT_SPLIT = re.compile(r"[。！？；!?;\n]+")

#: 事实句的细切分：中文摘要里一个「。」句常含多个并列事实
_FACT_SPLIT = re.compile(r"[。！？；，,!?;\n]+")

#: 「标签：正文」的形式
_LABEL = re.compile(r"^\s*([^：:]{2,12})\s*[：:]\s*(.*)$")

#: 太短的碎片当不了事实（「翻过两座山」只有 5 个字，也是有效事实，不能丢）
_MIN_FACT_LEN = 5


def split_material_sections(summary: str) -> tuple[list[tuple[str, list[str]]], list[str]]:
    """把梗概按段拆开，返回 (每段的 (标签, 事实句), 禁止项)。

    事实句保留中文原文（模型读中文更准），不做翻译。
    """
    sections: list[tuple[str, str]] = []
    for raw_line in (summary or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = _LABEL.match(line)
        label = match.group(1).strip() if match else ""
        if label in FACT_SECTIONS or label in TITLE_SECTIONS or label in PROHIBIT_SECTIONS:
            sections.append((label, match.group(2).strip()))
        elif sections:
            prev_label, prev_body = sections[-1]
            sections[-1] = (prev_label, f"{prev_body}\n{line}")
        else:
            sections.append(("正文", line))

    grouped: list[tuple[str, list[str]]] = []
    prohibitions: list[str] = []
    for label, body in sections:
        if label in PROHIBIT_SECTIONS:
            # 禁止项按整句保留：切碎会丢掉「不得编造…」的限定词
            sentences = [s.strip(" ，,、") for s in _SENT_SPLIT.split(body) if s and s.strip()]
            prohibitions.extend(s for s in sentences if len(s) >= _MIN_FACT_LEN)
            continue
        sentences = [s.strip(" ，,、") for s in _FACT_SPLIT.split(body) if s and s.strip()]
        sentences = [s for s in sentences if len(s) >= _MIN_FACT_LEN]
        if label in TITLE_SECTIONS:
            continue
        if sentences:
            grouped.append((label, sentences))
    return grouped, prohibitions


def split_material(summary: str) -> tuple[list[str], list[str]]:
    """把梗概拆成 (事实句列表, 禁止项列表)。"""
    grouped, prohibitions = split_material_sections(summary)
    facts: list[str] = []
    for _, sentences in grouped:
        facts.extend(sentences)
    return facts, prohibitions


def assign_facts(grouped: list[tuple[str, list[str]]], para_count: int) -> list[list[str]]:
    """把事实摊到各段落上，返回每段对应的事实句。

    素材的段落顺序本身就是叙事顺序（核心事实 → 背景意义 → 正向导向），
    所以按段分配：叙事事实占前面的段落，意义类事实自然落到结尾段。
    """
    if para_count <= 0:
        return []
    buckets: list[list[str]] = [[] for _ in range(para_count)]
    blocks = [(label, facts) for label, facts in grouped if facts]
    if not blocks:
        return buckets

    total = sum(len(f) for _, f in blocks)
    # 段落数不够分（段落数 ≤ 素材段数）：每段事实占一个段落，多出来的并进最后一段
    if len(blocks) >= para_count:
        for i, (_, facts) in enumerate(blocks):
            if i < para_count:
                buckets[i].extend(facts)
            else:
                buckets[-1].extend(facts)
        return buckets

    # 按事实数比例分配段落数，最大余数法保证总数正好等于 para_count
    exact = [len(f) / total * para_count for _, f in blocks]
    alloc = [max(1, int(r)) for r in exact]
    while sum(alloc) > para_count:
        i = max(range(len(alloc)), key=lambda k: (alloc[k], -k))
        alloc[i] -= 1
    while sum(alloc) < para_count:
        i = min(range(len(alloc)), key=lambda k: (alloc[k], k))
        alloc[i] += 1

    # 每个素材段内部再均分事实
    para_cursor = 0
    for (_, facts), n_para in zip(blocks, alloc):
        base, extra = divmod(len(facts), n_para)
        fact_cursor = 0
        for k in range(n_para):
            take = base + (1 if k < extra else 0)
            buckets[para_cursor + k].extend(facts[fact_cursor : fact_cursor + take])
            fact_cursor += take
        para_cursor += n_para
    return buckets
