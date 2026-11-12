# AGENTS.md

面向初一学生的中英双语泛读系统：采集 → 生成 → Postgres(RLS) → 只读阅读站，四个子服务串成一条流水线。**代码严格对齐各子项目的 `docs/prd.md`**，改功能先看对应 PRD。

## Setup commands

```powershell
# 依赖：Node ≥ 20（CI 用 24）、Python 3.12、Docker、Ollama(qwen3.5:9b)
.\scripts\start.ps1        # 起全部（Supabase → 采集 → 生成 → 前端）
.\scripts\status.ps1       # 看状态
.\scripts\stop.ps1         # 停全部

# SearXNG / Crawl4AI 由共享栈 searxng-crawl4ai 提供（不在本仓库）
cd <searxng-crawl4ai 目录>; docker compose up -d

# 单独起某个服务
cd Reading-DB-Supabase; supabase start
cd Reading-Material-Crawler-Service; .\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8020
cd Reading-Article-Generate-Service; .\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8010
cd Reading-Web-Frontend; npm install; npm run dev

# 本机另起一套生产模式实例（APP_ENV=production，指向在线 Supabase + DeepSeek）
$env:APP_ENV="production"
cd Reading-Material-Crawler-Service; .\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8021
cd Reading-Article-Generate-Service; .\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8011
```

端口：Supabase 54321(API)/54322(DB)、采集 8020、生成 8010、前端 5173；
依赖服务：SearXNG 8080、Crawl4AI 11235（共享栈 searxng-crawl4ai 提供，缺则分别降级到
RSS 兜底通道 / 内置提取器）、Ollama 11434。
`start.ps1` 会先清端口残留、启动后逐个探活并点名失败服务；SearXNG / Crawl4AI 只探活不代管。

暴露面：公网可达的只有前端站（GitHub Pages）与在线 Supabase REST；
两个后端一律只监听 `127.0.0.1`，CORS 只放行本机（采集：5173/8020，生成：5173/4173），不要对外开。
本地 Supabase 栈的 54321/54322 绑在 `0.0.0.0`（Supabase CLI 发布），共享网络下用
`supabase/config.toml` 的 `[db.network_restrictions]` 或防火墙收紧。

## Project layout

- `Reading-Material-Crawler-Service/` — 素材采集（FastAPI + SearXNG/Crawl4AI），`app/pipeline/` 是 search→summarize→dedupe
- `Reading-Article-Generate-Service/` — 语篇生成与自检入库（FastAPI），`app/generator.py` 是主流程
- `Reading-DB-Supabase/` — schema 与 RLS 策略（`supabase/migrations/`），`supabase/seed.sql` 是演示数据
- `Reading-Web-Frontend/` — 学生阅读站（React 18 + Vite + TS），**只读**
- `scripts/` — 一键启停、端到端冒烟 `e2e_smoke.py`、生产配置预检
- `docs/` — 架构图与部署手册；每个子项目另有自己的 `docs/prd.md`

## Code style

- Python：`from __future__ import annotations` + 全量类型标注；docstring 用中文讲清「为什么」，不只说「是什么」
- Pydantic 模型作数据契约（`app/schemas.py`），字段含义写进字段注释
- 提示词、难度分类、站点白名单全部外置到 `config/*.yaml`，不要硬编码进 Python
- 前端 TS `strict` + `noUnusedLocals`/`noUnusedParameters`；中英文用 `--font-en`/`--font-cn` 两个变量分开选，**栈里禁止出现 `serif`/`sans-serif` 通用族**（通用族命中即截断回退链，汉字就再也拿不到中文字体）
- 前端没有 ESLint/Prettier，风格以 `npm run typecheck` 与既有代码为准

## Testing instructions

```powershell
# 单元测试：必须在对应服务目录下跑（测试用 sys.path 注入服务根）
cd Reading-Article-Generate-Service; .\.venv\Scripts\python.exe -m pytest -q     # 47 项
cd Reading-Material-Crawler-Service; .\.venv\Scripts\python.exe -m pytest -q     # 42 项

# 端到端（需四个服务都在跑）
.\Reading-Article-Generate-Service\.venv\Scripts\python.exe scripts\e2e_smoke.py
```

- 新行为必须补测试，放同服务的 `tests/test_*.py`
- 上线前再跑 `scripts/check_prod_config.py <env文件>`（静态预检）与 `scripts/check_prod_connectivity.py`（真打线上）
- 前端无测试框架，靠 `npm run typecheck` + `npm run build` + 人工过页面

## 不可破的约束

- **前端只读**：代码里不允许出现任何 INSERT/UPDATE/DELETE 路径，前端只拿 anon 密钥；后端用 service_role 写入
- **段落绑定**：`english_paras` 与 `chinese_paras` 按数组下标一一配对，生成阶段强制校验数量一致
- **素材查重是两重判据**：梗概 SHA256 指纹 **+** 来源链接。只靠指纹会把同一篇素材收两遍（LLM 每次提炼措辞不同）
- **开发/生产两套配置**：`APP_ENV` 切 `.env` / `.env.production`，别把两套混着改
- **`.ps1` 存成带 BOM 的 UTF-8**，否则 Windows PowerShell 5.1 按 ANSI 解析中文直接语法报错
- **别用 `$msg | git commit -F -`**：PowerShell 管道会给原生命令加 UTF-8 BOM，污染提交信息首行。写无 BOM 文件再 `git commit -F <file>`
- **停服务要杀进程树 + 按端口兜底**（`taskkill /T` + `Get-NetTCPConnection`），只 `Stop-Process` 父进程会留孤儿占端口
- **`.bat` 必须纯 ASCII + CRLF + 无 BOM**（cmd 按 OEM 码页解析）
- DeepSeek 模型名以官网为准：现役 `deepseek-flash` / `deepseek-v4-pro`，`deepseek-chat` 已下线；思考模式默认开着，模板里用 `LLM_THINK=false` 关掉

## PR & commit conventions

- 分支从 `main` 切，别直接推 main —— 推 main 会触发 GitHub Pages 自动部署
- 提交信息用 conventional commits，正文中文：`feat:` / `fix:` / `ci:` / `docs:`
- 用 `git commit -F <无 BOM 文件>`，不要用管道

## Security

- 绝不入库真实密钥：根 `.gitignore` 已排除所有 `.env` / `.env.production`，只提交 `.example`
- 前端仓库里**绝不能**出现 service_role 密钥（`check_prod_config.py` 会扫出来）
- 后端 service_role 密钥不要拼进日志或异常信息
- 密钥/配置一律从环境变量或 `.env` 读，不写死在代码里
