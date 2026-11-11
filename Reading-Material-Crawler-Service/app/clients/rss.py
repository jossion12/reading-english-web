"""白名单站点 RSS 直采客户端（检索兜底通道）。

为什么需要它：SearXNG 只是**元搜索入口**，真正出结果的是它背后的各个上游引擎。
本机实测（容器出口）这些引擎基本全废：

  · baidu         返回「百度安全验证」拦截页
  · sogou         镜像版本 bug（'SXNG_Response' object has no attribute 'next_request'）
  · duckduckgo / brave / google cse   超时（境外不可达）
  · bing news / 360search   搜索结果是 JS 渲染，HTML 里没有文章链接 → 解析出 0 条

于是检索拿不到任何候选。而**白名单媒体自带的 RSS 频道是稳定可用的**
（中新网 9 个频道实测当天更新），域名天然落在白名单里，因此拿它做兜底：
SearXNG 仍然按 PRD §2.2 作为主检索通道，只有在它没产出候选时才启用本通道。
"""

from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from xml.etree import ElementTree

import httpx

from app.config import Settings, get_settings

ATOM_NS = "http://www.w3.org/2005/Atom"
DC_NS = "http://purl.org/dc/elements/1.1/"
CONTENT_NS = "http://purl.org/rss/1.0/modules/content/"


class RssError(RuntimeError):
    """RSS 抓取或解析失败。"""


@dataclass
class RssItem:
    """一条 RSS 条目。"""

    title: str
    url: str
    content: str = ""
    published_at: datetime | None = None
    source: str = ""

    @property
    def published_date(self) -> str | None:
        if self.published_at is None:
            return None
        return self.published_at.astimezone(timezone.utc).strftime("%Y-%m-%d")

    @property
    def engine(self) -> str:
        return f"rss:{self.source}" if self.source else "rss"


# ------------------------------------------------------------------ 解析 ---
# 块级标签换成空格，行内标签直接去掉 —— 避免中文正文里出现多余空格
_BLOCK_RE = re.compile(
    r"</?(p|div|br|li|ul|ol|tr|td|th|h[1-6]|section|article|blockquote)\b[^>]*>",
    re.IGNORECASE,
)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_ENTITIES = {
    "&amp;": "&", "&lt;": "<", "&gt;": ">", "&quot;": '"',
    "&apos;": "'", "&nbsp;": " ", "&ldquo;": "“", "&rdquo;": "”",
}


def strip_html(text: str) -> str:
    """把 RSS 描述里的 HTML 标签清掉，只留纯文本。"""
    if not text:
        return ""
    cleaned = _BLOCK_RE.sub(" ", text)
    cleaned = _TAG_RE.sub("", cleaned)
    for key, value in _ENTITIES.items():
        cleaned = cleaned.replace(key, value)
    return _WS_RE.sub(" ", cleaned).strip()


def _text(node: Any) -> str:
    if node is None:
        return ""
    return "".join(node.itertext()).strip()


def parse_date(value: str | None) -> datetime | None:
    """解析 RSS 的日期（RFC822 或 ISO8601）。"""
    if not value:
        return None
    value = value.strip()
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        parsed = None
    if parsed is not None:
        return parsed
    for fmt in (
        "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S", "%Y-%m-%d",
    ):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def parse_feed(xml_text: str, *, source: str = "") -> list[RssItem]:
    """解析 RSS 2.0 与 Atom 两种格式，返回条目列表。"""
    if not xml_text or not xml_text.strip():
        raise RssError("RSS 内容为空")
    try:
        root = ElementTree.fromstring(xml_text.encode("utf-8"))
    except ElementTree.ParseError as exc:
        raise RssError(f"RSS 解析失败: {exc}") from exc

    items: list[RssItem] = []

    for node in root.findall(".//item"):
        desc = _text(node.find("description")) or _text(node.find(f"{{{CONTENT_NS}}}encoded"))
        pub = _text(node.find("pubDate")) or _text(node.find(f"{{{DC_NS}}}date"))
        items.append(
            RssItem(
                title=_text(node.find("title")),
                url=_text(node.find("link")),
                content=strip_html(desc),
                published_at=parse_date(pub),
                source=source,
            )
        )

    if not items:  # Atom
        for node in root.findall(f".//{{{ATOM_NS}}}entry"):
            link = ""
            for ln in node.findall(f"{{{ATOM_NS}}}link"):
                if ln.get("rel") in (None, "alternate"):
                    link = ln.get("href") or ""
                    break
            desc = _text(node.find(f"{{{ATOM_NS}}}summary")) or _text(node.find(f"{{{ATOM_NS}}}content"))
            pub = _text(node.find(f"{{{ATOM_NS}}}published")) or _text(node.find(f"{{{ATOM_NS}}}updated"))
            items.append(
                RssItem(
                    title=_text(node.find(f"{{{ATOM_NS}}}title")),
                    url=link,
                    content=strip_html(desc),
                    published_at=parse_date(pub),
                    source=source,
                )
            )

    return items


# ------------------------------------------------------------------ 客户端 ---
class RssClient:
    """串行抓取 RSS 频道（带最小间隔，禁止并发 —— 与 SearXNG 同一套限流约定）。"""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._lock = asyncio.Lock()
        self._last_call = 0.0

    async def _throttle(self) -> None:
        gap = time.monotonic() - self._last_call
        if gap < self.settings.rss_min_interval:
            await asyncio.sleep(self.settings.rss_min_interval - gap)
        self._last_call = time.monotonic()

    async def fetch(self, url: str, *, source: str = "") -> list[RssItem]:
        """抓取并解析一个 RSS 频道。失败抛 RssError，由上层记录为可读错误。"""
        async with self._lock:
            await self._throttle()
            headers = {
                "User-Agent": self.settings.rss_user_agent,
                "Accept": "application/rss+xml, application/xml, text/xml, */*",
            }
            try:
                async with httpx.AsyncClient(
                    timeout=self.settings.rss_timeout, follow_redirects=True
                ) as client:
                    resp = await client.get(url, headers=headers)
            except httpx.HTTPError as exc:
                raise RssError(f"无法访问 RSS ({url}): {exc}") from exc

        if resp.status_code != 200:
            raise RssError(f"RSS 返回 HTTP {resp.status_code}")
        return parse_feed(resp.text, source=source)
