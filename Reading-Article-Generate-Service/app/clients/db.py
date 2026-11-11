"""Supabase 访问层（直接走 PostgREST，避免引入额外依赖）。

写操作一律使用 service_role 键 —— 它自带 BYPASSRLS，是本服务入库的唯一通道；
anon 键只读能力保留在前端，学生端拿不到 service_role。
"""

from __future__ import annotations

from typing import Any

import httpx

from app.config import Settings


class DatabaseError(RuntimeError):
    """数据库访问失败。"""


class SupabaseClient:
    def __init__(self, settings: Settings) -> None:
        self.base_url = settings.supabase_url.rstrip("/")
        self.key = settings.supabase_service_role_key
        self.timeout = 30.0

    # --- 内部 --------------------------------------------------------------
    def _headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        if not self.key:
            raise DatabaseError(
                "未配置 SUPABASE_SERVICE_ROLE_KEY，无法访问数据库；"
                "本地栈可用 `supabase status` 查看 anon / service_role key"
            )
        headers = {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
        }
        if extra:
            headers.update(extra)
        return headers

    def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: Any | None = None,
        params: dict[str, Any] | None = None,
        prefer: str | None = None,
    ) -> Any:
        url = f"{self.base_url}/rest/v1/{path}"
        headers = self._headers({"Prefer": prefer} if prefer else None)
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.request(method, url, json=json_body, params=params, headers=headers)
                resp.raise_for_status()
                if not resp.content:
                    return None
                return resp.json()
        except httpx.HTTPStatusError as exc:
            body = exc.response.text[:800]
            raise DatabaseError(f"Supabase {method} {path} 失败 HTTP {exc.response.status_code}: {body}") from exc
        except httpx.HTTPError as exc:
            raise DatabaseError(f"无法连接 Supabase ({url}): {exc}") from exc

    # --- articles ----------------------------------------------------------
    def insert_article(self, row: dict[str, Any]) -> dict[str, Any]:
        """写入一篇文章，返回带 id 的完整行。"""
        data = self._request(
            "POST",
            "articles",
            json_body=row,
            prefer="return=representation",
        )
        if not data:
            raise DatabaseError("插入 articles 后未返回数据")
        return data[0] if isinstance(data, list) else data

    def get_article(self, article_id: str) -> dict[str, Any] | None:
        data = self._request(
            "GET",
            "articles",
            params={"id": f"eq.{article_id}", "select": "*", "limit": 1},
        )
        return data[0] if data else None

    def list_articles(
        self,
        *,
        publish_date: str | None = None,
        theme: str | None = None,
        level: str | None = None,
        style: str | None = None,
        is_published: bool | None = None,
        source_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {
            "select": "*",
            "order": "publish_date.desc,sort.asc",
            "limit": limit,
            "offset": offset,
        }
        if publish_date:
            params["publish_date"] = f"eq.{publish_date}"
        if theme:
            params["theme"] = f"eq.{theme}"
        if level:
            params["level"] = f"eq.{level}"
        if style:
            params["style"] = f"eq.{style}"
        if is_published is not None:
            params["is_published"] = f"eq.{str(is_published).lower()}"
        if source_id:
            params["source_id"] = f"eq.{source_id}"
        return self._request("GET", "articles", params=params) or []

    # --- source_log --------------------------------------------------------
    def get_source(self, source_id: str) -> dict[str, Any] | None:
        data = self._request(
            "GET",
            "source_log",
            params={"id": f"eq.{source_id}", "select": "*", "limit": 1},
        )
        return data[0] if data else None

    def list_sources(self, *, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        params = {
            "select": "*",
            "order": "create_at.desc",
            "limit": limit,
            "offset": offset,
        }
        return self._request("GET", "source_log", params=params) or []
