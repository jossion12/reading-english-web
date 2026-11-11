"""素材指纹与检索过滤的单元测试（不触网）。"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.pipeline.dedupe import (
    compute_fingerprint,
    extract_source_url,
    normalize_summary,
    normalize_url,
)
from app.pipeline.summarize import parse_summary
from app.search_config import SearchConfig, SearchConfigError


# ------------------------------------------------------------------ 指纹 ---
def test_normalize_removes_formatting_noise() -> None:
    a = normalize_summary("新闻标题：测试\n\n核心事实：  内容   内容  ")
    b = normalize_summary("新闻标题：测试\r\n\r\n核心事实：内容 内容")
    # 连续空格被压缩，行首尾空白被去掉
    assert "内容   内容" not in a
    assert a.endswith("内容 内容")
    # 忽略空白后两者等价
    assert re.sub(r"\s+", "", a) == re.sub(r"\s+", "", b)


def test_fingerprint_is_stable_across_whitespace() -> None:
    a = compute_fingerprint("素材 A\n\n素材 B")
    b = compute_fingerprint("素材 A\r\n素材 B   ")
    assert a == b
    assert len(a) == 64


def test_fingerprint_differs_by_level_in_summary_level_mode() -> None:
    text = "同一份梗概"
    a = compute_fingerprint(text, mode="summary_level", level="L1")
    b = compute_fingerprint(text, mode="summary_level", level="L2")
    c = compute_fingerprint(text, mode="summary", level="L1")
    d = compute_fingerprint(text, mode="summary", level="L2")
    assert a != b
    assert c == d


# -------------------------------------------------------------- 来源链接 ---
def test_extract_source_url_from_remark() -> None:
    assert (
        extract_source_url("探针素材 · https://www.chinanews.com.cn/gn/2026/11-10/10729476.shtml")
        == "https://www.chinanews.com.cn/gn/2026/11-10/10729476.shtml"
    )
    # 中文标点紧跟链接时不算链接的一部分
    assert (
        extract_source_url("来源：https://example.com/a.html。")
        == "https://example.com/a.html"
    )
    assert extract_source_url("只有一句备注，没有链接") is None
    assert extract_source_url("") is None


def test_normalize_url_ignores_scheme_www_and_trailing_slash() -> None:
    a = normalize_url("https://www.chinanews.com.cn/gn/2026/11-10/10729476.shtml")
    b = normalize_url("http://chinanews.com.cn/gn/2026/11-10/10729476.shtml")
    c = normalize_url("https://www.chinanews.com.cn/gn/2026/11-10/10729476.shtml#top")
    assert a == b == c


def test_normalize_url_keeps_different_paths_apart() -> None:
    a = normalize_url("https://example.com/news/1.html")
    b = normalize_url("https://example.com/news/2.html")
    assert a != b


# ------------------------------------------------------------------ 检索 ---
@pytest.fixture(scope="module")
def config() -> SearchConfig:
    return SearchConfig()


def test_four_themes(config: SearchConfig) -> None:
    assert set(config.theme_names()) == {"人与自我", "人与社会", "人与自然", "人与科技"}


def test_build_queries_uses_keyword(config: SearchConfig) -> None:
    queries = config.build_queries("人与自然", keyword="候鸟迁徙")
    assert queries
    assert any("候鸟迁徙" in q for q in queries)
    assert all("{keyword}" not in q for q in queries)


def test_build_queries_falls_back_when_no_keyword(config: SearchConfig) -> None:
    queries = config.build_queries("人与自然")
    assert queries
    assert all("{keyword}" not in q for q in queries)


def test_build_queries_unknown_theme_raises(config: SearchConfig) -> None:
    with pytest.raises(SearchConfigError):
        config.build_queries("人与宇宙")


def test_whitelist_matches_subdomain(config: SearchConfig) -> None:
    assert config.is_whitelisted("https://news.cctv.com/2026/10/20/ARTI.shtml")
    assert config.is_whitelisted("https://www.news.cn/2026-10/20/c_1.html")
    assert not config.is_whitelisted("https://evil.example.com/news")
    assert not config.is_whitelisted("https://cctv.com.evil.net/x")


def test_blacklist_matches_title_and_summary(config: SearchConfig) -> None:
    assert config.hit_blacklist("某地发生事故") == "事故"
    assert config.hit_blacklist("好消息", "警方破获一起犯罪案件") == "犯罪"
    assert config.hit_blacklist("学生获得科技创新奖") is None


def test_invalid_url_detection(config: SearchConfig) -> None:
    assert config.is_valid_url("https://news.cn/a")
    assert not config.is_valid_url("ftp://news.cn/a")
    assert not config.is_valid_url("javascript:alert(1)")
    assert not config.is_valid_url("")


def test_time_range_mapping(config: SearchConfig) -> None:
    assert config.searxng_time_range("day") == "day"
    assert config.searxng_time_range("week") == "week"
    assert config.searxng_time_range("month") == "month"


# ------------------------------------------------------------------ 梗概 ---
def test_parse_summary_fields() -> None:
    raw = (
        "新闻标题：山区教师雨雪天家访\n"
        "核心事实：教师李雨冒雪走了三小时山路。\n"
        "背景意义：保障了偏远山区学生不因天气缺课。\n"
        "正向导向：展现教师的责任心与奉献精神。\n"
        "禁止加入内容：具体教师姓名、补助金额。\n"
    )
    summary = parse_summary(raw)
    assert summary.title == "山区教师雨雪天家访"
    assert "李雨" in summary.core_facts
    assert summary.negative is False
    assert summary.to_text().startswith("新闻标题：")


def test_parse_summary_detects_negative() -> None:
    raw = (
        "新闻标题：某地火灾\n"
        "核心事实：……\n"
        "背景意义：……\n"
        "正向导向：……\n"
        "禁止加入内容：……\n"
        "负面内容：是（含伤亡细节）\n"
    )
    summary = parse_summary(raw)
    assert summary.negative is True
    assert "伤亡" in summary.negative_reason


def test_parse_summary_requires_title() -> None:
    with pytest.raises(Exception):
        parse_summary("随便一段没有格式的输出")
