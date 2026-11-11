"""针对单条素材复跑生成，检查自检与重写闭环（不写库）。

用法：python scripts/probe_material.py <source_id> [level]

service_role 密钥从环境变量或 Reading-DB-Supabase/.env 读，仓库里不留明文。
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import httpx

PREVIEW = "http://127.0.0.1:8010/api/v1/generate/preview"
REST = "http://127.0.0.1:54321/rest/v1/source_log"
ROOT = Path(__file__).resolve().parent.parent


def _load_key() -> str:
    """依次尝试：环境变量 → Reading-DB-Supabase/.env。"""
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if key:
        return key
    env_file = ROOT / "Reading-DB-Supabase" / ".env"
    if env_file.exists():
        for raw in env_file.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if line.startswith("SUPABASE_SERVICE_ROLE_KEY"):
                _, _, value = line.partition("=")
                return value.strip().strip('"').strip("'")
    print("找不到 service_role 密钥：请设置环境变量 SUPABASE_SERVICE_ROLE_KEY，"
          "或写入 Reading-DB-Supabase/.env")
    raise SystemExit(1)


def main() -> None:
    source_id = sys.argv[1]
    level = sys.argv[2] if len(sys.argv) > 2 else "L2"
    key = _load_key()

    material = httpx.get(
        REST,
        headers={"apikey": key, "Authorization": f"Bearer {key}"},
        params={"id": f"eq.{source_id}", "select": "source_summary"},
        timeout=30,
    ).json()
    if not material:
        print("素材不存在")
        return
    print("素材原文：")
    print(material[0]["source_summary"])
    print()

    payload = {
        "source_id": source_id,
        "level": level,
        "style": "记叙文",
        "theme": "人与自我",
        "sub_theme": "坚持与责任",
        "color_tag": "#E8F1FF",
        "publish_date": "2026-11-11",
        "sort": 9,
        "is_published": True,
    }
    t0 = time.time()
    r = httpx.post(PREVIEW, json=payload, timeout=900)
    dt = time.time() - t0
    if r.status_code != 200:
        print(f"HTTP {r.status_code} ({dt:.0f}s) -> {r.text[:400]}")
        return

    b = r.json()
    p, v = b["payload"], b["validation"]
    print(f"ready={b['ready_to_commit']}  词数={v['word_count']}  ({dt:.0f}s)")
    print(f"标题: {p['title_en']} / {p['title_cn']}")
    print(f"issues: {v['issues']}")
    for i, (en, cn) in enumerate(zip(p["english_paras"], p["chinese_paras"])):
        print(f"EN[{i}] {en}")
        print(f"CN[{i}] {cn}")


if __name__ == "__main__":
    main()
