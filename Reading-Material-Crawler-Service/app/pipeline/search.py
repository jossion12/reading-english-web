"""检索流水线：主题 → 预设 Query → SearXNG → 过滤（PRD §2.1 / §2.2 / §2.3）。

过滤顺序：无效链接 → 域名不在白名单 → 命中黑名单关键词 → 标题过短。

兜底：SearXNG 拿不到候选时（上游引擎在很多网络环境下不可用），改从白名单媒体
自带的 RSS 频道直采，保证管理员总能看到候选列表（PRD §2.8 的兜底要求）。
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from app.clients.rss import RssClient, RssError, RssItem
from app.clients.searxng import RawResult, SearXNGClient, SearXNGError
from app.search_config import SearchConfig, get_search_config


def _domain_of(url: str) -> str:
    from app.clients.crawler import domain_of

    return domain_of(url)


def _recency(item: RssItem) -> float:
    """排序用：越新越大（无日期记 0）。"""
    return item.published_at.timestamp() if item.published_at else 0.0


def _parse_published(value: str | None) -> datetime | None:
    """解析 SearXNG 的 publishedDate，解析不了返回 None（当作「发布时间未知」）。

    SearXNG 各引擎给的日期格式不统一：ISO（2026-11-12T08:30:00）、带空格的
    秒级时间戳、只有日期（2026-11-12）都出现过，所以这里逐个试。
    """
    if not value:
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed: datetime | None = None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d"):
            try:
                parsed = datetime.strptime(text, fmt)
                break
            except ValueError:
                continue
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


@dataclass
class Candidate:
    """候选新闻卡片（PRD §2.2 字段）。"""

    title: str
    url: str
    summary: str = ""
    domain: str = ""
    published_date: str | None = None
    engine: str = ""
    score: float = 0.0
    query: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "url": self.url,
            "summary": self.summary,
            "domain": self.domain,
            "published_date": self.published_date,
            "engine": self.engine,
            "score": self.score,
            "query": self.query,
        }


@dataclass
class SearchOutcome:
    candidates: list[Candidate] = field(default_factory=list)
    queries: list[str] = field(default_factory=list)
    dropped: dict[str, int] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    exhausted: bool = False  # 无合格素材 —— 触发兜底提示（PRD §2.8）
    sources_used: list[str] = field(default_factory=list)  # 实际生效的检索通道
    fallback_used: bool = False  # 是否走了 RSS 兜底通道
    keyword_unmatched: bool = False  # 关键词没命中任何候选
    budget_exhausted: bool = False  # SearXNG 阶段用完时间预算，提前切兜底

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidates": [c.to_dict() for c in self.candidates],
            "queries": self.queries,
            "dropped": self.dropped,
            "errors": self.errors,
            "exhausted": self.exhausted,
            "sources_used": self.sources_used,
            "fallback_used": self.fallback_used,
            "keyword_unmatched": self.keyword_unmatched,
            "budget_exhausted": self.budget_exhausted,
        }


class SearchPipeline:
    def __init__(
        self,
        client: SearXNGClient | None = None,
        config: SearchConfig | None = None,
        rss_client: RssClient | None = None,
    ) -> None:
        self.client = client or SearXNGClient()
        self.config = config or get_search_config()
        self.rss_client = rss_client or RssClient()

    async def run(
        self,
        *,
        theme: str,
        time_range: str = "week",
        keyword: str | None = None,
        max_results: int | None = None,
    ) -> SearchOutcome:
        queries = self.config.build_queries(theme, keyword)
        limit = max_results or int(self.config.filters.get("max_results", 30))
        min_title = int(self.config.filters.get("min_title_length", 8))
        keep_without_summary = bool(self.config.filters.get("keep_without_summary", True))

        outcome = SearchOutcome(queries=queries)
        seen: set[str] = set()
        dropped = {"invalid_url": 0, "not_whitelisted": 0, "blacklist": 0, "short_title": 0, "duplicate": 0, "too_old": 0}

        searx_range = self.config.searxng_time_range(time_range)
        # 时效窗口：SearXNG 实例不一定支持 time_range 参数（不支持的引擎会被整个跳过），
        # 所以本地再按 publishedDate 兜一道，与 RSS 通道保持同一口径。
        window_days = self.config.window_days(time_range)
        now = datetime.now(timezone.utc)

        # SearXNG 阶段总时间预算：上游引擎全挂时，每条 Query 都要等满超时，
        # 管理员会干等好几分钟。预算用完就提前切到 RSS 兜底通道。
        budget = float(self.config.settings.searxng_total_budget)
        deadline = time.monotonic() + budget

        for query in queries:
            if len(outcome.candidates) >= limit:
                break
            remaining = deadline - time.monotonic()
            if remaining <= 0.5:
                outcome.budget_exhausted = True
                outcome.errors.append(
                    f"SearXNG 检索时间预算 {budget:.0f}s 已用尽，剩余 {len(queries)} 条 Query 未执行"
                )
                break
            try:
                raw_results, degrade_note = await self._search(query, searx_range, deadline)
            except asyncio.TimeoutError:
                outcome.budget_exhausted = True
                outcome.errors.append(
                    f"Query「{query}」超过 {budget:.0f}s 检索预算，提前切换兜底通道"
                )
                break
            except SearXNGError as exc:
                outcome.errors.append(f"Query「{query}」失败: {exc}")
                continue
            if degrade_note:
                outcome.errors.append(degrade_note)

            for raw in raw_results:
                candidate = self._to_candidate(raw, query)
                if candidate is None:
                    continue
                if not self.config.is_valid_url(candidate.url):
                    dropped["invalid_url"] += 1
                    continue
                if not self.config.is_whitelisted(candidate.url):
                    dropped["not_whitelisted"] += 1
                    continue
                hit = self.config.hit_blacklist(candidate.title, candidate.summary)
                if hit:
                    dropped["blacklist"] += 1
                    continue
                if len(candidate.title) < min_title:
                    dropped["short_title"] += 1
                    continue
                if not candidate.summary and not keep_without_summary:
                    dropped["short_title"] += 1
                    continue
                published = _parse_published(candidate.published_date)
                if window_days and published is not None:
                    if published < now - timedelta(days=window_days):
                        dropped["too_old"] += 1
                        continue
                if candidate.url in seen:
                    dropped["duplicate"] += 1
                    continue
                seen.add(candidate.url)
                outcome.candidates.append(candidate)
                if len(outcome.candidates) >= limit:
                    break

        outcome.dropped = dropped

        # --- 兜底通道：SearXNG 没产出候选时改走白名单站点 RSS 直采 ---------
        if not outcome.candidates:
            await self._run_rss_fallback(
                outcome,
                theme=theme,
                time_range=time_range,
                keyword=keyword,
                limit=limit,
                min_title=min_title,
                seen=seen,
            )

        outcome.exhausted = not outcome.candidates
        return outcome

    # ------------------------------------------------------------------
    # SearXNG 单条 Query
    # ------------------------------------------------------------------
    async def _search(
        self,
        query: str,
        searx_range: str | None,
        deadline: float,
    ) -> tuple[list[RawResult], str | None]:
        """跑一条 Query，返回 (结果, 降级说明)。

        带 time_range 搜不到时自动降级重试一次不限时。不同 SearXNG 实例的引擎池
        对 time_range 的支持度不一样：SearXNG 会跳过没开 time_range_support 的引擎，
        碰上这种实例，带参数反而一条都搜不出来。降级后由本地 publishedDate 兜时效。
        """
        remaining = deadline - time.monotonic()
        if remaining <= 0.5:
            raise asyncio.TimeoutError
        results = await asyncio.wait_for(
            self.client.search(query, time_range=searx_range),
            timeout=remaining,
        )
        if results or not searx_range:
            return results, None

        remaining = deadline - time.monotonic()
        if remaining <= 0.5:
            raise asyncio.TimeoutError
        results = await asyncio.wait_for(self.client.search(query), timeout=remaining)
        if not results:
            return results, None
        return results, (
            f"Query「{query}」的 time_range={searx_range} 未被该 SearXNG 实例支持，"
            "已降级为不限时检索（改由本地 publishedDate 过滤时效）"
        )

    # ------------------------------------------------------------------
    # RSS 兜底通道
    # ------------------------------------------------------------------
    async def _run_rss_fallback(
        self,
        outcome: SearchOutcome,
        *,
        theme: str,
        time_range: str,
        keyword: str | None,
        limit: int,
        min_title: int,
        seen: set[str],
    ) -> None:
        sources = self.config.rss_sources
        if not sources:
            return

        tokens = [t for t in (keyword or "").split() if len(t) >= 2]
        theme_keywords = self.config.theme_keywords(theme)
        window_days = self.config.window_days(time_range)
        now = datetime.now(timezone.utc)

        scored: list[tuple[int, RssItem, str]] = []
        for src in sources:
            try:
                items = await self.rss_client.fetch(src["url"], source=src["name"])
            except RssError as exc:
                outcome.errors.append(f"RSS 源「{src['name']}」失败: {exc}")
                continue
            outcome.sources_used.append(src["name"])

            for item in items:
                if not item.title or not item.url:
                    continue
                if item.url in seen:
                    outcome.dropped["duplicate"] += 1
                    continue
                if not self.config.is_valid_url(item.url):
                    outcome.dropped["invalid_url"] += 1
                    continue
                if not self.config.is_whitelisted(item.url):
                    outcome.dropped["not_whitelisted"] += 1
                    continue
                hit = self.config.hit_blacklist(item.title, item.content)
                if hit:
                    outcome.dropped["blacklist"] += 1
                    continue
                if len(item.title) < min_title:
                    outcome.dropped["short_title"] += 1
                    continue
                if window_days and item.published_at is not None:
                    if item.published_at < now - timedelta(days=window_days):
                        outcome.dropped["too_old"] += 1
                        continue
                scored.append((self._score(item, tokens, theme_keywords), item, src["name"]))

        if not scored:
            return

        # 管理员显式给了关键词时优先只留命中的；一个都没命中就把最新的也给出，
        # 免得管理员面对空列表（并在响应里标记 keyword_unmatched）。
        if tokens:
            matched = [row for row in scored if row[0] >= 2]
            if matched:
                scored = matched
            else:
                outcome.keyword_unmatched = True

        # 全局排序：相关度优先，其次越新越靠前
        scored.sort(key=lambda row: (-row[0], -_recency(row[1])))

        # 每源配额，避免单一频道刷屏
        cap = max(3, limit // 3)
        used: dict[str, int] = {}
        seen_titles: set[str] = set()
        for score, item, source in scored:
            # 同一条新闻常被多个频道同时推送，去重键要用 URL + 标题两把
            if item.url in seen:
                outcome.dropped["duplicate"] += 1
                continue
            title_key = "".join(item.title.split())
            if title_key in seen_titles:
                outcome.dropped["duplicate"] += 1
                continue
            if used.get(source, 0) >= cap:
                continue
            used[source] = used.get(source, 0) + 1
            seen.add(item.url)
            seen_titles.add(title_key)
            outcome.candidates.append(
                Candidate(
                    title=item.title,
                    url=item.url,
                    summary=item.content,
                    domain=_domain_of(item.url),
                    published_date=item.published_date,
                    engine=item.engine,
                    query="",
                )
            )
            if len(outcome.candidates) >= limit:
                break
        outcome.fallback_used = True

    @staticmethod
    def _score(item: RssItem, tokens: list[str], theme_keywords: list[str]) -> int:
        """候选相关度：标题命中 3 分 / 摘要命中 2 分 / 主题关键词命中 1 分。"""
        title = item.title
        blob = f"{item.title} {item.content}"
        score = 0
        for token in tokens:
            if token in title:
                score = max(score, 3)
            elif token in blob:
                score = max(score, 2)
        for word in theme_keywords:
            if word in title or word in blob:
                score = max(score, 1)
        return score

    # ------------------------------------------------------------------
    def _to_candidate(self, raw: RawResult, query: str) -> Candidate | None:
        from app.clients.crawler import domain_of

        if not raw.url:
            return None
        return Candidate(
            title=raw.title,
            url=raw.url,
            summary=raw.content,
            domain=domain_of(raw.url),
            published_date=raw.published_date,
            engine=raw.engine,
            score=raw.score,
            query=query,
        )
