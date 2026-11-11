"""Supabase 访问层（直接走 PostgREST，异步）。

素材库写操作统一走 service_role 键（自带 BYPASSRLS）。
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

import httpx

from app.config import Settings
from app.pipeline.dedupe import extract_source_url, normalize_url


class DatabaseError(RuntimeError):
    """数据库访问失败。"""


class SupabaseClient:
    def __init__(self, settings: Settings) -> None:
        self.base_url = settings.supabase_url.rstrip("/")
        self.key = settings.supabase_service_role_key
        self.timeout = 30.0

    def _headers(self, prefer: str | None = None) -> dict[str, str]:
        if not self.key:
            raise DatabaseError(
                "未配置 SUPABASE_SERVICE_ROLE_KEY，无法访问数据库；"
                "本地栈可用 `supabase status` 查看 key"
            )
        headers = {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
        }
        if prefer:
            headers["Prefer"] = prefer
        return headers

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: Any | None = None,
        params: dict[str, Any] | None = None,
        prefer: str | None = None,
    ) -> Any:
        url = f"{self.base_url}/rest/v1/{path}"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.request(method, url, json=json_body, params=params, headers=self._headers(prefer))
                resp.raise_for_status()
                if not resp.content:
                    return None
                return resp.json()
        except httpx.HTTPStatusError as exc:
            raise DatabaseError(f"Supabase {method} {path} 失败 HTTP {exc.response.status_code}: {exc.response.text[:800]}") from exc
        except httpx.HTTPError as exc:
            raise DatabaseError(f"无法连接 Supabase ({url}): {exc}") from exc

    # --- source_log --------------------------------------------------------
    async def insert_source(self, row: dict[str, Any]) -> dict[str, Any]:
        data = await self._request("POST", "source_log", json_body=row, prefer="return=representation")
        if not data:
            raise DatabaseError("插入 source_log 后未返回数据")
        return data[0] if isinstance(data, list) else data

    async def get_source(self, source_id: str) -> dict[str, Any] | None:
        data = await self._request(
            "GET", "source_log", params={"id": f"eq.{source_id}", "select": "*", "limit": 1}
        )
        return data[0] if data else None

    async def find_source_by_fingerprint(self, fingerprint: str) -> dict[str, Any] | None:
        data = await self._request(
            "GET",
            "source_log",
            params={"source_fingerprint": f"eq.{fingerprint}", "select": "*", "limit": 1},
        )
        return data[0] if data else None

    async def find_source_by_url(self, url: str) -> dict[str, Any] | None:
        """按来源链接查重（指纹之外的第二重判据）。

        来源链接存在备注里（PRD §2.7），文本列没法直接等值查询，
        所以先用主机名做粗筛，再在 Python 里比对归一化后的完整链接。
        """
        try:
            host = (urlsplit(url).hostname or "").lower()
        except ValueError:
            return None
        if not host:
            return None

        data = await self._request(
            "GET",
            "source_log",
            params={
                "remark": f"like.*{host}*",
                "select": "id,source_fingerprint,remark",
                "limit": 200,
            },
        )
        target = normalize_url(url)
        for row in data or []:
            other = extract_source_url(row.get("remark") or "")
            if other and normalize_url(other) == target:
                return row
        return None

    async def list_sources(self, *, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        data = await self._request(
            "GET",
            "source_log",
            params={"select": "*", "order": "create_at.desc", "limit": limit, "offset": offset},
        )
        return data or []

    async def update_source(self, source_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
        data = await self._request(
            "PATCH",
            "source_log",
            json_body=patch,
            params={"id": f"eq.{source_id}"},
            prefer="return=representation",
        )
        return data[0] if data else None

    async def delete_source(self, source_id: str) -> bool:
        data = await self._request("DELETE", "source_log", params={"id": f"eq.{source_id}", "select": "id"})
        return bool(data)

    # --- articles（关联跳转用）--------------------------------------------
    async def list_articles_by_source(self, source_id: str) -> list[dict[str, Any]]:
        data = await self._request(
            "GET",
            "articles",
            params={"source_id": f"eq.{source_id}", "select": "*", "order": "publish_date.desc"},
        )
        return data or []
