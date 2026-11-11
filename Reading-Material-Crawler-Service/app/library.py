"""素材库管理（PRD §2.7）：列表 / 编辑备注 / 删除 / 关联文章跳转。"""

from __future__ import annotations

from typing import Any

from app.clients.db import DatabaseError, SupabaseClient
from app.config import Settings, get_settings
from app.pipeline.dedupe import compute_fingerprint, extract_source_url


class LibraryError(RuntimeError):
    """素材库操作失败。"""


class SourceLibrary:
    def __init__(self, db: SupabaseClient | None = None, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.db = db or SupabaseClient(self.settings)

    async def list(self, *, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        try:
            return await self.db.list_sources(limit=limit, offset=offset)
        except DatabaseError as exc:
            raise LibraryError(str(exc)) from exc

    async def get(self, source_id: str) -> dict[str, Any] | None:
        try:
            return await self.db.get_source(source_id)
        except DatabaseError as exc:
            raise LibraryError(str(exc)) from exc

    async def related_articles(self, source_id: str) -> list[dict[str, Any]]:
        """关联跳转：查看该素材已经生成的阅读文章。"""
        try:
            return await self.db.list_articles_by_source(source_id)
        except DatabaseError as exc:
            raise LibraryError(str(exc)) from exc

    async def update_remark(self, source_id: str, remark: str | None) -> dict[str, Any] | None:
        try:
            return await self.db.update_source(source_id, {"remark": remark})
        except DatabaseError as exc:
            raise LibraryError(str(exc)) from exc

    async def delete(self, source_id: str) -> bool:
        """删除素材记录。articles.source_id 为 SET NULL 外键，已生成的文章不会丢。"""
        try:
            return await self.db.delete_source(source_id)
        except DatabaseError as exc:
            raise LibraryError(str(exc)) from exc

    async def find_by_fingerprint(self, fingerprint: str) -> dict[str, Any] | None:
        try:
            return await self.db.find_source_by_fingerprint(fingerprint)
        except DatabaseError as exc:
            raise LibraryError(str(exc)) from exc

    async def find_by_url(self, url: str) -> dict[str, Any] | None:
        try:
            return await self.db.find_source_by_url(url)
        except DatabaseError as exc:
            raise LibraryError(str(exc)) from exc

    async def create(
        self,
        *,
        summary_text: str,
        remark: str | None = None,
        level: str | None = None,
        fingerprint: str | None = None,
        source_url: str | None = None,
    ) -> dict[str, Any]:
        """入库素材。命中重复则拒绝（PRD §2.6）。

        两重判据：
        1. 梗概指纹（sha256）——同一份梗概重复入库；
        2. 来源链接 ——同一篇报道被二次抓取时，LLM 两次提炼的梗概文字会有
           细微差异，指纹不同但链接相同，靠这一重兜住。
        """
        fp = fingerprint or compute_fingerprint(
            summary_text, mode=self.settings.fingerprint_mode, level=level
        )
        existing = await self.find_by_fingerprint(fp)
        if existing:
            raise LibraryError(f"素材已存在（指纹 {fp[:12]}…，素材 id {existing.get('id')}）")

        note = (remark or "").strip()
        url = extract_source_url(note) or extract_source_url(source_url or "")
        if url:
            dup = await self.find_by_url(url)
            if dup:
                raise LibraryError(
                    f"素材已存在（来源链接重复：{url}，素材 id {dup.get('id')}）"
                )
            if not extract_source_url(note):
                # 备注里没有链接时补上，保证后续按链接查重能命中（PRD §2.7）
                note = f"{note} · {url}" if note else url

        row = {
            "source_fingerprint": fp,
            "source_summary": summary_text,
            "remark": note or None,
        }
        try:
            inserted = await self.db.insert_source(row)
        except DatabaseError as exc:
            raise LibraryError(str(exc)) from exc
        return inserted
