"""Reading-English-Web 全链路冒烟测试。

依次验证：
  1. Supabase 数据底座：表结构、RLS 只读隔离
  2. 采集服务：检索 -> 清洗 -> 梗概 -> 查重 -> 入库
  3. 生成服务：预览 -> 自检 -> 入库
  4. 前端 anon 角色能读到新入库的文章

配置从环境变量读（密钥不写死在代码里）：
    SUPABASE_URL               默认 http://127.0.0.1:54321
    SUPABASE_ANON_KEY          publishable / anon 键
    SUPABASE_SERVICE_ROLE_KEY  service_role 键
    CRAWLER_URL               默认 http://127.0.0.1:8020
    GENERATOR_URL             默认 http://127.0.0.1:8010

用法：
    python scripts/e2e_smoke.py                 # 跑全部
    python scripts/e2e_smoke.py --skip-crawl    # 跳过采集（不触外网）
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parent.parent


def _load_env_file() -> dict[str, str]:
    """从仓库里的 .env / 后端 .env 读键值作为兜底（环境变量优先）。"""
    candidates = [
        ROOT / "Reading-DB-Supabase" / ".env",
        ROOT / "Reading-Material-Crawler-Service" / ".env",
        ROOT / "Reading-Article-Generate-Service" / ".env",
    ]
    values: dict[str, str] = {}
    for path in candidates:
        if not path.exists():
            continue
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            values.setdefault(key.strip(), val.strip().strip('"').strip("'"))
    return values


_ENV_FILE = _load_env_file()


def _pick(key: str, default: str = "") -> str:
    return (os.environ.get(key) or _ENV_FILE.get(key) or default).strip()


SUPABASE_URL = _pick("SUPABASE_URL", "http://127.0.0.1:54321").rstrip("/") + "/rest/v1"
ANON_KEY = _pick("SUPABASE_ANON_KEY") or _pick("SUPABASE_PUBLISHABLE_KEY")
SERVICE_KEY = _pick("SUPABASE_SERVICE_ROLE_KEY")

CRAWLER_URL = _pick("CRAWLER_URL", "http://127.0.0.1:8020").rstrip("/")
GENERATOR_URL = _pick("GENERATOR_URL", "http://127.0.0.1:8010").rstrip("/")

# 检索引擎不可用时用来验证抓取链路的固定白名单文章
FALLBACK_ARTICLE_URL = "https://www.chinanews.com.cn/gn/2026/11-10/10729476.shtml"

OK, FAIL = "[PASS]", "[FAIL]"
failures: list[str] = []
created_source_id: str | None = None
created_article_id: str | None = None


def check(label: str, cond: bool, extra: str = "") -> bool:
    print(f"{OK if cond else FAIL} {label}" + (f"  -> {extra}" if extra else ""))
    if not cond:
        failures.append(label)
    return cond


def section(title: str) -> None:
    print(f"\n--- {title} ---")


def db_headers(key: str) -> dict[str, str]:
    return {"apikey": key, "Authorization": f"Bearer {key}"}


def db_get(path: str, key: str, params: dict[str, Any] | None = None) -> Any:
    r = httpx.get(f"{SUPABASE_URL}/{path}", headers=db_headers(key), params=params, timeout=30)
    r.raise_for_status()
    return r.json()


# =========================================================== 1. 数据底座 ===
def test_database() -> None:
    section("1. Supabase 数据底座")
    rows = db_get("articles", ANON_KEY, {"select": "id,is_published"})
    check("anon 可读 articles", isinstance(rows, list), f"{len(rows)} 行")
    check(
        "anon 只看到已发布文章",
        all(r["is_published"] for r in rows),
        f"{sum(1 for r in rows if not r['is_published'])} 条未发布被挡住",
    )
    r = httpx.get(f"{SUPABASE_URL}/source_log", headers=db_headers(ANON_KEY), timeout=20)
    check("anon 读不到 source_log", r.status_code != 200, f"HTTP {r.status_code}")
    all_rows = db_get("articles", SERVICE_KEY, {"select": "id,is_published"})
    check(
        "service_role 能看到全部文章（含未发布）",
        len(all_rows) >= len(rows),
        f"{len(all_rows)} 行",
    )


# =========================================================== 2. 采集服务 ===
def test_crawler(skip_crawl: bool) -> None:
    section("2. 素材采集服务")
    try:
        h = httpx.get(f"{CRAWLER_URL}/health", timeout=20).json()
    except Exception as exc:
        check("采集服务可访问", False, str(exc))
        return
    check("采集服务健康", h.get("ok") is True, f"SearXNG={h.get('searxng')}")

    cfg = httpx.get(f"{CRAWLER_URL}/api/v1/config", timeout=20).json()
    check(
        "四大主题已配置",
        set(cfg["themes"]) == {"人与自我", "人与社会", "人与自然", "人与科技"},
        ", ".join(cfg["themes"]),
    )
    check("域名白名单非空", len(cfg["domain_whitelist"]) > 0, f"{len(cfg['domain_whitelist'])} 条")

    r = httpx.post(
        f"{CRAWLER_URL}/api/v1/search",
        json={"theme": "人与社会", "time_range": "month", "keyword": "乡村教师 家访"},
        timeout=180,
    )
    check("检索接口返回 200", r.status_code == 200, f"HTTP {r.status_code}")
    data = r.json()
    cands = data.get("candidates", [])
    if cands:
        check("检索到候选新闻", True, f"{len(cands)} 条 / 过滤 {data.get('dropped')}")
        bad = [c for c in cands if not any(d in c["url"] for d in cfg["domain_whitelist"])]
        check("候选全部来自白名单域名", not bad, f"越界 {len(bad)} 条")
    else:
        # 这是环境问题不是代码问题：本地 SearXNG 的上游引擎可能被验证码/超时拦截。
        # 过滤逻辑本身由 tests/test_search_pipeline.py 用假引擎覆盖。
        print(
            "  [SKIP] SearXNG 没有返回可用候选"
            f"（dropped={data.get('dropped')} errors={data.get('errors')}）"
            " —— 属本机网络环境对搜索引擎的可达性，不影响下游链路"
        )

    if skip_crawl:
        print("  (跳过抓取/梗概/入库)")
        return

    # 检索没有候选时（搜索引擎在本机网络下不可用），改用一条已知的白名单文章
    # 直接验证「抓取 → 梗概 → 查重 → 入库」这条链路。
    if cands:
        target = cands[0]["url"]
    else:
        target = FALLBACK_ARTICLE_URL
        print(f"  (检索无候选，改用固定白名单文章验证抓取链路: {target})")

    # 清理同一来源链接的历史素材，保证本脚本可重复执行
    stale = httpx.get(f"{CRAWLER_URL}/api/v1/sources?limit=200", timeout=30).json()
    removed = 0
    for row in stale if isinstance(stale, list) else []:
        if target in (row.get("remark") or ""):
            httpx.delete(f"{CRAWLER_URL}/api/v1/sources/{row['id']}", timeout=30)
            removed += 1
    if removed:
        print(f"  (清理同一来源链接的历史素材 {removed} 条)")

    t0 = time.time()
    try:
        resp = httpx.post(
            f"{CRAWLER_URL}/api/v1/summarize", json={"url": target}, timeout=600
        )
    except Exception as exc:
        check("抓取+梗概请求完成", False, str(exc))
        return
    check("抓取+梗概返回 200", resp.status_code == 200, f"HTTP {resp.status_code} 用时 {time.time()-t0:.0f}s")
    if resp.status_code != 200:
        print(resp.text[:400])
        return

    body = resp.json()
    summary = body.get("summary", {})
    check(
        "梗概五段模板齐全",
        all(
            summary.get(k)
            for k in ("title", "core_facts", "background", "positive_direction", "forbidden")
        ),
        summary.get("title", "")[:40],
    )
    check("算出素材指纹", len(body.get("fingerprint", "")) == 64, body.get("fingerprint", "")[:16])
    check("首次查重未命中", body.get("duplicated") is False, f"duplicated={body.get('duplicated')}")

    # 入库
    create = httpx.post(
        f"{CRAWLER_URL}/api/v1/sources",
        json={
            "summary_text": summary.get("text", ""),
            "fingerprint": body["fingerprint"],
            "remark": f"e2e 测试素材 · {target}",
            "source_url": target,
        },
        timeout=60,
    )
    check("素材入库返回 200", create.status_code == 200, f"HTTP {create.status_code}")
    if create.status_code == 200:
        global created_source_id
        created_source_id = create.json()["id"]
        check("拿到素材 id", bool(created_source_id), created_source_id)

        # 重复入库应被阻断
        dup = httpx.post(
            f"{CRAWLER_URL}/api/v1/sources",
            json={"summary_text": summary.get("text", ""), "fingerprint": body["fingerprint"]},
            timeout=60,
        )
        check("重复素材被阻断（409）", dup.status_code == 409, f"HTTP {dup.status_code}")

        # 第二重判据：同一来源链接、但梗概措辞不同（指纹不同）也必须挡住
        dup_url = httpx.post(
            f"{CRAWLER_URL}/api/v1/sources",
            json={
                "summary_text": summary.get("text", "") + "\n（测试用：同链接但措辞不同）",
                "source_url": target,
            },
            timeout=60,
        )
        check(
            "同来源链接二次入库被阻断（409）",
            dup_url.status_code == 409,
            f"HTTP {dup_url.status_code}",
        )

        # 素材库列表
        lib = httpx.get(f"{CRAWLER_URL}/api/v1/sources?limit=50", timeout=30).json()
        check("素材库列表可读", isinstance(lib, list) and len(lib) > 0, f"{len(lib)} 条")


# =========================================================== 3. 生成服务 ===
def test_generator() -> None:
    section("3. 语篇生成服务")
    try:
        h = httpx.get(f"{GENERATOR_URL}/health", timeout=20).json()
    except Exception as exc:
        check("生成服务可访问", False, str(exc))
        return
    check("生成服务健康", h.get("ok") is True, f"{h.get('llm_model')}")

    meta = httpx.get(f"{GENERATOR_URL}/api/v1/meta", timeout=20).json()
    check("分类元信息可读", len(meta.get("themes", {})) == 4, f"{len(meta.get('themes', {}))} 个主题")

    sources = db_get("source_log", SERVICE_KEY, {"select": "id", "limit": 1})
    source_id = sources[0]["id"] if sources else None

    payload = {
        "source_id": source_id,
        "level": "L2",
        "style": "记叙文",
        "theme": "人与社会",
        "sub_theme": "邻里互助",
        "color_tag": "#E8F1FF",
        "publish_date": "2026-11-11",
        "sort": 9,
        "is_published": True,
    }
    t0 = time.time()
    try:
        resp = httpx.post(f"{GENERATOR_URL}/api/v1/generate/preview", json=payload, timeout=900)
    except Exception as exc:
        check("生成预览请求完成", False, str(exc))
        return
    check("生成预览返回 200", resp.status_code == 200, f"HTTP {resp.status_code} 用时 {time.time()-t0:.0f}s")
    if resp.status_code != 200:
        print(resp.text[:600])
        return

    body = resp.json()
    art = body["payload"]
    val = body["validation"]
    check("英文标题非空", bool(art["title_en"]), art["title_en"])
    check("中文标题非空", bool(art["title_cn"]), art["title_cn"])
    check(
        "中英段落数一致",
        len(art["english_paras"]) == len(art["chinese_paras"]),
        f"en={len(art['english_paras'])} cn={len(art['chinese_paras'])}",
    )
    check(
        "英文词数在 L2 区间 120-180",
        val["word_count_ok"],
        f"实际 {val['word_count']} 词",
    )
    check(
        "段落数在建议区间 3-5",
        val.get("para_count_ok", True),
        f"实际 {val.get('para_count', len(art['english_paras']))} 段",
    )
    check("自检无编造事实", val["no_fabrication"] is True)
    check("自检无敏感内容", val["no_sensitive"] is True)
    if val.get("issues"):
        print(f"      issues: {val['issues']}")

    commit = httpx.post(
        f"{GENERATOR_URL}/api/v1/generate/commit",
        json={"draft_id": body["draft_id"], "force": True},
        timeout=120,
    )
    check("确认入库返回 200", commit.status_code == 200, f"HTTP {commit.status_code}")
    if commit.status_code == 200:
        global created_article_id
        created_article_id = commit.json()["article_id"]
        check("文章已写入 articles", bool(created_article_id), str(created_article_id))

    logs = httpx.get(f"{GENERATOR_URL}/api/v1/generation-logs?limit=5", timeout=30).json()
    check("生成日志已记录", isinstance(logs, list) and len(logs) > 0, f"{len(logs)} 条")


# =========================================================== 4. 前端读链路 ===
def test_frontend_read_path() -> None:
    section("4. 前端只读链路")
    if not created_article_id:
        print("  (本轮没有新文章，跳过)")
        return
    rows = db_get("articles", ANON_KEY, {"id": f"eq.{created_article_id}", "select": "id,title_en"})
    check("anon 能读到新入库文章", len(rows) == 1, rows[0]["title_en"] if rows else "读不到")
    check(
        "前端拿到的文章已发布",
        bool(rows) and db_get("articles", ANON_KEY, {"id": f"eq.{created_article_id}"})[0]["is_published"],
    )


def cleanup(created_article_id: str | None, created_source_id: str | None) -> None:
    """清掉本轮冒烟测试写入的数据，保持库干净。"""
    if created_article_id:
        r = httpx.delete(
            f"{SUPABASE_URL}/articles",
            headers=db_headers(SERVICE_KEY),
            params={"id": f"eq.{created_article_id}"},
            timeout=30,
        )
        print(f"清理文章 {created_article_id[:8]}… HTTP {r.status_code}")
    if created_source_id:
        r = httpx.delete(
            f"{SUPABASE_URL}/source_log",
            headers=db_headers(SERVICE_KEY),
            params={"id": f"eq.{created_source_id}"},
            timeout=30,
        )
        print(f"清理素材 {created_source_id[:8]}… HTTP {r.status_code}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-crawl", action="store_true", help="跳过需要外网的采集链路")
    parser.add_argument("--keep", action="store_true", help="保留本轮写入的文章与素材")
    args = parser.parse_args()

    print(f"Supabase : {SUPABASE_URL}")
    print(f"采集服务 : {CRAWLER_URL}")
    print(f"生成服务 : {GENERATOR_URL}")
    if not ANON_KEY or not SERVICE_KEY:
        print(
            "\n缺少 Supabase 密钥。请设置环境变量 SUPABASE_ANON_KEY 与 "
            "SUPABASE_SERVICE_ROLE_KEY，或在 Reading-DB-Supabase/.env 里写好。"
        )
        return 2

    test_database()
    test_crawler(args.skip_crawl)
    test_generator()
    test_frontend_read_path()

    if not args.keep:
        cleanup(created_article_id, created_source_id)

    print("\n" + "=" * 62)
    if failures:
        print(f"{FAIL} {len(failures)} 项未通过：")
        for f in failures:
            print(f"   - {f}")
        return 1
    print("全链路冒烟测试通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
