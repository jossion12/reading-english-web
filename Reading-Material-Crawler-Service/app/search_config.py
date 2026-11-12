"""检索配置加载与过滤规则（PRD §2.1 / §2.2）。"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

from app.config import Settings, get_settings


class SearchConfigError(RuntimeError):
    """检索配置错误。"""


class SearchConfig:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.data = self._load(self.settings.search_path)

    @staticmethod
    def _load(path: Path) -> dict[str, Any]:
        if not path.exists():
            raise SearchConfigError(f"检索配置不存在: {path}")
        with path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        if not isinstance(data, dict):
            raise SearchConfigError(f"检索配置格式错误: {path}")
        return data

    # --- 主题 / Query ------------------------------------------------------
    @property
    def themes(self) -> dict[str, Any]:
        return self.data.get("themes") or {}

    @property
    def time_ranges(self) -> dict[str, Any]:
        return self.data.get("time_ranges") or {}

    @property
    def domain_whitelist(self) -> list[str]:
        return [str(d).strip().lower().lstrip(".") for d in (self.data.get("domain_whitelist") or []) if str(d).strip()]

    @property
    def blacklist_keywords(self) -> list[str]:
        return [str(k).strip() for k in (self.data.get("blacklist_keywords") or []) if str(k).strip()]

    @property
    def filters(self) -> dict[str, Any]:
        return self.data.get("filters") or {}

    @property
    def rss_sources(self) -> list[dict[str, str]]:
        """RSS 直采源列表（检索兜底通道）。"""
        out: list[dict[str, str]] = []
        for item in self.data.get("rss_sources") or []:
            if not isinstance(item, dict):
                continue
            url = str(item.get("url") or "").strip()
            if not url:
                continue
            out.append({"name": str(item.get("name") or url).strip(), "url": url})
        return out

    def theme_keywords(self, theme: str) -> list[str]:
        """主题自身的关键词（未指定关键词时用于给候选排序）。"""
        entry = self.themes.get(theme) or {}
        return [str(k).strip() for k in (entry.get("keywords") or []) if str(k).strip()]

    def window_days(self, time_range: str) -> int | None:
        """时间范围对应的天数窗口（None 表示不按时间过滤）。

        SearXNG 与 RSS 两条通道共用这一口径：SearXNG 那条通道不一定支持
        time_range 参数，届时由管线用 publishedDate 在本地按这个窗口兜住时效。
        """
        return {"day": 1, "week": 7, "month": 31}.get(time_range)

    def theme_names(self) -> list[str]:
        return list(self.themes.keys())

    def build_queries(self, theme: str, keyword: str | None = None) -> list[str]:
        """按主题生成预设搜索 Query（PRD §2.1）。"""
        entry = self.themes.get(theme)
        if entry is None:
            raise SearchConfigError(
                f"未知主题: {theme}（可选: {', '.join(self.theme_names())}）"
            )
        templates = entry.get("queries") or []
        kw = (keyword or "").strip()
        queries: list[str] = []
        for tpl in templates:
            query = str(tpl).strip()
            if "{keyword}" in query:
                if not kw:
                    # 没给关键词时，用主题自身的关键词兜底
                    fallback = (entry.get("keywords") or [theme])[0]
                    query = query.replace("{keyword}", str(fallback))
                else:
                    query = query.replace("{keyword}", kw)
            if query and query not in queries:
                queries.append(query)
        return queries

    def searxng_time_range(self, time_range: str) -> str | None:
        entry = self.time_ranges.get(time_range)
        if entry is None:
            return None
        return str(entry.get("searxng") or time_range)

    # --- 过滤 --------------------------------------------------------------
    def is_valid_url(self, url: str) -> bool:
        if not url:
            return False
        try:
            parsed = urlparse(url)
        except ValueError:
            return False
        return parsed.scheme in {"http", "https"} and bool(parsed.hostname)

    def is_whitelisted(self, url: str) -> bool:
        try:
            host = (urlparse(url).hostname or "").lower()
        except ValueError:
            return False
        if not host:
            return False
        for domain in self.domain_whitelist:
            if host == domain or host.endswith("." + domain):
                return True
        return False

    def hit_blacklist(self, *texts: str | None) -> str | None:
        """命中黑名单则返回命中的关键词。"""
        blob = " ".join(t for t in texts if t)
        if not blob:
            return None
        for word in self.blacklist_keywords:
            if word in blob:
                return word
        return None


@lru_cache(maxsize=1)
def get_search_config() -> SearchConfig:
    return SearchConfig()
