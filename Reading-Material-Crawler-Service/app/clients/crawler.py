"""Crawl4AI 网页清洗客户端（PRD §2.4）。

三种模式：
  library  —— 直接 import 本地 crawl4ai 库（AsyncWebCrawler），最贴近 PRD 描述
  http     —— 调用已启动的 Crawl4AI 服务（0.9.x 走 /crawl，老版本走 /md 或 /crawl）
  builtin  —— 内置降级提取器：Crawl4AI 不可用时的兜底，剥离导航/广告/页脚后转 Markdown

auto 模式按 library → http → builtin 顺序尝试。
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

from app.config import Settings, get_settings

_SKIP_TAGS = {
    "script", "style", "noscript", "svg", "iframe", "canvas", "form", "button",
    "nav", "header", "footer", "aside", "menu", "dialog", "template",
}
_BLOCK_TAGS = {
    "p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "blockquote", "td", "th",
    "dd", "dt", "figcaption", "pre", "section", "article", "div",
}
_MAIN_HINTS = ("article", "main", "content", "post", "story", "detail", "text")
# Crawl4AI 0.9.x 的 /crawl 请求体。旧版本只认 {"url": ...}，由 _via_http 负责回退。
_CRAWL4AI_V095_CRAWLER_PARAMS: dict[str, Any] = {
    "cache_mode": "BYPASS",
    "wait_until": "domcontentloaded",
    "word_count_threshold": 10,
    "remove_overlay_elements": True,
    "exclude_external_images": True,
}
_CRAWL4AI_V095_BROWSER_PARAMS: dict[str, Any] = {
    "headless": True,
    "text_mode": True,
    "enable_stealth": True,
    "locale": "zh-CN",
    "viewport_width": 1280,
    "viewport_height": 900,
}
# 正文容器特征：class/id 里出现这些词的多为文章正文
_CONTENT_HINTS = (
    "content", "article", "post", "story", "detail", "text", "zw", "news_txt",
    "article_con", "left_zw", "main-text", "artical", "body_con",
    # 国内新闻站常见的正文容器命名
    "content_desc", "art_con", "content_area", "txt_con", "news_content",
    "zoom", "trs_editor", "cnt_bd", "article_txt", "wznr", "main-cont",
)


class CrawlError(RuntimeError):
    """抓取失败。"""


@dataclass
class CrawlResult:
    url: str
    markdown: str = ""
    engine: str = ""
    status: str = "ok"  # ok | too_short | failed
    error: str | None = None
    content_length: int = 0


# ---------------------------------------------------------------------------
# 内置降级提取器
# ---------------------------------------------------------------------------
class _TextExtractor(HTMLParser):
    """把 HTML 正文抽成 Markdown 风格的纯文本。

    做法：逐个元素收集文本，记住「疑似正文容器」的文本区间，取最长的那个区间。
    不能用正则去抠 div —— 非贪婪匹配会在第一个 </div> 处截断，正文被砍掉一大半。
    """

    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.parts: list[str] = []
        self.stack: list[dict[str, object]] = []
        self.skip_depth = 0
        self.best_start = 0
        self.best_end = 0
        self.best_len = 0
        self._href: str | None = None

    # -- 标签 --
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _SKIP_TAGS:
            self.skip_depth += 1
            self.stack.append({"tag": tag, "skip": True, "cand": None})
            return
        if self.skip_depth:
            self.stack.append({"tag": tag, "skip": True, "cand": None})
            return

        cand: int | None = None
        if tag in ("article", "main"):
            cand = len(self.parts)
        elif tag == "div":
            blob = " ".join(f"{k}={v or ''}" for k, v in attrs).lower()
            if any(hint in blob for hint in _CONTENT_HINTS):
                cand = len(self.parts)
        self.stack.append({"tag": tag, "skip": False, "cand": cand})

        if tag in _BLOCK_TAGS:
            self.parts.append("\n")
        elif tag == "a":
            href = dict(attrs).get("href")
            self._href = urljoin(self.base_url, href) if href else None

    def handle_endtag(self, tag: str) -> None:
        if not self.stack:
            return
        entry = self.stack.pop()
        if entry["skip"]:
            if tag in _SKIP_TAGS:
                self.skip_depth = max(0, self.skip_depth - 1)
            return

        cand = entry["cand"]
        if cand is not None:
            length = sum(len(p) for p in self.parts[int(cand) :])
            if length > self.best_len:
                self.best_len = length
                self.best_start = int(cand)
                self.best_end = len(self.parts)

        if tag == "a":
            self._href = None
        if tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self.skip_depth:
            return
        text = data.strip()
        if not text:
            return
        self.parts.append(text + " ")

    # -- 输出 --
    def full_text(self) -> str:
        return _clean_text("".join(self.parts))

    def candidate_text(self) -> str:
        if self.best_len == 0:
            return ""
        return _clean_text("".join(self.parts[self.best_start : self.best_end]))


def _clean_text(raw: str) -> str:
    raw = re.sub(r"[ \t\u3000]+", " ", raw)
    raw = re.sub(r" *\n *", "\n", raw)
    raw = re.sub(r"\n{3,}", "\n\n", raw)
    return raw.strip()


def builtin_extract(html: str, url: str) -> str:
    """内置降级提取：剥离导航/广告/页脚，输出 Markdown 风格正文。"""
    parser = _TextExtractor(url)
    try:
        parser.feed(html)
        parser.close()
    except Exception:  # pragma: no cover - 解析异常时兜底
        text = re.sub(r"<[^>]+>", " ", html)
        return re.sub(r"\s{2,}", " ", text).strip()

    candidate = parser.candidate_text()
    full = parser.full_text()
    # 找到疑似正文容器就用它（更干净，能滤掉侧栏与相关阅读）；否则退回整页去噪文本
    if len(candidate) >= 80:
        return candidate
    return full if len(full) > len(candidate) else candidate


# ---------------------------------------------------------------------------
# 客户端
# ---------------------------------------------------------------------------
class CrawlClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._lock = asyncio.Lock()  # 禁止并发抓取（PRD §4.2）

    async def crawl(self, url: str) -> CrawlResult:
        """抓取并清洗单个 URL。串行执行，失败不阻塞主流程。"""
        async with self._lock:
            mode = self.settings.crawler_mode.strip().lower()
            attempts: list[tuple[str, Any]] = []
            if mode in {"auto", "library"}:
                attempts.append(("crawl4ai-library", self._via_library))
            if mode in {"auto", "http"}:
                attempts.append(("crawl4ai-http", self._via_http))
            if mode == "auto" or not attempts:
                attempts.append(("builtin", self._via_builtin))

            errors: list[str] = []
            for engine, fn in attempts:
                try:
                    markdown = await fn(url)
                except Exception as exc:  # noqa: BLE001 - 逐个降级，记录原因
                    errors.append(f"{engine}: {exc}")
                    continue
                if not markdown:
                    errors.append(f"{engine}: 正文为空")
                    continue
                length = len(markdown)
                if length < self.settings.crawler_min_content_length:
                    return CrawlResult(
                        url=url,
                        markdown=markdown,
                        engine=engine,
                        status="too_short",
                        content_length=length,
                        error=f"清洗后正文仅 {length} 字，低于 {self.settings.crawler_min_content_length} 字下限，已丢弃",
                    )
                return CrawlResult(url=url, markdown=markdown, engine=engine, status="ok", content_length=length)

            return CrawlResult(
                url=url,
                status="failed",
                error="；".join(errors) or "所有清洗方式均失败",
            )

    # -- 各模式实现 --------------------------------------------------------
    async def _via_library(self, url: str) -> str:
        try:
            from crawl4ai import AsyncWebCrawler  # type: ignore
        except ImportError as exc:
            raise CrawlError("未安装 crawl4ai 库（pip install crawl4ai）") from exc

        async with AsyncWebCrawler(verbose=False) as crawler:
            result = await crawler.arun(url=url)
        markdown = ""
        try:
            markdown = getattr(result, "markdown", "") or ""
        except Exception:  # pragma: no cover
            markdown = ""
        if isinstance(markdown, str):
            return markdown.strip()
        # 新版返回对象时取 .raw_markdown
        raw = getattr(markdown, "raw_markdown", "") or getattr(markdown, "fit_markdown", "")
        return str(raw).strip()

    async def _via_http(self, url: str) -> str:
        """调用 Crawl4AI 服务的 HTTP 接口。

        版本差异：0.9.x 的 /crawl 收 urls + browser_config + crawler_config，
        老版本只认 {"url": ...}。先按新版打，422/404 再回退老版本，
        这样容器换版本不用动客户端。
        """
        base = self.settings.crawler_base_url.rstrip("/")
        headers = {"Content-Type": "application/json"}
        token = self.settings.crawler_api_token.strip()
        if token:
            headers["Authorization"] = f"Bearer {token}"

        v095_payload = {
            "urls": [url],
            "browser_config": {
                "type": "BrowserConfig",
                "params": dict(_CRAWL4AI_V095_BROWSER_PARAMS),
            },
            "crawler_config": {
                "type": "CrawlerRunConfig",
                "params": dict(_CRAWL4AI_V095_CRAWLER_PARAMS),
            },
        }
        legacy_payload = {
            "url": url,
            "page_config": {"only_main_content": True},
            "f": "markdown",
        }

        async with httpx.AsyncClient(timeout=self.settings.crawler_timeout) as client:
            resp = await self._post(client, f"{base}/crawl", headers, v095_payload)
            if resp.status_code in {404, 422}:
                # 老版本：正文走 /md；连 /md 都没有时再退到 /crawl
                resp = await self._post(client, f"{base}/md", headers, legacy_payload)
                if resp.status_code == 404:
                    resp = await self._post(client, f"{base}/crawl", headers, legacy_payload)
            if resp.status_code == 401:
                raise CrawlError(
                    "Crawl4AI 拒绝请求（HTTP 401）：缺少或错误的 CRAWL4AI_API_TOKEN"
                    "（容器侧 CRAWL4AI_API_TOKEN 与客户端侧 CRAWLER_API_TOKEN 需一致）"
                )
            if resp.status_code != 200:
                raise CrawlError(f"Crawl4AI 返回 HTTP {resp.status_code}: {resp.text[:300]}")
            try:
                data = resp.json()
            except ValueError as exc:
                raise CrawlError(f"Crawl4AI 返回的不是 JSON: {resp.text[:300]}") from exc
        return _extract_markdown(data)

    @staticmethod
    async def _post(
        client: httpx.AsyncClient,
        url: str,
        headers: dict[str, str],
        payload: dict[str, Any],
    ) -> httpx.Response:
        try:
            return await client.post(url, json=payload, headers=headers)
        except httpx.HTTPError as exc:
            raise CrawlError(f"无法连接 Crawl4AI 服务 ({url}): {exc}") from exc

    async def _via_builtin(self, url: str) -> str:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
            ),
            "Accept-Language": "zh-CN,zh;q=0.9",
        }
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
            try:
                resp = await client.get(url, headers=headers)
            except httpx.HTTPError as exc:
                raise CrawlError(f"无法抓取 {url}: {exc}") from exc
        if resp.status_code != 200:
            raise CrawlError(f"目标站返回 HTTP {resp.status_code}")
        if "html" not in resp.headers.get("content-type", "").lower():
            raise CrawlError(f"目标站不是 HTML（content-type={resp.headers.get('content-type')}）")
        resp.encoding = resp.encoding or "utf-8"
        return builtin_extract(resp.text, str(resp.url))


def _extract_markdown(data: Any) -> str:
    """从 Crawl4AI 各种响应结构里找出 markdown 字段。"""
    if isinstance(data, str):
        return data.strip()
    if isinstance(data, dict):
        # Crawl4AI 0.9.x：{"success": true, "results": [{"markdown": {"fit_markdown": ..., "raw_markdown": ...}}]}
        # 先按这个结构精确取，避免递归时先撞上 media/metadata 里的杂字段。
        results = data.get("results")
        if isinstance(results, list):
            for item in results:
                if not isinstance(item, dict):
                    continue
                md = item.get("markdown")
                if isinstance(md, dict):
                    fit = md.get("fit_markdown")
                    raw = md.get("raw_markdown")
                    fit_text = fit.strip() if isinstance(fit, str) else ""
                    raw_text = raw.strip() if isinstance(raw, str) else ""
                    # fit 是 Crawl4AI 的「正文挑选」结果；但它有时只挑出零星几句，
                    # 那时宁可用完整（带导航的）raw，也不要半截正文。
                    if fit_text and (not raw_text or len(fit_text) * 2 >= len(raw_text)):
                        return fit_text
                    if raw_text:
                        return raw_text
                    if fit_text:
                        return fit_text
                elif isinstance(md, str) and md.strip():
                    return md.strip()
        for key in ("markdown", "raw_markdown", "fit_markdown"):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        result = data.get("result")
        if result is not None:
            return _extract_markdown(result)
        for value in data.values():
            if isinstance(value, (dict, list)):
                found = _extract_markdown(value)
                if found:
                    return found
    if isinstance(data, list):
        for item in data:
            found = _extract_markdown(item)
            if found:
                return found
    return ""


def domain_of(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except ValueError:
        return ""
