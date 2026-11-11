"""SearXNG 元搜索客户端（PRD §2.2）。

特性：
  · 只走本地实例，JSON 接口（需在 searxng settings.yml 的 formats 里包含 json）
  · 内置限流：串行调用 + 最小调用间隔，禁止并发（PRD §4.2）
  · 失败不阻塞主流程，抛出可读错误由上层兜底（PRD §4.5）
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.config import Settings, get_settings


class SearXNGError(RuntimeError):
    """SearXNG 调用失败。"""


@dataclass
class RawResult:
    """一条搜索结果。"""

    title: str
    url: str
    content: str = ""
    engine: str = ""
    published_date: str | None = None
    category: str | None = None
    score: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


class SearXNGClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._lock = asyncio.Lock()
        self._last_call = 0.0

    async def _throttle(self) -> None:
        gap = time.monotonic() - self._last_call
        if gap < self.settings.searxng_min_interval:
            await asyncio.sleep(self.settings.searxng_min_interval - gap)
        self._last_call = time.monotonic()

    async def search(
        self,
        query: str,
        *,
        time_range: str | None = None,
        categories: str | None = None,
        language: str | None = None,
    ) -> list[RawResult]:
        """执行一次元搜索，返回原始结果列表。"""
        params: dict[str, str] = {
            "q": query,
            "format": "json",
            "categories": categories or self.settings.searxng_categories,
            "language": language or self.settings.searxng_language,
        }
        if time_range:
            params["time_range"] = time_range

        url = f"{self.settings.searxng_base_url.rstrip('/')}/search"
        async with self._lock:  # 串行 + 间隔，杜绝并发抓取
            await self._throttle()
            try:
                async with httpx.AsyncClient(timeout=self.settings.searxng_timeout) as client:
                    resp = await client.get(url, params=params, headers={"Accept": "application/json"})
            except httpx.HTTPError as exc:
                raise SearXNGError(f"无法连接 SearXNG ({url}): {exc}") from exc

        if resp.status_code == 403:
            raise SearXNGError(
                "SearXNG 拒绝 JSON 请求（HTTP 403）。请在 searxng settings.yml 的 "
                "`formats:` 中加入 `json` 后重启实例。"
            )
        if resp.status_code != 200:
            raise SearXNGError(f"SearXNG 返回 HTTP {resp.status_code}: {resp.text[:300]}")

        try:
            data = resp.json()
        except ValueError as exc:
            raise SearXNGError(f"SearXNG 返回的不是 JSON: {resp.text[:300]}") from exc

        results: list[RawResult] = []
        for item in data.get("results") or []:
            if not isinstance(item, dict):
                continue
            results.append(
                RawResult(
                    title=str(item.get("title") or "").strip(),
                    url=str(item.get("url") or "").strip(),
                    content=str(item.get("content") or "").strip(),
                    engine=str(item.get("engine") or "").strip(),
                    published_date=_first_str(item.get("publishedDate")),
                    category=_first_str(item.get("category")),
                    score=float(item.get("score") or 0.0),
                    metadata=item.get("metadata") if isinstance(item.get("metadata"), dict) else {},
                )
            )
        return results

    async def health(self) -> dict[str, Any]:
        """健康检查只探活根路径 —— 真正跑一次搜索可能要等几十秒。"""
        url = f"{self.settings.searxng_base_url.rstrip('/')}/"
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(url)
            return {"ok": resp.status_code < 500, "status_code": resp.status_code}
        except httpx.HTTPError as exc:
            return {"ok": False, "error": str(exc) or type(exc).__name__}


def _first_str(value: Any) -> str | None:
    if isinstance(value, (list, tuple)):
        return str(value[0]) if value else None
    if value:
        return str(value)
    return None
