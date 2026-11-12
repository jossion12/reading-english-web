"""超长稿件的确定性裁剪（PRD §2.2 词数硬约束）。

为什么需要它
------------
实测（deepseek-flash，2026-11）：同一份素材下，模型写出的**总词数几乎恒定**——
素材有多少条事实，它就展开多少，长度由素材决定而不是由指令决定。
改「每段句数」「每段词数」「段落数」都改不动：把句数从区间上界钉成单值，
模型只会把句子写得更长，总字数反而上去了。

于是把「词数落在难度区间」这条 PRD 硬约束交给代码兜底：
超出上限时，从**最长的段落尾部整句裁掉**，英文与中文同步裁。

裁剪保证：
  - 段落数量不变，中英段落仍按下标一一对应（前端联动高亮不受影响）；
  - 只整句裁，不改写、不截半句，不引入任何新内容；
  - 至少保留每段一句，绝不产生空段落；
  - 少裁的是模型自己加的注水句（素材没提的重复/总结句），阅读体验反而更干净。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.validate import count_words

#: 常见缩写：这些词后面的句点不是句末，不能断句
_ABBREV = {
    "mr", "mrs", "ms", "dr", "prof", "st", "no", "vs", "etc", "fig", "inc",
    "ltd", "jr", "sr", "approx", "dept", "est", "gen", "gov", "capt", "lt",
}

_EN_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
_ZH_SPLIT_RE = re.compile(r"(?<=[。！？；])")


def _ends_with_abbrev(chunk: str) -> bool:
    """判断一段文字是否以缩写结尾（Dr. / U.S. / e.g.）。"""
    text = chunk.strip()
    match = re.search(r"([A-Za-z][A-Za-z.]*)\.$", text)
    if not match:
        return False
    token = match.group(1).lower()
    if token in _ABBREV:
        return True
    # 单字母或点号缩写（U.S. / a.m. / e.g.）
    return bool(re.fullmatch(r"(?:[a-z]\.){1,3}", token + "."))


def split_en_sentences(text: str) -> list[str]:
    """英文断句。保守：缩写后的点不当作句末。"""
    text = (text or "").strip()
    if not text:
        return []
    sentences: list[str] = []
    for chunk in _EN_SPLIT_RE.split(text):
        chunk = chunk.strip()
        if not chunk:
            continue
        if sentences and _ends_with_abbrev(sentences[-1]):
            sentences[-1] = f"{sentences[-1]} {chunk}"
        else:
            sentences.append(chunk)
    return sentences


def split_zh_sentences(text: str) -> list[str]:
    """中文断句：按句号 / 问号 / 感叹号 / 分号切，保留标点。"""
    text = (text or "").strip()
    if not text:
        return []
    parts = [p.strip() for p in _ZH_SPLIT_RE.split(text)]
    return [p for p in parts if p]


@dataclass
class TrimResult:
    """裁剪结果。"""

    english_paras: list[str]
    chinese_paras: list[str]
    words_before: int = 0
    words_after: int = 0
    removed: list[str] = field(default_factory=list)

    @property
    def trimmed(self) -> bool:
        return bool(self.removed)


def trim_to_max_words(
    english_paras: list[str],
    chinese_paras: list[str],
    max_words: int,
) -> TrimResult:
    """把英文总词数裁到 max_words 以内。

    裁剪顺序：每次从**当前最长的段落**尾部裁掉一句（该段至少剩一句才可裁），
    中英文同步裁掉各自段落末尾的一句，保证段落级一一对应不变。
    """
    en = list(english_paras)
    zh = list(chinese_paras)
    before = count_words("\n".join(en))

    if before <= max_words:
        return TrimResult(english_paras=en, chinese_paras=zh, words_before=before, words_after=before)

    removed: list[str] = []
    guard = 0
    while count_words("\n".join(en)) > max_words and guard < 200:
        guard += 1
        # 候选：还能再裁一句的段落（至少两句）
        candidates = [i for i, para in enumerate(en) if len(split_en_sentences(para)) > 1]
        if not candidates:
            break
        target = max(candidates, key=lambda i: count_words(en[i]))
        en_sentences = split_en_sentences(en[target])
        dropped = en_sentences[-1].strip()
        en[target] = " ".join(en_sentences[:-1]).strip()

        # 中文同步裁掉对应段落末尾的一句；中文只剩一句时保留，避免出现空段落
        if target < len(zh):
            zh_sentences = split_zh_sentences(zh[target])
            if len(zh_sentences) > 1:
                zh[target] = "".join(zh_sentences[:-1]).strip()
        removed.append(f"第{target + 1}段末句「{dropped[:60]}」")

    after = count_words("\n".join(en))
    return TrimResult(
        english_paras=en,
        chinese_paras=zh,
        words_before=before,
        words_after=after,
        removed=removed,
    )
