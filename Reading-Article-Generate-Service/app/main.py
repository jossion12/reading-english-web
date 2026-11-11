"""Reading-Article-Generate-Service —— FastAPI 入口。

内网服务，默认只监听 127.0.0.1（见 .env 的 SERVICE_HOST），不对外暴露公网。
"""

from __future__ import annotations

from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from app.clients.db import DatabaseError
from app.config import get_settings
from app.generator import ArticleGenerator, GenerationError, get_generator
from app.prompts import get_prompts
from app.schemas import (
    CommitRequest,
    CommitResponse,
    GenerateRequest,
    GenerationLogEntry,
    PreviewResponse,
)
from app.store import get_store

settings = get_settings()

app = FastAPI(
    title="Reading-Article-Generate-Service",
    description="语篇生成服务：素材梗概 → 中英双语泛读短文 → 自检 → 预览 → 入库",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:4173",
        "http://localhost:4173",
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(GenerationError)
async def _generation_error_handler(_request, exc: GenerationError):  # type: ignore[no-untyped-def]
    from fastapi.responses import JSONResponse

    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.message, "detail": exc.detail},
    )


# ---------------------------------------------------------------- 基础信息 ---
@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "service": "reading-article-generate-service",
        "llm_provider": settings.llm_provider,
        "llm_model": settings.llm_model,
        "supabase_url": settings.supabase_url,
    }


@app.get("/api/v1/meta")
def meta() -> dict[str, Any]:
    """分类元信息：难度 / 文体 / 主题 / 子话题 / 默认标签色。"""
    return get_prompts().taxonomy_meta()


# ------------------------------------------------------------------- 生成 ---
@app.post("/api/v1/generate/preview", response_model=PreviewResponse)
def generate_preview(req: GenerateRequest, generator: ArticleGenerator = Depends(get_generator)):
    """生成预览：只产出草稿与自检报告，不写数据库（PRD §2.5）。"""
    return generator.preview(req)


@app.post("/api/v1/generate/commit", response_model=CommitResponse)
def generate_commit(req: CommitRequest, generator: ArticleGenerator = Depends(get_generator)):
    """确认入库：把预览草稿写入 articles 表（PRD §2.5）。"""
    return generator.commit(req.draft_id, req.force)


# ------------------------------------------------------------------- 日志 ---
@app.get("/api/v1/generation-logs", response_model=list[GenerationLogEntry])
def list_logs(
    limit: int = Query(default=20, ge=1, le=200),
    status: str | None = Query(default=None, pattern="^(preview|committed|failed)$"),
):
    """生成日志：入参梗概、LLM 原始返回、入库状态、生成时间（PRD §2.6）。"""
    rows = get_store().list(limit=limit, status=status)
    return [GenerationLogEntry(**{k: v for k, v in row.items() if k in GenerationLogEntry.model_fields}) for row in rows]


# ----------------------------------------------------------------- 文章 ----
@app.get("/api/v1/articles")
def list_articles(
    publish_date: str | None = None,
    theme: str | None = None,
    level: str | None = None,
    style: str | None = None,
    is_published: bool | None = None,
    source_id: str | None = None,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    generator: ArticleGenerator = Depends(get_generator),
):
    """管理端查看 articles（走 service_role，可见未发布草稿）。"""
    try:
        return generator.db.list_articles(
            publish_date=publish_date,
            theme=theme,
            level=level,
            style=style,
            is_published=is_published,
            source_id=source_id,
            limit=limit,
            offset=offset,
        )
    except DatabaseError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/api/v1/articles/{article_id}")
def get_article(article_id: str, generator: ArticleGenerator = Depends(get_generator)):
    try:
        row = generator.db.get_article(article_id)
    except DatabaseError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if row is None:
        raise HTTPException(status_code=404, detail="文章不存在")
    return row
