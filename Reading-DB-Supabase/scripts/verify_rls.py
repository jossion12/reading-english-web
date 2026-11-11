"""RLS 权限隔离自测：验证 anon 只读已发布文章、读不到 source_log；service_role 全权。

配置从环境变量读，密钥不写死在代码里（避免随仓库泄露）：
    SUPABASE_URL              默认 http://127.0.0.1:54321（本地栈）
    SUPABASE_ANON_KEY         publishable / anon 密钥（前端同款）
    SUPABASE_SERVICE_ROLE_KEY service_role 密钥

用法：
    # 本地栈
    py -3.12 Reading-DB-Supabase\\scripts\\verify_rls.py
    # 在线版（先设好三个环境变量，或用 --env 指定 .env 文件）
    $env:SUPABASE_URL="https://xxx.supabase.co"
    $env:SUPABASE_ANON_KEY="sb_publishable_..."
    $env:SUPABASE_SERVICE_ROLE_KEY="sb_secret_..."
    py -3.12 Reading-DB-Supabase\\scripts\\verify_rls.py
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ENV = ROOT / ".env"


def load_env_file(path: Path) -> dict[str, str]:
    """从 .env 文件读键值（只认 KEY=VALUE 这种简单格式）。"""
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        values[key.strip()] = val.strip().strip('"').strip("'")
    return values


def resolve_config(env_file: Path | None) -> tuple[str, str, str]:
    """优先级：命令行 --env 文件 > 进程环境变量 > .env 文件 > 本地栈默认值。"""
    file_values = load_env_file(env_file) if env_file else load_env_file(DEFAULT_ENV)

    def pick(key: str, default: str = "") -> str:
        return (os.environ.get(key) or file_values.get(key) or default).strip()

    base = pick("SUPABASE_URL", "http://127.0.0.1:54321").rstrip("/")
    anon = pick("SUPABASE_ANON_KEY") or pick("SUPABASE_PUBLISHABLE_KEY")
    service = pick("SUPABASE_SERVICE_ROLE_KEY")
    return base, anon, service


def main() -> int:
    parser = argparse.ArgumentParser(description="Supabase RLS 权限隔离自测")
    parser.add_argument("--env", type=Path, default=None, help="从指定 .env 文件读配置")
    parser.add_argument("--url", default=None, help="直接指定 Supabase 项目地址")
    args = parser.parse_args()

    base, anon, service = resolve_config(args.env)
    if args.url:
        base = args.url.rstrip("/")

    if not anon or not service:
        print(
            "缺少密钥。请设置环境变量 SUPABASE_ANON_KEY 与 SUPABASE_SERVICE_ROLE_KEY，"
            "\n或在 Reading-DB-Supabase/.env 里写好（也可以用 --env 指定别的文件）。"
        )
        return 2

    api = f"{base}/rest/v1"
    print(f"目标: {api}\n")

    OK, FAIL = "  ✅", "  ❌"
    failures: list[str] = []

    def check(label: str, cond: bool, extra: str = "") -> None:
        print(f"{OK if cond else FAIL} {label}" + (f"  -> {extra}" if extra else ""))
        if not cond:
            failures.append(label)

    def hdrs(key: str) -> dict[str, str]:
        return {"apikey": key, "Authorization": f"Bearer {key}"}

    def get(path: str, key: str, params: dict | None = None):
        return httpx.get(f"{api}/{path}", headers=hdrs(key), params=params, timeout=20)

    print("\n=== 1. anon 读取 articles ===")
    r = get("articles", anon, {"select": "id,title_en,is_published", "order": "publish_date"})
    rows = r.json() if r.status_code == 200 else []
    check("anon SELECT articles 返回 200", r.status_code == 200, f"HTTP {r.status_code}")
    check("anon 能读到文章", len(rows) > 0, f"{len(rows)} 行")
    check(
        "anon 只看到已发布文章",
        all(row["is_published"] is True for row in rows) if rows else False,
        f"is_published 取值: {sorted({row['is_published'] for row in rows}) if rows else 'n/a'}",
    )

    print("\n=== 2. anon 读取 source_log（应当被拒） ===")
    r = get("source_log", anon, {"select": "id"})
    body = r.text[:200]
    check("anon SELECT source_log 被拒（无权限）", r.status_code in (401, 403, 404), f"HTTP {r.status_code} {body}")
    rows2 = r.json() if r.status_code == 200 and r.text.strip() else []
    check("anon 从 source_log 拿不到任何行", len(rows2) == 0, f"{len(rows2)} 行")

    print("\n=== 3. anon 写入 articles（应当被拒） ===")
    r = httpx.post(
        f"{api}/articles",
        headers=hdrs(anon),
        json={"publish_date": "2026-11-01", "title_en": "hack", "title_cn": "hack"},
        timeout=20,
    )
    check("anon INSERT articles 被拒", r.status_code in (401, 403, 404), f"HTTP {r.status_code}")

    print("\n=== 4. anon 修改已发布文章（应当被拒） ===")
    if rows:
        aid = rows[0]["id"]
        r = httpx.patch(
            f"{api}/articles",
            headers=hdrs(anon),
            params={"id": f"eq.{aid}"},
            json={"title_en": "hacked"},
            timeout=20,
        )
        check("anon UPDATE articles 被拒", r.status_code in (401, 403, 404), f"HTTP {r.status_code}")

    print("\n=== 5. service_role 全权 ===")
    r = get("articles", service, {"select": "id,is_published"})
    svc_rows = r.json() if r.status_code == 200 else []
    check("service_role SELECT articles 返回 200", r.status_code == 200, f"HTTP {r.status_code}")
    check(
        "service_role 能看到全部文章（含未发布）",
        len(svc_rows) > 0,
        f"共 {len(svc_rows)} 行",
    )
    r = get("source_log", service, {"select": "id,source_fingerprint"})
    svc_src = r.json() if r.status_code == 200 else []
    check("service_role 能读到 source_log", r.status_code == 200, f"HTTP {r.status_code} {len(svc_src)} 行")

    print("\n=== 6. 外键关联（软检查）===")
    r = get("articles", service, {"select": "id,title_en,source_id", "source_id": "not.is.null"})
    fk_rows = r.json() if r.status_code == 200 else []
    print(f"  ℹ️  articles.source_id 外键关联：{len(fk_rows)} 行为空（新库没有历史文章属正常）")

    print("\n" + "=" * 60)
    if failures:
        print(f"❌ {len(failures)} 项未通过：")
        for f in failures:
            print(f"   - {f}")
        return 1
    print("✅ 全部 RLS 权限校验通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
