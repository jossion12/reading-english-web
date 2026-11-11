"""采集链路探针：真实新闻 URL → 清洗 → 梗概 → 查重 → 入库 → 重复入库阻断。"""

from __future__ import annotations

import sys
import time

import httpx

CRAWLER = "http://127.0.0.1:8020"


def summarize(url: str) -> dict | None:
    t0 = time.time()
    r = httpx.post(f"{CRAWLER}/api/v1/summarize", json={"url": url}, timeout=900)
    print(f"-- summarize {url}")
    print(f"   HTTP {r.status_code}  ({time.time()-t0:.0f}s)")
    if r.status_code != 200:
        print("   ", r.text[:400])
        return None
    return r.json()


def main() -> int:
    urls = sys.argv[1:] or [
        "https://www.chinanews.com.cn/gn/2026/11-10/10729476.shtml",
    ]
    for url in urls:
        body = summarize(url)
        if not body:
            continue
        s = body["summary"]
        print(f"   清洗引擎: {body['crawl_engine']}")
        print(f"   标题: {s['title']}")
        print(f"   核心事实: {s['core_facts'][:120]}")
        print(f"   背景意义: {s['background'][:80]}")
        print(f"   正向导向: {s['positive_direction'][:80]}")
        print(f"   禁止加入: {s['forbidden'][:80]}")
        print(f"   负面内容: {s['negative']} {s['negative_reason']}")
        print(f"   指纹: {body['fingerprint'][:16]}…  重复={body['duplicated']}")

        # 入库
        c = httpx.post(
            f"{CRAWLER}/api/v1/sources",
            json={
                "summary_text": s["text"],
                "fingerprint": body["fingerprint"],
                "remark": f"探针素材 · {url}",
            },
            timeout=60,
        )
        print(f"   入库 HTTP {c.status_code}", c.json().get("id") if c.status_code == 200 else c.text[:200])

        # 重复入库应被阻断
        d = httpx.post(
            f"{CRAWLER}/api/v1/sources",
            json={"summary_text": s["text"], "fingerprint": body["fingerprint"]},
            timeout=60,
        )
        print(f"   重复入库 HTTP {d.status_code}（应为 409）-> {d.text[:120]}")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
