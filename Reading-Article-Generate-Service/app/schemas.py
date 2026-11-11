"""请求 / 响应模型。"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.validate import ValidationReport

Level = Literal["L1", "L2", "L3"]


class GenerateRequest(BaseModel):
    """语篇生成入参（PRD §2.1）。"""

    source_id: str | None = Field(default=None, description="素材 id，常青素材可为 null")
    summary: str = Field(default="", description="标准化素材梗概文本；常青模式可为空")
    level: Level = Field(description="难度 L1 / L2 / L3")
    style: str = Field(description="文体：记叙文 / 说明文 / 应用文 / 议论文")
    theme: str = Field(description="主题大类")
    sub_theme: str = Field(default="", description="子话题")
    color_tag: str = Field(default="#E8F1FF", description="标签色值 #xxxxxx")
    publish_date: date | None = Field(default=None, description="发布日期，默认今天")
    sort: int = Field(default=0, description="同日期文章排序序号")
    is_published: bool = Field(default=False, description="是否上线")
    evergreen: bool = Field(default=False, description="常青素材模式：不依赖梗概")
    title_en: str | None = Field(default=None, description="可选：指定英文标题")
    title_cn: str | None = Field(default=None, description="可选：指定中文标题")

    @field_validator("color_tag")
    @classmethod
    def _check_color(cls, value: str) -> str:
        value = (value or "").strip()
        if not value.startswith("#") or len(value) != 7:
            raise ValueError("color_tag 必须是 #xxxxxx 形式的色值")
        int(value[1:], 16)
        return value.upper()

    @field_validator("style")
    @classmethod
    def _check_style(cls, value: str) -> str:
        value = (value or "").strip()
        if not value:
            raise ValueError("style 不能为空")
        return value

    @field_validator("theme")
    @classmethod
    def _check_theme(cls, value: str) -> str:
        value = (value or "").strip()
        if not value:
            raise ValueError("theme 不能为空")
        return value


class ArticlePayload(BaseModel):
    """结构化后的文章内容（PRD §2.4）。"""

    title_en: str
    title_cn: str
    english_paras: list[str]
    chinese_paras: list[str]
    level: Level
    theme: str
    sub_theme: str = ""
    style: str
    color_tag: str
    publish_date: date
    sort: int = 0
    is_published: bool = False
    source_id: str | None = None


class PreviewResponse(BaseModel):
    """预览接口返回（PRD §2.5）。"""

    draft_id: str
    payload: ArticlePayload
    validation: ValidationReport
    ready_to_commit: bool
    llm_raw: str = Field(default="", description="LLM 原始返回内容")
    created_at: datetime


class CommitRequest(BaseModel):
    draft_id: str = Field(description="预览接口返回的草稿 id")
    force: bool = Field(default=False, description="自检未通过时强制入库")


class CommitResponse(BaseModel):
    ok: bool
    article_id: str | None = None
    message: str
    article: dict[str, Any] | None = None


class GenerationLogEntry(BaseModel):
    id: str
    created_at: datetime
    status: Literal["preview", "committed", "failed"]
    level: str
    style: str
    theme: str
    sub_theme: str
    source_id: str | None
    publish_date: str | None
    summary: str
    llm_raw: str
    validation: dict[str, Any]
    article_id: str | None
    error: str | None = None


class TaxonomyMeta(BaseModel):
    levels: dict[str, Any]
    styles: dict[str, Any]
    themes: dict[str, Any]
