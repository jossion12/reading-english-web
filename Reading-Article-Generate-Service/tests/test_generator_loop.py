"""生成循环的单元测试：假 LLM 驱动，验证重试与选优逻辑（不触网）。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.generator import ArticleGenerator, GenerationError
from app.schemas import GenerateRequest


class FakeLLM:
    """假 LLM：按顺序返回预设字符串，并记录收到的 user prompt。"""

    def __init__(self, replies: list[str]) -> None:
        self.replies = replies
        self.prompts: list[str] = []

    def chat_json(self, system: str, user: str, *, temperature: float | None = None) -> str:
        self.prompts.append(user)
        return self.replies[min(len(self.prompts) - 1, len(self.replies) - 1)]


def make_article(words: int = 130, paras: int = 4) -> str:
    body = " ".join(["word"] * (words // paras))
    return json.dumps(
        {
            "title_en": "A Test Passage",
            "title_cn": "测试短文",
            "english_paras": [body] * paras,
            "chinese_paras": ["测试段落内容"] * paras,
        }
    )


class FakeStore:
    """假日志存储：只记录，不落盘。"""

    def __init__(self) -> None:
        self.rows: list[dict] = []

    def append(self, record: dict) -> dict:
        record = {
            "id": f"draft-{len(self.rows)}",
            "created_at": "2026-11-11T00:00:00+00:00",
            **record,
        }
        self.rows.append(record)
        return record


def make_generator(replies: list[str]) -> tuple[ArticleGenerator, FakeLLM]:
    llm = FakeLLM(replies)
    gen = ArticleGenerator.__new__(ArticleGenerator)
    from app.config import get_settings
    from app.prompts import get_prompts

    gen.settings = get_settings()
    gen.llm = llm
    gen.prompts = get_prompts()
    gen.db = None
    gen.store = FakeStore()
    return gen, llm


def request() -> GenerateRequest:
    return GenerateRequest(
        summary="一段梗概：老师雪天家访学生。",
        level="L2",
        style="记叙文",
        theme="人与社会",
        sub_theme="邻里互助",
        evergreen=False,
    )


def test_malformed_json_is_retried_not_fatal() -> None:
    """模型偶尔吐残缺 JSON —— 第一轮解析失败不能直接判死整次请求。"""
    gen, llm = make_generator(
        [
            '{"title_en": "broken", "title_en": "x"}',  # 缺 chinese_paras
            make_article(130),
        ]
    )
    # 伪造自检：只跑生成逻辑，_llm_self_check 用假实现
    gen._llm_self_check = lambda report, **kw: report  # type: ignore[assignment]

    resp = gen.preview(request())

    assert resp.validation.word_count > 0
    assert len(llm.prompts) == 2
    # 第二轮的 prompt 里要带上「解析失败」的可执行反馈
    assert "could not be parsed" in llm.prompts[1]


def test_all_rounds_malformed_raises_clear_error() -> None:
    """所有轮次都解析不了才报错，且错误信息要可读。"""
    gen, llm = make_generator(['{"title_en": "broken"}'])
    gen._llm_self_check = lambda report, **kw: report  # type: ignore[assignment]

    with pytest.raises(GenerationError) as excinfo:
        gen.preview(request())

    assert "解析失败" in str(excinfo.value)
    assert len(llm.prompts) == ArticleGenerator.MAX_REWRITE + 1


def test_rewrite_feedback_names_paragraph_and_sentence_counts() -> None:
    """回喂必须点名「你写了 N 段」和「每段几句」，否则小模型改不对。"""
    gen, _ = make_generator([make_article()])
    gen._llm_self_check = lambda report, **kw: report  # type: ignore[assignment]

    gen.llm.replies = [make_article(words=60, paras=2)]  # 段数与词数都不合格
    resp = gen.preview(request())

    # 第二次请求就是回喂
    feedback = gen.llm.prompts[1]
    assert "You wrote 2 paragraphs" in feedback
    assert "sentences in EACH English paragraph" in feedback
    assert "words short" in feedback
    assert resp.validation.para_count == 2
    assert resp.validation.para_count_ok is False


def test_fabrication_judgement_is_fed_back_to_the_model() -> None:
    """判官指出的具体编造点必须原样回喂，否则模型不知道该改哪句。"""
    from app.validate import ValidationReport

    gen, _ = make_generator([make_article()])
    report = ValidationReport(
        word_count=130,
        word_count_ok=True,
        no_fabrication=False,
        issues=[
            "LLM 复核判定存在梗概以外的编造事实",
            "The Chinese paragraph adds '风雨' although the material only says '暴雪'.",
        ],
    )
    feedback = gen._rewrite_feedback(report, 120, 180, "L2")
    assert "The Chinese paragraph adds '风雨'" in feedback
    # 泛泛的判定语不该挤占具体意见的名额
    assert "LLM 复核判定存在梗概以外的编造事实" not in feedback
