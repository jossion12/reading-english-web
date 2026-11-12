"""搜索管线单元测试：用假引擎喂结果，验证白名单/黑名单/去重/标题过滤。

不触网 —— 真实 SearXNG 的可达性属于环境问题，引擎返回什么由单元测试固定下来。
"""

from __future__ import annotations

import asyncio
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.clients.searxng import RawResult
from app.pipeline.search import SearchPipeline
from app.search_config import SearchConfig


class FakeSearXNG:
    """假引擎：返回预设结果，并记录被调用的 query 与 time_range。"""

    def __init__(self, results_by_query: dict[str, list[RawResult]]) -> None:
        self.results_by_query = results_by_query
        self.calls: list[str] = []
        self.time_ranges: list[str | None] = []

    async def search(self, query: str, **kwargs: object) -> list[RawResult]:
        self.calls.append(query)
        self.time_ranges.append(kwargs.get("time_range"))  # type: ignore[arg-type]
        return self.results_by_query.get(query, [])


def make_result(
    title: str,
    url: str,
    content: str = "摘要内容",
    published_date: str | None = None,
) -> RawResult:
    return RawResult(
        title=title,
        url=url,
        content=content,
        engine="fake",
        published_date=published_date,
    )


def run(coro):
    return asyncio.run(coro)


def test_keeps_whitelisted_only() -> None:
    fake = FakeSearXNG(
        {
            "q1": [
                make_result("乡村教师雨雪天家访", "https://www.news.cn/2026-10/20/c_1.htm"),
                make_result("某站爆料内容", "https://evil.example.com/a.htm"),
            ]
        }
    )
    cfg = SearchConfig()
    cfg.data["rss_sources"] = []  # 本组用例只测 SearXNG 路径，关掉 RSS 兜底
    cfg.data["themes"] = {"人与社会": {"queries": ["q1"], "keywords": []}}
    pipeline = SearchPipeline(client=fake, config=cfg)  # type: ignore[arg-type]

    outcome = run(pipeline.run(theme="人与社会"))

    assert len(outcome.candidates) == 1
    assert outcome.candidates[0].domain.endswith("news.cn")
    assert outcome.dropped["not_whitelisted"] == 1


def test_drops_blacklist_keyword() -> None:
    fake = FakeSearXNG(
        {
            "q1": [
                make_result("某地发生交通事故", "https://www.news.cn/a.htm"),
                make_result("社区志愿者温暖邻里", "https://www.news.cn/b.htm"),
            ]
        }
    )
    cfg = SearchConfig()
    cfg.data["rss_sources"] = []  # 本组用例只测 SearXNG 路径，关掉 RSS 兜底
    cfg.data["themes"] = {"人与社会": {"queries": ["q1"], "keywords": []}}
    pipeline = SearchPipeline(client=fake, config=cfg)  # type: ignore[arg-type]

    outcome = run(pipeline.run(theme="人与社会"))

    assert len(outcome.candidates) == 1
    assert outcome.candidates[0].title == "社区志愿者温暖邻里"
    assert outcome.dropped["blacklist"] == 1


def test_drops_invalid_and_short_title() -> None:
    fake = FakeSearXNG(
        {
            "q1": [
                make_result("短标题", "https://www.news.cn/a.htm"),
                make_result("正常长标题在这里", "ftp://www.news.cn/b.htm"),
                make_result("另一个正常长标题", "https://www.news.cn/c.htm"),
            ]
        }
    )
    cfg = SearchConfig()
    cfg.data["rss_sources"] = []  # 本组用例只测 SearXNG 路径，关掉 RSS 兜底
    cfg.data["themes"] = {"推断的": {}}
    cfg.data["themes"] = {"人与社会": {"queries": ["q1"], "keywords": []}}
    pipeline = SearchPipeline(client=fake, config=cfg)  # type: ignore[arg-type]

    outcome = run(pipeline.run(theme="人与社会"))

    urls = [c.url for c in outcome.candidates]
    assert "https://www.news.cn/c.htm" in urls
    assert "ftp://www.news.cn/b.htm" not in urls
    assert outcome.dropped["invalid_url"] == 1
    assert outcome.dropped["short_title"] == 1


def test_deduplicates_same_url() -> None:
    fake = FakeSearXNG(
        {
            "q1": [make_result("同一个链接出现两次", "https://www.news.cn/a.htm")],
            "q2": [make_result("同一个链接出现两次", "https://www.news.cn/a.htm")],
        }
    )
    cfg = SearchConfig()
    cfg.data["rss_sources"] = []  # 本组用例只测 SearXNG 路径，关掉 RSS 兜底
    cfg.data["themes"] = {"人与社会": {"queries": ["q1", "q2"], "keywords": []}}
    pipeline = SearchPipeline(client=fake, config=cfg)  # type: ignore[arg-type]

    outcome = run(pipeline.run(theme="人与社会"))

    assert len(outcome.candidates) == 1
    assert outcome.dropped["duplicate"] == 1


def test_exhausted_flag_when_nothing_survives() -> None:
    fake = FakeSearXNG({"q1": [make_result("非白名单来源", "https://evil.example.com/x.htm")]})
    cfg = SearchConfig()
    cfg.data["rss_sources"] = []  # 本组用例只测 SearXNG 路径，关掉 RSS 兜底
    cfg.data["themes"] = {"人与社会": {"queries": ["q1"], "keywords": []}}
    pipeline = SearchPipeline(client=fake, config=cfg)  # type: ignore[arg-type]

    outcome = run(pipeline.run(theme="人与社会"))

    assert outcome.candidates == []
    assert outcome.exhausted is True


def test_query_templates_are_used() -> None:
    fake = FakeSearXNG({})
    cfg = SearchConfig()
    cfg.data["rss_sources"] = []  # 本组用例只测 SearXNG 路径，关掉 RSS 兜底
    cfg.data["themes"] = {"人与自然": {"queries": ["{keyword} 生态"], "keywords": ["生态"]}}
    pipeline = SearchPipeline(client=fake, config=cfg)  # type: ignore[arg-type]

    run(pipeline.run(theme="人与自然", keyword="湿地"))

    # 第一次带 time_range，空结果后降级重试一次不限时 —— 两次都是同一条模板 Query
    assert fake.calls == ["湿地 生态", "湿地 生态"]
    assert fake.time_ranges == ["week", None]


class TimeRangeBlindSearXNG:
    """模拟不支持 time_range 的 SearXNG 实例。

    SearXNG 会跳过没开 time_range_support 的引擎，这种实例带 time_range 反而一条不出。
    """

    def __init__(self, results: list[RawResult]) -> None:
        self.results = results
        self.calls: list[str] = []
        self.time_ranges: list[str | None] = []

    async def search(self, query: str, **kwargs: object) -> list[RawResult]:
        self.calls.append(query)
        self.time_ranges.append(kwargs.get("time_range"))  # type: ignore[arg-type]
        if kwargs.get("time_range"):
            return []
        return self.results


def test_falls_back_when_instance_ignores_time_range() -> None:
    """实例不支持 time_range 时应降级重试一次不限时，并留下可读的提示。"""
    fake = TimeRangeBlindSearXNG(
        [make_result("社区志愿者暖心服务", "https://www.news.cn/a.htm")]
    )
    cfg = SearchConfig()
    cfg.data["rss_sources"] = []  # 本组用例只测 SearXNG 路径，关掉 RSS 兜底
    cfg.data["themes"] = {"人与社会": {"queries": ["q1"], "keywords": []}}
    pipeline = SearchPipeline(client=fake, config=cfg)  # type: ignore[arg-type]

    outcome = run(pipeline.run(theme="人与社会"))

    assert len(outcome.candidates) == 1
    assert fake.time_ranges == ["week", None]
    assert any("降级" in e for e in outcome.errors), outcome.errors


def test_drops_candidates_older_than_window() -> None:
    """降级成不限时检索后，本地按 publishedDate 兜住时效（与 RSS 通道同口径）。"""
    fake = FakeSearXNG(
        {
            "q1": [
                make_result(
                    "很久以前发布的一条旧新闻报道",
                    "https://www.news.cn/old.htm",
                    published_date="2020-01-01T00:00:00",
                ),
                make_result(
                    "今天刚刚发布的一条最新新闻报道",
                    "https://www.news.cn/new.htm",
                    published_date=datetime.now(timezone.utc).isoformat(),
                ),
            ]
        }
    )
    cfg = SearchConfig()
    cfg.data["rss_sources"] = []  # 这组用例只测 SearXNG 路径，关掉 RSS 兜底
    cfg.data["themes"] = {"人与社会": {"queries": ["q1"], "keywords": []}}
    pipeline = SearchPipeline(client=fake, config=cfg)  # type: ignore[arg-type]

    outcome = run(pipeline.run(theme="人与社会", time_range="week"))

    urls = [c.url for c in outcome.candidates]
    assert "https://www.news.cn/new.htm" in urls
    assert "https://www.news.cn/old.htm" not in urls
    assert outcome.dropped["too_old"] == 1


def test_keeps_candidates_without_published_date() -> None:
    """没有 publishedDate 的候选照留 —— 引擎不一定给日期，不能一刀切丢掉。"""
    fake = FakeSearXNG(
        {"q1": [make_result("没有标注发布时间的新闻报道", "https://www.news.cn/a.htm")]}
    )
    cfg = SearchConfig()
    cfg.data["rss_sources"] = []
    cfg.data["themes"] = {"人与社会": {"queries": ["q1"], "keywords": []}}
    pipeline = SearchPipeline(client=fake, config=cfg)  # type: ignore[arg-type]

    outcome = run(pipeline.run(theme="人与社会", time_range="week"))

    assert len(outcome.candidates) == 1
    assert outcome.dropped["too_old"] == 0


class SlowSearXNG:
    """假引擎：模拟上游引擎挂住不返回。"""

    def __init__(self, delay: float) -> None:
        self.delay = delay
        self.calls: list[str] = []

    async def search(self, query: str, **kwargs: object) -> list[RawResult]:
        self.calls.append(query)
        await asyncio.sleep(self.delay)
        return []


def test_budget_stops_hanging_engine_and_switches_to_fallback() -> None:
    """上游引擎一直不返回时，预算用完应提前切兜底，而不是把管理员一直挂着。"""
    fake = SlowSearXNG(delay=5.0)
    cfg = SearchConfig()
    cfg.data["themes"] = {"人与社会": {"queries": ["q1", "q2", "q3"], "keywords": []}}
    cfg.data["rss_sources"] = [
        {"name": "中新网·社会", "url": "https://www.chinanews.com.cn/rss/society.xml"}
    ]
    cfg.settings.searxng_total_budget = 1.0  # 预算耗尽得快，单测不用真等
    pipeline = SearchPipeline(client=fake, config=cfg)  # type: ignore[arg-type]

    class _FakeRss:
        async def fetch(self, url: str, *, source: str = "") -> list:
            from app.clients.rss import RssItem

            return [
                RssItem(
                    title="社区志愿者暖心服务",
                    url="https://www.chinanews.com.cn/sh/1.shtml",
                    content="内容",
                    source=source,
                    published_at=datetime(2026, 11, 11, tzinfo=timezone.utc),
                )
            ]

    pipeline.rss_client = _FakeRss()  # type: ignore[assignment]

    started = time.monotonic()
    outcome = run(pipeline.run(theme="人与社会"))
    elapsed = time.monotonic() - started

    assert elapsed < 3.0  # 没有等满 3 条 Query × 5 秒
    assert outcome.budget_exhausted is True
    assert outcome.fallback_used is True
    assert len(outcome.candidates) == 1
    assert fake.calls == ["q1"]  # 只执行了第一条 Query
