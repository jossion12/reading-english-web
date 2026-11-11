"""生成合格率探针（指定素材）：对同一份梗概连跑 N 次，统计各校验项通过率。

用法：.\\Reading-Article-Generate-Service\\.venv\\Scripts\\python.exe scripts\\probe_gen_quality.py [次数] [source_id]
"""

from __future__ import annotations

import statistics
import sys
import time

import httpx

GEN = "http://127.0.0.1:8010/api/v1/generate/preview"
CRAWLER = "http://127.0.0.1:8020/api/v1/sources"


def main() -> int:
    times = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    source_id = sys.argv[2] if len(sys.argv) > 2 else None

    summary = ""
    if source_id:
        rows = httpx.get(f"{CRAWLER}/{source_id}", timeout=30).json()
        summary = rows.get("source_summary") or rows.get("summary_text") or ""
        print(f"素材 {source_id}：{summary[:80]}…\n")
    else:
        # 默认用库里第一份素材
        rows = httpx.get(f"{CRAWLER}?limit=50", timeout=30).json()
        if not rows:
            print("素材库为空")
            return 1
        summary = rows[0].get("source_summary") or ""
        source_id = rows[0].get("id")
        print(f"素材 {source_id}：{summary[:80]}…\n")

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
        "evergreen": False,
    }

    words: list[int] = []
    ok_word = ok_fab = ok_all = 0
    durations: list[float] = []
    for i in range(times):
        t0 = time.time()
        r = httpx.post(GEN, json=payload, timeout=900)
        dt = time.time() - t0
        durations.append(dt)
        if r.status_code != 200:
            print(f"  #{i+1}: HTTP {r.status_code} {r.text[:160]}")
            continue
        v = r.json()["validation"]
        # ValidationReport.passed 是 property，API 响应里对应的是 ready_to_commit
        passed = r.json().get("ready_to_commit", v.get("passed"))
        words.append(v["word_count"])
        ok_word += 1 if v["word_count_ok"] else 0
        ok_fab += 1 if v["no_fabrication"] else 0
        ok_all += 1 if passed else 0
        flag = "PASS" if passed else "FAIL"
        print(
            f"  #{i+1}: {v['word_count']}词 词数{'✓' if v['word_count_ok'] else '✗'} "
            f"编造{'✓' if v['no_fabrication'] else '✗'} 段落{v.get('para_count')} "
            f"→ {flag} ({dt:.0f}s)"
        )
        for issue in v.get("issues") or []:
            if "编造" not in issue:
                print(f"      · {issue[:150]}")

    n = len(words)
    print(
        f"\n词数合格 {ok_word}/{n} · 无编造 {ok_fab}/{n} · 全通过 {ok_all}/{n} · "
        f"词数中位 {statistics.median(words) if words else '-'} · "
        f"平均耗时 {statistics.mean(durations):.0f}s"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
