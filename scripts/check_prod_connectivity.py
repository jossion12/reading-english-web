"""生产配置连通性自检：拿真实密钥打一次线上接口，确认配置能用。

用法：
    py -3.12 scripts\\check_prod_connectivity.py
    py -3.12 scripts\\check_prod_connectivity.py --env-dir Reading-DB-Supabase

检查项：
    1. Supabase 在线版：表结构在不在、anon 能不能读 articles、anon 能不能读 source_log（应该不行）
    2. DeepSeek：密钥能不能用、配置的模型名在不在在线列表里、能不能真的回一句话

只读不写：不往库里插任何数据。密钥不打印明文。
退出码 0 = 全部通过，1 = 有失败项。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent

DEFAULT_FILES = {
    "generate": "Reading-Article-Generate-Service/.env.production",
    "crawler": "Reading-Material-Crawler-Service/.env.production",
    "frontend": "Reading-Web-Frontend/.env.production",
    "db": "Reading-DB-Supabase/.env.production",
}


def read_env(path: Path) -> dict[str, str]:
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


def mask(value: str) -> str:
    if not value:
        return "(空)"
    if len(value) <= 14:
        return "***"
    return f"{value[:6]}…{value[-4:]}"


def check_supabase(env: dict[str, str]) -> list[tuple[bool, str, str]]:
    """检查在线 Supabase：表结构、anon 读权限、RLS 隔离。"""
    results: list[tuple[bool, str, str]] = []
    base = (env.get("SUPABASE_URL") or env.get("VITE_SUPABASE_URL") or "").rstrip("/")
    anon = env.get("SUPABASE_ANON_KEY") or env.get("VITE_SUPABASE_ANON_KEY") or ""
    service = env.get("SUPABASE_SERVICE_ROLE_KEY") or ""

    if not base:
        results.append((False, "Supabase 地址", "配置里没有 SUPABASE_URL"))
        return results
    results.append((True, "Supabase 地址", f"{base}（密钥 {mask(anon)} / {mask(service)}）"))

    # 1) 表结构在不在 + anon 能不能读已发布文章
    try:
        resp = httpx.get(
            f"{base}/rest/v1/articles",
            headers={"apikey": anon, "Authorization": f"Bearer {anon}"},
            params={"select": "id", "limit": 3},
            timeout=20,
        )
    except httpx.HTTPError as exc:
        results.append((False, "anon 读 articles", f"连不上：{exc}"))
        return results

    if resp.status_code == 200:
        rows = resp.json()
        results.append((True, "anon 读 articles", f"HTTP 200，读到 {len(rows)} 行（表结构已就绪）"))
    elif resp.status_code in (404, 400) and "42P01" in resp.text:
        results.append(
            (False, "anon 读 articles", "表不存在 —— 迁移还没灌进在线项目（supabase db push）")
        )
    else:
        results.append((False, "anon 读 articles", f"HTTP {resp.status_code} {resp.text[:160]}"))

    # 2) RLS：anon 不该能读 source_log
    try:
        resp = httpx.get(
            f"{base}/rest/v1/source_log",
            headers={"apikey": anon, "Authorization": f"Bearer {anon}"},
            params={"select": "id", "limit": 1},
            timeout=20,
        )
        if resp.status_code in (401, 403):
            results.append((True, "RLS 隔离 source_log", f"anon 被挡住（HTTP {resp.status_code}）"))
        elif resp.status_code == 200:
            results.append((False, "RLS 隔离 source_log", "anon 竟然能读 source_log，权限配置有误"))
        else:
            results.append((False, "RLS 隔离 source_log", f"HTTP {resp.status_code} {resp.text[:160]}"))
    except httpx.HTTPError as exc:
        results.append((False, "RLS 隔离 source_log", f"连不上：{exc}"))

    # 3) service_role 能读（写库权限链路）
    if service:
        try:
            resp = httpx.get(
                f"{base}/rest/v1/source_log",
                headers={"apikey": service, "Authorization": f"Bearer {service}"},
                params={"select": "id", "limit": 3},
                timeout=20,
            )
            if resp.status_code == 200:
                results.append((True, "service_role 读 source_log", f"HTTP 200，读到 {len(resp.json())} 行"))
            else:
                results.append((False, "service_role 读 source_log", f"HTTP {resp.status_code} {resp.text[:160]}"))
        except httpx.HTTPError as exc:
            results.append((False, "service_role 读 source_log", f"连不上：{exc}"))
    else:
        results.append((False, "service_role 读 source_log", "配置里没有 service_role 密钥"))
    return results


def check_deepseek(env: dict[str, str]) -> list[tuple[bool, str, str]]:
    """检查 DeepSeek：密钥、模型名、能不能真的回一句话。"""
    results: list[tuple[bool, str, str]] = []
    base = (env.get("LLM_BASE_URL") or "").rstrip("/")
    key = env.get("LLM_API_KEY") or ""
    model = env.get("LLM_MODEL") or ""

    if not base or not key:
        results.append((False, "DeepSeek 配置", "缺少 LLM_BASE_URL 或 LLM_API_KEY"))
        return results
    results.append((True, "DeepSeek 地址", f"{base}（模型 {model}，密钥 {mask(key)}）"))

    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

    # 1) 模型列表 —— 顺便验证配置里的模型名是否真的存在
    try:
        resp = httpx.get(f"{base}/models", headers=headers, timeout=20)
        if resp.status_code == 200:
            ids = [m.get("id") for m in resp.json().get("data", [])]
            if model in ids:
                results.append((True, "模型名有效", f"{model} 在在线列表里"))
            else:
                results.append(
                    (False, "模型名有效", f"{model} 不在在线列表 {ids} —— 换用官网现役模型名")
                )
        else:
            results.append((False, "模型名有效", f"HTTP {resp.status_code} {resp.text[:160]}"))
    except httpx.HTTPError as exc:
        results.append((False, "模型名有效", f"连不上：{exc}"))

    # 2) 真的发一次最小请求（max_tokens 给够，否则模型还没说完就被截断成空）
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "Reply with the single word: ok"}],
        "max_tokens": 64,
    }
    try:
        resp = httpx.post(f"{base}/chat/completions", headers=headers, json=payload, timeout=60)
        if resp.status_code == 200:
            data = resp.json()
            got = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            results.append((True, "chat/completions", f"HTTP 200，实际模型 {data.get('model')}，回复「{got.strip()[:20]}」"))
        elif resp.status_code == 401:
            results.append((False, "chat/completions", "密钥无效（401）"))
        else:
            results.append((False, "chat/completions", f"HTTP {resp.status_code} {resp.text[:200]}"))
    except httpx.HTTPError as exc:
        results.append((False, "chat/completions", f"连不上：{exc}"))
    return results


def check_frontend(env: dict[str, str]) -> list[tuple[bool, str, str]]:
    """前端只查配置自洽性（真正上线靠 Actions 构建）。"""
    results: list[tuple[bool, str, str]] = []
    url = env.get("VITE_SUPABASE_URL") or ""
    key = env.get("VITE_SUPABASE_ANON_KEY") or ""
    if not url or not key:
        results.append((False, "前端配置", "缺少 VITE_SUPABASE_URL 或 VITE_SUPABASE_ANON_KEY"))
        return results
    if "sb_secret_" in key:
        results.append((False, "前端密钥类型", "这是 service_role 密钥，绝不能进前端"))
    elif key.startswith("sb_publishable_") or key.startswith("eyJ"):
        results.append((True, "前端密钥类型", "publishable / anon 键，只读权限 ✓"))
    else:
        results.append((False, "前端密钥类型", f"密钥格式不像 publishable/anon：{mask(key)}"))

    base_path = (env.get("VITE_BASE_PATH") or "").strip()
    if base_path and base_path != "/":
        results.append(
            (True, "VITE_BASE_PATH", f"={base_path}（必须是仓库名对应的路径，否则资源 404）")
        )
    else:
        results.append((True, "VITE_BASE_PATH", "留空 → 工作流会按 GITHUB_REPOSITORY 自动推导"))
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="生产配置连通性自检")
    parser.add_argument("--env-dir", default=".", help="存放 .env.production 的根目录")
    parser.add_argument("--only", choices=["supabase", "deepseek", "frontend"], help="只跑某一项")
    args = parser.parse_args()

    env_root = Path(args.env_dir)
    if not env_root.is_absolute():
        env_root = ROOT / env_root

    envs = {name: read_env(env_root / rel) for name, rel in DEFAULT_FILES.items()}
    for name, env in envs.items():
        if not env:
            print(f"[FAIL] 读不到配置：{DEFAULT_FILES[name]}")
            return 1

    sections: list[tuple[str, list[tuple[bool, str, str]]]] = []
    if args.only in (None, "supabase"):
        sections.append(("Supabase 在线版", check_supabase(envs["db"])))
    if args.only in (None, "deepseek"):
        sections.append(("DeepSeek", check_deepseek(envs["generate"])))
    if args.only in (None, "frontend"):
        sections.append(("前端", check_frontend(envs["frontend"])))

    failed = 0
    for title, items in sections:
        print(f"\n=== {title} ===")
        for ok, name, detail in items:
            flag = "PASS" if ok else "FAIL"
            if not ok:
                failed += 1
            print(f"  [{flag}] {name} -> {detail}")

    print("\n" + "=" * 62)
    if failed:
        print(f"结论：{failed} 项未通过")
        return 1
    print("结论：生产配置连通性全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
