"""生产环境配置预检：检查 .env 是否齐全、有没有漏改的本地地址。

用法：
    py -3.12 scripts\\check_prod_config.py Reading-Article-Generate-Service\\.env
    py -3.12 scripts\\check_prod_config.py Reading-Material-Crawler-Service\\.env
    py -3.12 scripts\\check_prod_config.py Reading-Web-Frontend\\.env

只读文件、不打印密钥明文。退出码 0 = 通过，1 = 有问题。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: 出现这些占位符就说明还没改
PLACEHOLDERS = ("YOUR-PROJECT-REF", "sk-xxxxxxxx", "YOUR-PLACEHOLDER", "<", "填")

#: 生产环境不允许出现的本地地址
LOCAL_HINTS = ("127.0.0.1", "localhost", "http://[::1]")

#: 各服务必须配置的键
REQUIRED: dict[str, list[str]] = {
    "generate": [
        "SUPABASE_URL",
        "SUPABASE_SERVICE_ROLE_KEY",
        "LLM_PROVIDER",
        "LLM_BASE_URL",
        "LLM_MODEL",
        "LLM_API_KEY",
    ],
    "crawler": [
        "SUPABASE_URL",
        "SUPABASE_SERVICE_ROLE_KEY",
        "LLM_PROVIDER",
        "LLM_BASE_URL",
        "LLM_MODEL",
        "LLM_API_KEY",
        "SEARXNG_BASE_URL",
    ],
    "frontend": ["VITE_SUPABASE_URL", "VITE_SUPABASE_ANON_KEY"],
    # 数据底座只有 Supabase 密钥，没有 LLM
    "db": ["SUPABASE_URL"],
}

#: 哪些键必须是公网地址（不能指向本机）
MUST_BE_PUBLIC = {
    "SUPABASE_URL",
    "VITE_SUPABASE_URL",
}


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        values[key.strip()] = val.strip().strip('"').strip("'")
    return values


def kind_of(path: Path) -> str:
    text = str(path).lower()
    if "frontend" in text or "web-frontend" in text:
        return "frontend"
    if "crawler" in text or "material" in text:
        return "crawler"
    if "db-supabase" in text or "db_supabase" in text:
        return "db"
    return "generate"


def mask(value: str) -> str:
    if len(value) <= 12:
        return "***"
    return f"{value[:6]}…{value[-4:]}（{len(value)} 字符）"


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1

    path = Path(sys.argv[1])
    if not path.is_absolute():
        path = ROOT / path
    if not path.exists():
        print(f"[FAIL] 配置文件不存在: {path}")
        return 1

    kind = kind_of(path)
    env = read_env(path)
    problems: list[str] = []
    notes: list[str] = []

    print(f"检查 {path}（{kind}）\n")

    for key in REQUIRED.get(kind, []):
        value = env.get(key)
        if not value:
            problems.append(f"缺少 {key}")
            continue
        if any(p in value for p in PLACEHOLDERS):
            problems.append(f"{key} 还是占位符（{mask(value)}）")
            continue
        if key in MUST_BE_PUBLIC and any(h in value for h in LOCAL_HINTS):
            problems.append(f"{key} 仍指向本机（{value}），生产必须指向在线 Supabase")
            continue
        print(f"  [OK]   {key} = {mask(value)}")

    # LLM 适配器一致性
    provider = env.get("LLM_PROVIDER", "").lower()
    base = env.get("LLM_BASE_URL", "")
    model = env.get("LLM_MODEL", "")
    if provider == "openai" and base and not base.startswith("https://"):
        problems.append(f"LLM_PROVIDER=openai 时 LLM_BASE_URL 应为 https（当前 {base}）")
    if provider == "openai" and "deepseek" in base:
        if not base.startswith("https://api.deepseek.com"):
            problems.append(
                f"DeepSeek 地址应为 https://api.deepseek.com（当前 {base}；末尾加 /v1 也能用）"
            )
        if model == "deepseek-chat":
            problems.append(
                "LLM_MODEL=deepseek-chat 已不在 DeepSeek 现行模型列表里，"
                "请改用 deepseek-flash 或 deepseek-v4-pro"
            )
    if provider == "openai" and kind != "frontend" and not env.get("LLM_MAX_TOKENS"):
        notes.append("未设置 LLM_MAX_TOKENS，将用默认 4096（JSON 被截断会返回空内容）")
    if provider == "ollama" and kind != "frontend":
        notes.append("当前仍指向本机 Ollama（开发环境配置）")

    # 前端不能出现 service_role（只看真正生效的配置行，注释里的说明文字不算）
    if kind == "frontend":
        effective = "\n".join(
            line for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        )
        if "service_role" in effective or re.search(r"sb_secret_", effective):
            problems.append("前端配置里出现了 service_role / sb_secret_ 密钥，只读前端绝不能带写权限密钥")

    # 数据库底座：只需要 Supabase 密钥，不该出现 LLM 配置
    if kind == "db":
        if "LLM_API_KEY" in env:
            problems.append("数据底座配置里不需要 LLM_API_KEY，别把模型密钥放进来")
        for key in ("SUPABASE_ANON_KEY", "SUPABASE_PUBLISHABLE_KEY"):
            if env.get(key):
                print(f"  [OK]   {key} = {mask(env[key])}")
                break
        else:
            notes.append("没有 publishable/anon 键：verify_rls.py 需要它来验证「anon 读不到 source_log」")

    for n in notes:
        print(f"  [提示] {n}")
    for p in problems:
        print(f"  [FAIL] {p}")

    if problems:
        print(f"\n结论：{len(problems)} 项待修复")
        return 1
    print("\n结论：配置检查通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
