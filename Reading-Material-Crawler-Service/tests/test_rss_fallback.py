"""RSS 直采兜底通道的单元测试（不触网）。

覆盖两件事：
1. RSS / Atom 的解析（含日期、HTML 清洗）；
2. SearXNG 无候选时，检索管线自动改走 RSS 兜底，并且照常做白名单 / 黑名单 /
   标题长度 / 时间窗口过滤，关键词命中与未命中的两种行为。
"""

from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.clients.rss import RssItem, parse_date, parse_feed, strip_html
from app.pipeline.search import SearchPipeline
from app.search_config import SearchConfig

RSS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>中新网</title>
    <item>
      <title><![CDATA[乡村教师雨雪天徒步家访]]></title>
      <link>https://www.chinanews.com.cn/sh/2026/11-11/10730187.shtml</link>
      <description><![CDATA[<p>暴雪中她走了三小时翻越两座山头。</p>]]></description>
      <pubDate>Mon, 11 Nov 2026 10:00:00 +0800</pubDate>
    </item>
    <item>
      <title>某地发生交通事故致多人受伤</title>
      <link>https://www.chinanews.com.cn/sh/2026/11-11/10730188.shtml</link>
      <description>负面消息</description>
      <pubDate>Mon, 11 Nov 2026 11:00:00 +0800</pubDate>
    </item>
  </channel>
</rss>
"""

ATOM_XML = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title>社区志愿服务暖人心</title>
    <link rel="alternate" href="https://www.chinanews.com.cn/sh/2026/11-11/1.shtml"/>
    <summary>志愿者为社区老人送温暖</summary>
    <published>2026-11-11T09:30:00+08:00</published>
  </entry>
</feed>
"""


class FakeSearXNG:
    """假引擎：永远返回空结果，强制走 RSS 兜底。"""

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def search(self, query: str, **kwargs: object) -> list:
        self.calls.append(query)
        return []


class FakeRss:
    """假 RSS 源：按 url 返回预设条目。"""

    def __init__(self, items_by_source: dict[str, list[RssItem]]) -> None:
        self.items_by_source = items_by_source
        self.calls: list[str] = []

    async def fetch(self, url: str, *, source: str = "") -> list[RssItem]:
        self.calls.append(url)
        return self.items_by_source.get(source, [])


def make_config(*, rss: bool = True) -> SearchConfig:
    cfg = SearchConfig()
    cfg.data["themes"] = {
        "人与社会": {"queries": ["q1"], "keywords": ["社区", "志愿者", "邻里", "公益", "文化"]},
    }
    cfg.data["rss_sources"] = (
        [{"name": "中新网·社会", "url": "https://www.chinanews.com.cn/rss/society.xml"}] if rss else []
    )
    return cfg


def run(coro):
    return asyncio.run(coro)


# ------------------------------------------------------------------ 解析 ---
def test_parse_rss_items() -> None:
    items = parse_feed(RSS_XML, source="中新网·社会")
    assert len(items) == 2
    assert items[0].title == "乡村教师雨雪天徒步家访"
    assert items[0].url == "https://www.chinanews.com.cn/sh/2026/11-11/10730187.shtml"
    assert items[0].published_date == "2026-11-11"
    assert items[0].engine == "rss:中新网·社会"
    # description 里的 HTML 标签要清掉
    assert items[0].content == "暴雪中她走了三小时翻越两座山头。"


def test_parse_atom_entries() -> None:
    items = parse_feed(ATOM_XML, source="中新网·社会")
    assert len(items) == 1
    assert items[0].title == "社区志愿服务暖人心"
    assert items[0].url == "https://www.chinanews.com.cn/sh/2026/11-11/1.shtml"
    assert items[0].content == "志愿者为社区老人送温暖"


def test_strip_html_and_parse_date() -> None:
    assert strip_html("<b>粗体</b>&amp;文本") == "粗体&文本"
    assert strip_html("") == ""
    assert parse_date("Mon, 11 Nov 2026 10:00:00 +0800") is not None
    assert parse_date("2026-11-11") is not None
    assert parse_date("") is None
    assert parse_date("不是日期") is None


# ------------------------------------------------------------------ 兜底 ---
def _rss_item(title: str, url: str, days_ago: int = 0, content: str = "") -> RssItem:
    when = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return RssItem(title=title, url=url, content=content, published_at=when, source="中新网·社会")


def test_fallback_used_when_searxng_empty() -> None:
    fake_rss = FakeRss(
        {
            "中新网·社会": [
                _rss_item("社区志愿者温暖邻里", "https://www.chinanews.com.cn/a.shtml"),
                _rss_item("某地发生交通事故致多人受伤", "https://www.chinanews.com.cn/b.shtml"),
                _rss_item("不在白名单的站点内容", "https://evil.example.com/c.shtml"),
            ]
        }
    )
    pipeline = SearchPipeline(client=FakeSearXNG(), config=make_config(), rss_client=fake_rss)  # type: ignore[arg-type]

    outcome = run(pipeline.run(theme="人与社会"))

    assert outcome.fallback_used is True
    assert outcome.sources_used == ["中新网·社会"]
    assert [c.title for c in outcome.candidates] == ["社区志愿者温暖邻里"]
    assert outcome.dropped["blacklist"] == 1
    assert outcome.dropped["not_whitelisted"] == 1
    assert outcome.exhausted is False


def test_fallback_filters_old_items_by_time_window() -> None:
    fake_rss = FakeRss(
        {
            "中新网·社会": [
                _rss_item("今天发布的新鲜内容", "https://www.chinanews.com.cn/new.shtml"),
                _rss_item("二十天前发布的老内容", "https://www.chinanews.com.cn/old.shtml", days_ago=20),
            ]
        }
    )
    pipeline = SearchPipeline(client=FakeSearXNG(), config=make_config(), rss_client=fake_rss)  # type: ignore[arg-type]

    outcome = run(pipeline.run(theme="人与社会", time_range="week"))

    urls = [c.url for c in outcome.candidates]
    assert "https://www.chinanews.com.cn/new.shtml" in urls
    assert "https://www.chinanews.com.cn/old.shtml" not in urls
    assert outcome.dropped["too_old"] == 1


def test_keyword_hit_keeps_only_matching_candidates() -> None:
    fake_rss = FakeRss(
        {
            "中新网·社会": [
                _rss_item("乡村教师家访暖人心", "https://www.chinanews.com.cn/hit.shtml"),
                _rss_item("完全无关的一条内容", "https://www.chinanews.com.cn/miss.shtml"),
            ]
        }
    )
    pipeline = SearchPipeline(client=FakeSearXNG(), config=make_config(), rss_client=fake_rss)  # type: ignore[arg-type]

    outcome = run(pipeline.run(theme="人与社会", keyword="家访"))

    assert [c.title for c in outcome.candidates] == ["乡村教师家访暖人心"]
    assert outcome.keyword_unmatched is False


def test_keyword_unmatched_still_returns_latest_candidates() -> None:
    """关键词没命中时也要给管理员候选，只是标记出来（而不是空列表）。"""
    fake_rss = FakeRss(
        {
            "中新网·社会": [
                _rss_item("今天的一条新闻标题", "https://www.chinanews.com.cn/a.shtml"),
            ]
        }
    )
    pipeline = SearchPipeline(client=FakeSearXNG(), config=make_config(), rss_client=fake_rss)  # type: ignore[arg-type]

    outcome = run(pipeline.run(theme="人与社会", keyword="完全不存在的东西"))

    assert len(outcome.candidates) == 1
    assert outcome.keyword_unmatched is True


def test_no_rss_sources_configured_means_no_fallback() -> None:
    fake_rss = FakeRss({"中新网·社会": [_rss_item("内容在这里", "https://www.chinanews.com.cn/a.shtml")]})
    pipeline = SearchPipeline(
        client=FakeSearXNG(), config=make_config(rss=False), rss_client=fake_rss  # type: ignore[arg-type]
    )

    outcome = run(pipeline.run(theme="人与社会"))

    assert outcome.fallback_used is False
    assert outcome.candidates == []
    assert outcome.exhausted is True
    assert fake_rss.calls == []


def test_same_article_from_two_channels_is_deduped() -> None:
    """同一条新闻常被多个频道同时推送，候选列表里只能出现一次。"""
    same = _rss_item("社区志愿者温暖邻里", "https://www.chinanews.com.cn/a.shtml")
    same_other_channel = RssItem(
        title="社区志愿者温暖邻里",
        url="https://www.chinanews.com.cn/a.shtml",
        content=same.content,
        published_at=same.published_at,
        source="中新网·国内",
    )
    same_title_diff_url = RssItem(
        title="社区志愿者温暖邻里",
        url="https://www.chinanews.com.cn/a2.shtml",
        content=same.content,
        published_at=same.published_at,
        source="中新网·国内",
    )
    fake_rss = FakeRss(
        {
            "中新网·社会": [same],
            "中新网·国内": [same_other_channel, same_title_diff_url],
        }
    )
    cfg = make_config()
    cfg.data["rss_sources"] = [
        {"name": "中新网·社会", "url": "https://www.chinanews.com.cn/rss/society.xml"},
        {"name": "中新网·国内", "url": "https://www.chinanews.com.cn/rss/china.xml"},
    ]
    pipeline = SearchPipeline(client=FakeSearXNG(), config=cfg, rss_client=fake_rss)  # type: ignore[arg-type]

    outcome = run(pipeline.run(theme="人与社会"))

    assert len(outcome.candidates) == 1
    assert outcome.candidates[0].url == "https://www.chinanews.com.cn/a.shtml"
    assert outcome.dropped["duplicate"] == 2
