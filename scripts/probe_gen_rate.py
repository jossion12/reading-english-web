"""生成服务合格率探针：每档连跑 N 次 preview，看词数落进区间的比例。

用法：.\\Reading-Article-Generate-Service\\.venv\\Scripts\\python.exe scripts\\probe_gen_rate.py [每档次数]
"""

from __future__ import annotations

import statistics
import sys
import time

import httpx

URL = "http://127.0.0.1:8010/api/v1/generate/preview"
RANGE = {"L1": (80, 120), "L2": (120, 180), "L3": (180, 240)}

CASES = [
    ("L1", "记叙文", "人与社会", "邻里互助"),
    ("L2", "记叙文", "人与社会", "邻里互助"),
    ("L3", "议论文", "人与自然", "气候变化与日常选择"),
]


def one(level: str, style: str, theme: str, sub: str) -> tuple[int | str, float]:
    payload = {
        "level": level,
        "style": style,
        "theme": theme,
        "sub_theme": sub,
        "color_tag": "#E8F1FF",
        "publish_date": "2026-11-11",
        "sort": 9,
        "is_published": True,
        "evergreen": True,
        "source_id": None,
    }
    t0 = time.time()
    r = httpx.post(URL, json=payload, timeout=900)
    dt = time.time() - t0
    if r.status_code != 200:
        return f"HTTP{r.status_code}", dt
    b = r.json()
    v = b["validation"]
    return v["word_count"], dt


def main() -> int:
    times = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    for level, style, theme, sub in CASES:
        lo, hi = RANGE[level]
        words: list[int] = []
        times_taken: list[float] = []
        errors = 0
        for _ in range(times):
            w, dt = one(level, style, theme, sub)
            times_taken.append(dt)
            if isinstance(w, int):
                words.append(w)
            else:
                errors += 1
        ok = sum(1 for w in words if lo <= w <= hi)
        print(
            f"{level} [{lo}-{hi}] 合格 {ok}/{len(words)}  词数 {words}  "
            f"中位 {statistics.median(words) if words else '-'}  "
            f"平均耗时 {statistics.mean(times_taken):.0f}s  报错 {errors}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
