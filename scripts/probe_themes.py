"""四个主题各检索一次，统计耗时与候选分布，验证主题区分度与检索预算。

用法：.\\Reading-Material-Crawler-Service\\.venv\\Scripts\\python.exe scripts\\probe_themes.py
输出：.runtime\\theme_probe.json
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / ".runtime" / "theme_probe.json"
CRAWLER = "http://127.0.0.1:8020/api/v1/search"
THEMES = ["人与自我", "人与社会", "人与自然", "人与科技"]


def probe(theme: str, time_range: str = "week", keyword: str = "") -> dict:
    payload = {"theme": theme, "time_range": time_range, "keyword": keyword}
    started = time.monotonic()
    try:
        resp = httpx.post(CRAWLER, json=payload, timeout=300)
        elapsed = round(time.monotonic() - started, 1)
        data = resp.json()
    except Exception as exc:  # noqa: BLE001
        return {"theme": theme, "seconds": round(time.monotonic() - started, 1), "error": str(exc)}

    cands = data.get("candidates") or []
    return {
        "theme": theme,
        "seconds": elapsed,
        "http_status": resp.status_code,
        "count": len(cands),
        "fallback_used": data.get("fallback_used"),
        "budget_exhausted": data.get("budget_exhausted"),
        "keyword_unmatched": data.get("keyword_unmatched"),
        "sources_used": data.get("sources_used"),
        "dropped": data.get("dropped"),
        "errors": data.get("errors"),
        "top5": [c.get("title") for c in cands[:5]],
        "titles": [c.get("title") for c in cands],
        "urls": [c.get("url") for c in cands],
    }


def main() -> int:
    results = [probe(t) for t in THEMES]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    for r in results:
        print(f"=== {r['theme']} | {r.get('seconds')}s | 候选 {r.get('count')} 条 ===")
        if r.get("error"):
            print(f"  错误: {r['error']}")
            continue
        print(f"  fallback_used={r.get('fallback_used')} budget_exhausted={r.get('budget_exhausted')}")
        print(f"  来源: {', '.join(r.get('sources_used') or [])}")
        print(f"  过滤: {r.get('dropped')}")
        for e in r.get("errors") or []:
            print(f"  err: {e}")
        for i, t in enumerate(r.get("top5") or [], 1):
            print(f"  {i}. {t}")
        print()

    # 主题区分度：两两之间 Top5 标题的重合度
    print("=== 主题区分度（Top5 标题重合数）===")
    for i, a in enumerate(results):
        for b in results[i + 1 :]:
            sa, sb = set(a.get("top5") or []), set(b.get("top5") or [])
            print(f"  {a['theme']} vs {b['theme']}: {len(sa & sb)}")
    print(f"\n结果已写入 {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
