"""Crawl4AI HTTP 模式的单元测试（不触网）。

验三件事：
  1. 请求体用 0.9.x 的 urls + browser_config + crawler_config，且带 Bearer 鉴权头；
  2. 0.9.x 拒绝旧 payload（422）时能回退到 /md；
  3. 401 时给出「缺 token」的可读报错，而不是一句 HTTP 401。
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app.clients.crawler as crawler_mod
from app.clients.crawler import CrawlClient, _extract_markdown
from app.config import Settings


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "crawler_mode": "http",
        "crawler_base_url": "http://127.0.0.1:11235",
        "crawler_api_token": "tok-123",
        "crawler_min_content_length": 10,
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def _install_mock(monkeypatch, handler) -> None:
    """把 httpx.AsyncClient 换成带 MockTransport 的版本，拦截所有请求。"""
    real_client = httpx.AsyncClient

    def factory(*args: object, **kwargs: object) -> httpx.AsyncClient:
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_client(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(crawler_mod.httpx, "AsyncClient", factory)


V095_RESPONSE: dict[str, object] = {
    "success": True,
    "results": [
        {
            "url": "https://www.news.cn/a.htm",
            "markdown": {
                "fit_markdown": "清洗后的正文内容，" * 20,
                "raw_markdown": "原始正文内容，" * 20,
            },
        }
    ],
}


def test_http_mode_uses_v095_payload_and_bearer_token(monkeypatch) -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["auth"] = request.headers.get("authorization")
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=V095_RESPONSE)

    _install_mock(monkeypatch, handler)
    result = asyncio.run(CrawlClient(_settings()).crawl("https://www.news.cn/a.htm"))

    assert result.status == "ok"
    assert seen["path"] == "/crawl"
    assert seen["auth"] == "Bearer tok-123"
    body = seen["body"]
    assert isinstance(body, dict)
    assert body["urls"] == ["https://www.news.cn/a.htm"]
    assert body["crawler_config"]["type"] == "CrawlerRunConfig"  # type: ignore[index]
    assert body["browser_config"]["type"] == "BrowserConfig"  # type: ignore[index]


def test_http_mode_omits_authorization_when_token_empty(monkeypatch) -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json=V095_RESPONSE)

    _install_mock(monkeypatch, handler)
    result = asyncio.run(
        CrawlClient(_settings(crawler_api_token="")).crawl("https://www.news.cn/a.htm")
    )

    assert result.status == "ok"
    assert seen["auth"] is None


def test_http_mode_falls_back_to_md_when_server_rejects_v095_payload(monkeypatch) -> None:
    """老版本 Crawl4AI 只认 {"url": ...}：先 /crawl 吃 422，再退到 /md。"""
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        body = json.loads(request.content)
        if "urls" in body:
            return httpx.Response(422, json={"detail": "legacy only"})
        return httpx.Response(200, json={"markdown": "旧版正文，" * 20})

    _install_mock(monkeypatch, handler)
    result = asyncio.run(CrawlClient(_settings()).crawl("https://www.news.cn/a.htm"))

    assert result.status == "ok"
    assert paths == ["/crawl", "/md"]


def test_http_mode_reports_missing_token(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"detail": "unauthorized"})

    _install_mock(monkeypatch, handler)
    result = asyncio.run(CrawlClient(_settings()).crawl("https://www.news.cn/a.htm"))

    assert result.status == "failed"
    assert "401" in (result.error or "")
    assert "CRAWL4AI_API_TOKEN" in (result.error or "")


def test_extract_markdown_prefers_fit_markdown() -> None:
    """0.9.x 的 markdown 是嵌套对象，优先取 fit_markdown（清洗过的正文）。"""
    out = _extract_markdown(V095_RESPONSE)
    assert out.startswith("清洗后的正文内容")
    assert "原始正文内容" not in out


def test_extract_markdown_falls_back_to_raw_when_fit_is_empty() -> None:
    """有些页面 fit_markdown 是空的（正文挑选没命中），要退回 raw_markdown。"""
    data = {
        "success": True,
        "results": [{"markdown": {"fit_markdown": "", "raw_markdown": "完整正文，" * 20}}],
    }
    out = _extract_markdown(data)
    assert out.startswith("完整正文")


def test_extract_markdown_prefers_raw_when_fit_is_only_a_fragment() -> None:
    """fit 只挑出零星几句时，宁可用完整 raw —— 半截正文会被当成长度不足丢掉。"""
    data = {
        "success": True,
        "results": [
            {"markdown": {"fit_markdown": "只有标题", "raw_markdown": "完整正文，" * 20}}
        ],
    }
    out = _extract_markdown(data)
    assert out.startswith("完整正文")
