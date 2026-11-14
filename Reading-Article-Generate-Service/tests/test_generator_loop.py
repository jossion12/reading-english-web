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


def test_chinese_residue_words_are_named_in_feedback() -> None:
    """中文段落残留的英文缩写必须点名回喂，否则模型只知道「用中文写」却不知改哪个词。"""
    from app.validate import ValidationReport

    gen, _ = make_generator([make_article()])
    report = ValidationReport(
        word_count=227,
        word_count_ok=True,
        chinese_purity=False,
        issues=[
            "第1段中文残留英文单词「APEC」",
            "第2段中文残留英文单词「APEC」",
        ],
    )
    feedback = gen._rewrite_feedback(report, 180, 240, "L3")
    assert "APEC" in feedback
    # 同一个词只点一次名，别把回喂撑成噪声
    assert feedback.count("APEC") == 1


# ------------------------------------------------------------- P0 语言质量 ---
def test_language_failures_are_fed_back_with_actions() -> None:
    """判官报中式英语 / 同义反复时，回喂必须给出可执行的改写指令（R4）。"""
    from app.validate import ValidationReport

    gen, _ = make_generator([make_article()])
    report = ValidationReport(
        word_count=130,
        word_count_ok=True,
        natural_english=False,
        repetition_free=False,
        issues=[
            "LLM 复核判定存在中式英语或回译腔",
            "LLM 复核判定存在同义反复",
            "Rewrite 'new era civilization practice' in plain English.",
            "Delete this sentence: 'It is meant to lower the threshold.'",
        ],
    )
    feedback = gen._rewrite_feedback(report, 120, 180, "L2")
    assert "as a native journalist would write them" in feedback
    assert "Delete the quoted repeated sentence entirely" in feedback
    # 泛泛的判定语不该挤占具体意见的名额
    assert "LLM 复核判定存在中式英语或回译腔" not in feedback
    assert "LLM 复核判定存在同义反复" not in feedback
    # 判官引用的原句仍要回喂，模型才知道动哪一句
    assert "new era civilization practice" in feedback


def test_word_count_feedback_no_longer_permits_restatement() -> None:
    """词数不足的回喂不能再教模型「换个角度复述同一事实」。"""
    from app.validate import ValidationReport

    gen, _ = make_generator([make_article()])
    report = ValidationReport(word_count=90, word_count_ok=False, issues=["词数不足"])
    feedback = gen._rewrite_feedback(report, 120, 180, "L2")
    assert "restate the same fact from the other side" not in feedback
    assert "restate the assigned facts from another angle" not in feedback
    assert "Do NOT repeat a fact from another angle" in feedback


def make_article_with_reflection(words: int = 130, paras: int = 4) -> str:
    body = " ".join(["word"] * (words // paras))
    return json.dumps(
        {
            "title_en": "A Test Passage",
            "title_cn": "测试短文",
            "english_paras": [body] * paras,
            "chinese_paras": ["测试段落内容"] * paras,
            "reflection_en": "Small kind acts can change a day.",
            "reflection_cn": "一个小小的善举也能点亮一天。",
        }
    )


def test_preview_payload_carries_reflection() -> None:
    """R5：解析出的读后思考要一路进预览 payload，才能写进 articles。"""
    gen, _ = make_generator([make_article_with_reflection()])
    gen._llm_self_check = lambda report, **kw: report  # type: ignore[assignment]

    resp = gen.preview(request())
    assert resp.payload.reflection_en == "Small kind acts can change a day."
    assert resp.payload.reflection_cn == "一个小小的善举也能点亮一天。"
    assert gen.store.rows[0]["payload"]["reflection_en"] is not None  # type: ignore[attr-defined]


class FakeDB:
    def __init__(self) -> None:
        self.row: dict | None = None

    def insert_article(self, row: dict) -> dict:
        self.row = row
        return {"id": "article-1", **row}


class FakeStoreWithGet(FakeStore):
    def get(self, draft_id: str) -> dict | None:
        return self.rows[0] if self.rows else None

    def update(self, draft_id: str, patch: dict) -> dict:
        self.rows[0].update(patch)
        return self.rows[0]


def _draft_record(payload: dict) -> dict:
    from app.validate import ValidationReport

    return {
        "status": "preview",
        "validation": ValidationReport(word_count=130, word_count_ok=True).to_dict(),
        "payload": {
            "publish_date": "2026-11-14",
            "title_en": "T",
            "title_cn": "测试",
            "level": "L2",
            "theme": "人与社会",
            "style": "记叙文",
            "color_tag": "#E8F1FF",
            "english_paras": ["a"],
            "chinese_paras": ["甲"],
            **payload,
        },
    }


def test_commit_writes_reflection_columns() -> None:
    gen, _ = make_generator([make_article_with_reflection()])
    gen.db = FakeDB()  # type: ignore[assignment]
    gen.store = FakeStoreWithGet()  # type: ignore[assignment]
    gen.store.append(  # type: ignore[attr-defined]
        _draft_record(
            {
                "reflection_en": "Small kind acts can change a day.",
                "reflection_cn": "一个小小的善举也能点亮一天。",
            }
        )
    )

    resp = gen.commit("draft-0")
    assert resp.ok is True
    assert gen.db.row["reflection_en"] == "Small kind acts can change a day."  # type: ignore[index]
    assert gen.db.row["reflection_cn"] == "一个小小的善举也能点亮一天。"  # type: ignore[index]


def test_commit_omits_reflection_for_legacy_drafts() -> None:
    """旧草稿 / 未迁移的库没有这两列，写入时不能带空列（PostgREST 会 400）。"""
    gen, _ = make_generator([make_article()])
    gen.db = FakeDB()  # type: ignore[assignment]
    gen.store = FakeStoreWithGet()  # type: ignore[assignment]
    gen.store.append(_draft_record({}))  # type: ignore[attr-defined]

    gen.commit("draft-0")
    assert "reflection_en" not in gen.db.row  # type: ignore[operator]
    assert "reflection_cn" not in gen.db.row  # type: ignore[operator]
