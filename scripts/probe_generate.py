"""生成服务质量探针：连续跑多个难度，看自检与重写循环的表现。"""

from __future__ import annotations

import sys
import time

import httpx

URL = "http://127.0.0.1:8010/api/v1/generate/preview"


def run(level: str, style: str, theme: str, sub_theme: str, evergreen: bool, source_id=None):
    payload = {
        "level": level,
        "style": style,
        "theme": theme,
        "sub_theme": sub_theme,
        "color_tag": "#E8F1FF",
        "publish_date": "2026-11-11",
        "sort": 9,
        "is_published": True,
        "evergreen": evergreen,
        "source_id": source_id,
    }
    t0 = time.time()
    r = httpx.post(URL, json=payload, timeout=900)
    dt = time.time() - t0
    if r.status_code != 200:
        print(f"{level} {style}: HTTP {r.status_code} ({dt:.0f}s) -> {r.text[:300]}")
        return None
    b = r.json()
    p = b["payload"]
    v = b["validation"]
    print(
        f"{level} {style}: {v['word_count']}词 ok={v['word_count_ok']} "
        f"段落 {len(p['english_paras'])}/{len(p['chinese_paras'])} "
        f"ready={b['ready_to_commit']} ({dt:.0f}s)"
    )
    print(f"   标题: {p['title_en']} / {p['title_cn']}")
    print(f"   issues: {v['issues']}")
    print(f"   EN: {p['english_paras'][0][:150]}")
    print(f"   CN: {p['chinese_paras'][0][:60]}")
    print()
    return b


if __name__ == "__main__":
    cases = [
        ("L1", "记叙文", "人与社会", "邻里互助", True),
        ("L2", "记叙文", "人与社会", "邻里互助", True),
        ("L3", "议论文", "人与自然", "气候变化与日常选择", True),
        ("L2", "说明文", "人与自然", "水循环", True),
    ]
    for lvl, style, theme, sub, eg in cases:
        run(lvl, style, theme, sub, eg)
