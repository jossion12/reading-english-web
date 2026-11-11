"""Reading-Material-Crawler-Service —— FastAPI 入口。

内网服务，默认只监听 127.0.0.1，不对外暴露公网。
/ 提供内置的素材库管理页面（单页，纯静态，无需额外前端工程）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.clients.crawler import CrawlClient, CrawlError, CrawlResult
from app.clients.db import DatabaseError
from app.clients.searxng import SearXNGClient, SearXNGError
from app.config import get_settings
from app.library import LibraryError, SourceLibrary
from app.pipeline.dedupe import compute_fingerprint
from app.pipeline.search import SearchPipeline
from app.pipeline.summarize import SummaryError, SummaryPipeline
from app.search_config import SearchConfigError, get_search_config
from app.store import get_store

settings = get_settings()

app = FastAPI(
    title="Reading-Material-Crawler-Service",
    description="素材采集与素材管理服务：检索 → 清洗 → 梗概 → 查重 → 入库",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:8020",
        "http://localhost:8020",
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC_DIR = Path(__file__).resolve().parent / "static"


# ====================================================================== 请求 ===
class SearchRequest(BaseModel):
    theme: str = Field(description="主题大类")
    time_range: str = Field(default="week", description="day / week / month")
    keyword: str | None = Field(default=None, description="附加关键词，会替换 Query 模板里的 {keyword}")
    max_results: int | None = Field(default=None, ge=1, le=100)


class ScoreRequest(BaseModel):
    candidates: list[dict[str, Any]] = Field(default_factory=list)


class CrawlRequest(BaseModel):
    url: str


class SummarizeRequest(BaseModel):
    url: str | None = Field(default=None, description="给 URL 则先抓取清洗")
    content: str | None = Field(default=None, description="直接给正文则跳过抓取")
    title: str | None = Field(default=None, description="原始新闻标题，用于备注")
    level: str | None = Field(default=None, description="难度，配合 fingerprint_mode=summary_level 使用")


class CreateSourceRequest(BaseModel):
    summary_text: str = Field(min_length=1)
    remark: str | None = None
    level: str | None = None
    fingerprint: str | None = None
    source_url: str | None = Field(default=None, description="来源链接，写入备注并用于查重")


class UpdateRemarkRequest(BaseModel):
    remark: str | None = None


# ==================================================================== 依赖 ===
def get_search_pipeline() -> SearchPipeline:
    return SearchPipeline()


def get_summary_pipeline() -> SummaryPipeline:
    return SummaryPipeline()


def get_crawl_client() -> CrawlClient:
    return CrawlClient()


def get_library() -> SourceLibrary:
    return SourceLibrary()


# ================================================================== 基础信息 ===
@app.get("/health")
async def health() -> dict[str, Any]:
    from app.config import _env_file_name

    searx = await SearXNGClient().health()
    return {
        "ok": True,
        "service": "reading-material-crawler-service",
        "env_file": _env_file_name(),
        "llm_provider": settings.llm_provider,
        "llm_model": settings.llm_model,
        "crawler_mode": settings.crawler_mode,
        "searxng": searx,
        "supabase_url": settings.supabase_url,
    }


@app.get("/api/v1/config")
def read_config() -> dict[str, Any]:
    """检索配置：主题、Query 模板、时间范围、白名单、黑名单。"""
    cfg = get_search_config()
    return {
        "themes": cfg.themes,
        "time_ranges": cfg.time_ranges,
        "domain_whitelist": cfg.domain_whitelist,
        "blacklist_keywords": cfg.blacklist_keywords,
        "filters": cfg.filters,
        "rss_sources": cfg.rss_sources,
        "fingerprint_mode": settings.fingerprint_mode,
    }


# ====================================================================== 检索 ===
@app.post("/api/v1/search")
async def search(req: SearchRequest, pipeline: SearchPipeline = Depends(get_search_pipeline)):
    """按主题检索候选新闻（PRD §2.1 / §2.2）。"""
    try:
        outcome = await pipeline.run(
            theme=req.theme,
            time_range=req.time_range,
            keyword=req.keyword,
            max_results=req.max_results,
        )
    except SearchConfigError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    get_store().append(
        "search",
        theme=req.theme,
        time_range=req.time_range,
        keyword=req.keyword,
        queries=outcome.queries,
        candidate_count=len(outcome.candidates),
        dropped=outcome.dropped,
        errors=outcome.errors,
        sources_used=outcome.sources_used,
        fallback_used=outcome.fallback_used,
    )
    return outcome.to_dict()


@app.post("/api/v1/score")
async def score(req: ScoreRequest, pipeline: SummaryPipeline = Depends(get_summary_pipeline)):
    """全自动打分模式（PRD §2.3 预留扩展）。"""
    try:
        scores = await pipeline.score_candidates(req.candidates)
    except SummaryError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"scores": scores}


# ====================================================================== 清洗 ===
@app.post("/api/v1/crawl")
async def crawl(req: CrawlRequest, client: CrawlClient = Depends(get_crawl_client)):
    """Crawl4AI 网页清洗，输出纯净 Markdown 正文（PRD §2.4）。"""
    result = await client.crawl(req.url)
    get_store().append(
        "crawl",
        url=req.url,
        status=result.status,
        engine=result.engine,
        content_length=result.content_length,
        error=result.error,
    )
    if result.status == "failed":
        raise HTTPException(status_code=502, detail=result.error or "抓取失败")
    return {
        "url": result.url,
        "markdown": result.markdown,
        "engine": result.engine,
        "status": result.status,
        "content_length": result.content_length,
        "error": result.error,
    }


# ================================================================== 梗概/查重 ===
@app.post("/api/v1/summarize")
async def summarize(
    req: SummarizeRequest,
    summary_pipeline: SummaryPipeline = Depends(get_summary_pipeline),
    crawl_client: CrawlClient = Depends(get_crawl_client),
    library: SourceLibrary = Depends(get_library),
):
    """LLM 标准化梗概提炼 + 查重（PRD §2.5 / §2.6）。返回预览，不入库。"""
    content = (req.content or "").strip()
    engine = "direct"
    crawl_error: str | None = None

    if not content:
        if not req.url:
            raise HTTPException(status_code=422, detail="需要 url 或 content 之一")
        result: CrawlResult = await crawl_client.crawl(req.url)
        if result.status == "failed":
            raise HTTPException(status_code=502, detail=result.error or "抓取失败")
        if result.status == "too_short":
            raise HTTPException(status_code=422, detail=result.error or "正文过短，已丢弃")
        content = result.markdown
        engine = result.engine

    try:
        material = await summary_pipeline.summarize(content)
    except SummaryError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    fingerprint = compute_fingerprint(
        material.to_text(), mode=settings.fingerprint_mode, level=req.level
    )
    try:
        existing = await library.find_by_fingerprint(fingerprint)
        duplicate_reason: str | None = "fingerprint" if existing else None
        if not existing and req.url:
            # 同一篇报道二次抓取：两次 LLM 提炼的梗概文字有细微差异，指纹不同，
            # 这时按来源链接再判一次，避免同一篇报道被收进素材库两遍。
            dup_url = await library.find_by_url(req.url)
            if dup_url:
                existing = dup_url
                duplicate_reason = "url"
    except LibraryError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    get_store().append(
        "dedupe",
        url=req.url,
        fingerprint=fingerprint,
        duplicated=bool(existing),
        duplicate_reason=duplicate_reason,
        existing_id=(existing or {}).get("id"),
    )

    return {
        "summary": material.to_dict(),
        "fingerprint": fingerprint,
        "fingerprint_mode": settings.fingerprint_mode,
        "duplicated": bool(existing),
        "duplicate_reason": duplicate_reason,
        "existing": existing,
        "url": req.url,
        "crawl_engine": engine,
        "crawl_error": crawl_error,
    }


# ==================================================================== 素材库 ===
sources_router = APIRouter(prefix="/api/v1/sources", tags=["素材库"])


@sources_router.get("")
async def list_sources(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    library: SourceLibrary = Depends(get_library),
):
    try:
        rows = await library.list(limit=limit, offset=offset)
    except LibraryError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return rows


@sources_router.post("")
async def create_source(
    req: CreateSourceRequest,
    library: SourceLibrary = Depends(get_library),
):
    """确认入库（PRD §2.6）。命中重复则阻断。"""
    try:
        row = await library.create(
            summary_text=req.summary_text,
            remark=req.remark,
            level=req.level,
            fingerprint=req.fingerprint,
            source_url=req.source_url,
        )
    except LibraryError as exc:
        message = str(exc)
        status = 409 if "已存在" in message else 502
        raise HTTPException(status_code=status, detail=message) from exc

    get_store().append("insert_source", source_id=row.get("id"), remark=req.remark)
    return row


@sources_router.get("/{source_id}")
async def get_source(source_id: str, library: SourceLibrary = Depends(get_library)):
    try:
        row = await library.get(source_id)
    except LibraryError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if row is None:
        raise HTTPException(status_code=404, detail="素材不存在")
    return row


@sources_router.get("/{source_id}/articles")
async def related_articles(source_id: str, library: SourceLibrary = Depends(get_library)):
    """关联跳转：查看该素材已经生成的阅读文章（PRD §2.7）。"""
    try:
        return await library.related_articles(source_id)
    except LibraryError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@sources_router.patch("/{source_id}")
async def update_source(
    source_id: str,
    req: UpdateRemarkRequest,
    library: SourceLibrary = Depends(get_library),
):
    """修改备注信息（PRD §2.7）。"""
    try:
        row = await library.update_remark(source_id, req.remark)
    except LibraryError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if row is None:
        raise HTTPException(status_code=404, detail="素材不存在")
    get_store().append("update_source", source_id=source_id, remark=req.remark)
    return row


@sources_router.delete("/{source_id}")
async def delete_source(source_id: str, library: SourceLibrary = Depends(get_library)):
    """删除素材记录（PRD §2.7）。已生成文章会保留，source_id 置空。"""
    try:
        ok = await library.delete(source_id)
    except LibraryError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if not ok:
        raise HTTPException(status_code=404, detail="素材不存在")
    get_store().append("delete_source", source_id=source_id)
    return {"ok": True, "id": source_id}


app.include_router(sources_router)


# ====================================================================== 日志 ===
@app.get("/api/v1/logs")
def list_logs(
    limit: int = Query(default=100, ge=1, le=500),
    event: str | None = None,
):
    """运行日志：搜索记录、抓取 URL、查重结果、入库操作（PRD §4.4）。"""
    return get_store().list(limit=limit, event=event)


# ============================================================== 管理页面 ===
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
def index() -> FileResponse:
    """内置素材库管理页面。"""
    page = STATIC_DIR / "index.html"
    if not page.exists():
        raise HTTPException(status_code=404, detail="管理页面缺失")
    return FileResponse(page)


@app.get("/favicon.ico")
def favicon() -> FileResponse:
    icon = STATIC_DIR / "favicon.svg"
    if icon.exists():
        return FileResponse(icon, media_type="image/svg+xml")
    raise HTTPException(status_code=404, detail="not found")
