"""结果自检校验（PRD §2.3）。

分两层：
  1. 确定性校验（代码判定）：英文词数是否落在难度区间、中英段落数是否一致、段落数是否合理。
  2. 语义校验（LLM 二次校验）：是否编造事实、是否含敏感负面内容。
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, computed_field

_WORD_RE = re.compile(r"[A-Za-z]+(?:['\-][A-Za-z]+)*")
# 中文段落里残留的英文单词（3 个字母以上才算，避免 CCTV / AI 这类缩写误报）
_ASCII_WORD_RE = re.compile(r"[A-Za-z]{3,}")


def count_words(text: str) -> int:
    """统计英文词数：'don't' / 'well-known' 各算一个词。"""
    return len(_WORD_RE.findall(text or ""))


class ValidationReport(BaseModel):
    """自检结果（PRD §2.3）。

    这里是唯一的定义，schemas 与 generator 共用，避免出现两份同名类型对不上。
    """

    model_config = ConfigDict(extra="ignore")

    word_count: int = 0
    word_count_ok: bool = False
    no_fabrication: bool = True
    para_match: bool = True
    no_sensitive: bool = True
    issues: list[str] = Field(default_factory=list)
    #: 中文段落里是否残留未翻译的英文单词
    chinese_purity: bool = True
    #: LLM 自检自报的词数，仅作参考 —— 小模型常少算十几个词，以代码计数为准
    llm_word_count: int = 0
    #: 实际写出来的英文段落数
    para_count: int = 0
    #: 段落数是否落在难度档位的建议区间内
    para_count_ok: bool = True
    #: 是否因为超出词数上限而被裁剪过（见 app/trim.py）
    trimmed: bool = False
    #: 裁剪掉的词数
    trimmed_words: int = 0

    @computed_field  # type: ignore[prop-decorator]
    @property
    def passed(self) -> bool:
        """全部检查项都通过才算通过。序列化时会一并输出，接口方不用自己拼。"""
        return (
            self.word_count_ok
            and self.no_fabrication
            and self.para_match
            and self.no_sensitive
            and self.chinese_purity
            and self.para_count_ok
            and not self.issues
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "word_count": self.word_count,
            "word_count_ok": self.word_count_ok,
            "no_fabrication": self.no_fabrication,
            "para_match": self.para_match,
            "no_sensitive": self.no_sensitive,
            "chinese_purity": self.chinese_purity,
            "para_count": self.para_count,
            "para_count_ok": self.para_count_ok,
            "trimmed": self.trimmed,
            "trimmed_words": self.trimmed_words,
            "issues": list(self.issues),
            "llm_word_count": self.llm_word_count,
            "passed": self.passed,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ValidationReport":
        return cls.model_validate(data or {})


def deterministic_checks(
    *,
    english_paras: list[str],
    chinese_paras: list[str],
    min_words: int,
    max_words: int,
    para_range: tuple[int, int] | None = None,
) -> ValidationReport:
    """代码层面的硬校验。"""
    report = ValidationReport()
    text = "\n".join(english_paras)
    report.word_count = count_words(text)
    report.word_count_ok = min_words <= report.word_count <= max_words
    if not report.word_count_ok:
        report.issues.append(
            f"英文词数 {report.word_count} 不在难度区间 {min_words}-{max_words} 之内"
        )

    report.para_match = len(english_paras) == len(chinese_paras)
    if not report.para_match:
        report.issues.append(
            f"中英段落数不一致（英文 {len(english_paras)} 段，中文 {len(chinese_paras)} 段）"
        )

    report.para_count = len(english_paras)
    if para_range:
        low, high = para_range
        report.para_count_ok = low <= len(english_paras) <= high
        if not report.para_count_ok:
            report.issues.append(
                f"段落数 {len(english_paras)} 不在建议区间 {low}-{high} 之内"
            )

    # 中文段落里残留未翻译的英文单词
    residue: list[str] = []
    for idx, para in enumerate(chinese_paras, start=1):
        for match in _ASCII_WORD_RE.finditer(para):
            residue.append(f"第{idx}段中文残留英文单词「{match.group(0)}」")
    if residue:
        report.chinese_purity = False
        report.issues.extend(residue)

    return report


def merge_llm_check(
    base: ValidationReport,
    llm_result: dict[str, Any],
    *,
    min_words: int,
    max_words: int,
) -> ValidationReport:
    """把 LLM 二次校验结果并入确定性校验结果。

    词数以**代码计数**为准：LLM 自检自报的数字常常少算十几个词，若采信它会把
    合格稿件误判为不合格。因此 LLM 的词数只作参考记录，不参与判定。
    LLM 负责它真正擅长的三项：是否编造事实、段落是否真的互为翻译、是否含敏感内容。
    """
    llm_word_count = llm_result.get("word_count")
    if isinstance(llm_word_count, (int, float)) and int(llm_word_count) > 0:
        base.llm_word_count = int(llm_word_count)

    base.word_count_ok = min_words <= base.word_count <= max_words
    if not base.word_count_ok and not any("词数" in i for i in base.issues):
        base.issues.append(
            f"英文词数 {base.word_count} 不在难度区间 {min_words}-{max_words} 之内"
        )

    base.no_fabrication = bool(llm_result.get("no_fabrication", True))
    base.no_sensitive = bool(llm_result.get("no_sensitive", True))
    if llm_result.get("para_match") is False:
        base.para_match = False
        if not any("段落数不一致" in i for i in base.issues):
            base.issues.append("LLM 复核判定中英段落数不一致")

    if not base.no_fabrication:
        base.issues.append("LLM 复核判定存在梗概以外的编造事实")
    if not base.no_sensitive:
        base.issues.append("LLM 复核判定包含敏感或负面内容")

    for issue in llm_result.get("issues") or []:
        text = str(issue).strip()
        if not text or text in base.issues:
            continue
        # 词数相关的问题由代码判定，LLM 的词数意见不再重复计入
        low = text.lower()
        if "词数" in text or "word count" in low or "words" in low and "count" in low:
            continue
        base.issues.append(text)

    return base
