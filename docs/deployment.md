# 生产环境部署手册

开发环境用本机 Ollama + 本地 Docker Supabase 栈；生产环境用 DeepSeek 云端模型 + Supabase 在线托管版，前端发布到 GitHub Pages。

本文按顺序走完三步：

1. [Supabase 在线版](#一supabase-在线版) —— 建项目、灌表结构、拿密钥、验权限
2. [后端服务](#二后端服务deepseek--在线-supabase) —— 采集 8020 / 生成 8010 跑在服务器上
3. [前端 → GitHub Pages](#三前端--github-pages) —— CI 自动构建发布

---

## 环境对照表

| | 开发环境（本机） | 生产环境 |
| --- | --- | --- |
| LLM | Ollama `qwen3.5:9b`<br>`http://127.0.0.1:11434` | DeepSeek `deepseek-flash`<br>`https://api.deepseek.com` |
| Supabase | Docker 本地栈 `http://127.0.0.1:54321` | 在线托管版 `https://<ref>.supabase.co` |
| 前端 | `vite dev` → `http://127.0.0.1:5173` | GitHub Pages `https://<user>.github.io/<repo>/` |
| 采集 / 生成服务 | 本机 uvicorn | 服务器上常驻（systemd 或 Docker） |
| 配置模板 | `.env.example` | `.env.production.example` |

两套配置**用同一个服务、同一份代码**，只换环境变量：

```env
# 开发
LLM_PROVIDER=ollama
LLM_BASE_URL=http://127.0.0.1:11434
LLM_MODEL=qwen3.5:9b
LLM_API_KEY=

# 生产
LLM_PROVIDER=openai
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-flash
LLM_API_KEY=sk-xxxxxxxx
LLM_THINK=false          # DeepSeek 思考模式默认开着，结构化任务要显式关
LLM_MAX_TOKENS=4096      # 不给够，JSON 会被截断成空内容
```

`LLM_PROVIDER=openai` 走的是通用 OpenAI 兼容适配器，DeepSeek / MiniMax / OpenAI / vLLM / LM Studio 都能用同一套代码。

> **模型名以官网为准**（<https://api-docs.deepseek.com/quick_start/pricing>）：
> 现役模型是 `deepseek-flash`（DeepSeek-V4.1-Flash-1017）和 `deepseek-v4-pro`；
> 早期的 `deepseek-chat` 已不在模型列表里，配了会直接报错。
> `LLM_BASE_URL` 用官网的 `https://api.deepseek.com`（末尾加 `/v1` 也能用）。
> 另外 DeepSeek 的**思考模式默认是开的**，`LLM_THINK=false` 时适配器会下发
> `thinking: {type: disabled}`；思考模式下 `temperature` 之类参数不生效。

---

## 一、Supabase 在线版

### 1.1 建项目

[Supabase Dashboard](https://supabase.com/dashboard) → New project → 选区域（选离用户近的，延迟低）→ 设数据库密码。

### 1.2 拿三个密钥

项目页 → **Project Settings → API**：

| 键 | 用途 | 给谁 |
| --- | --- | --- |
| Project URL | `https://<ref>.supabase.co` | 三个组件都要 |
| `anon` / publishable key | 前端只读用 | 前端 |
| `service_role` key | 写库用 | 仅两个后端服务 |

> ⚠️ `service_role` 等同于数据库管理员权限，**绝对不能出现在前端代码、GitHub Secrets（除了后端服务的部署环境）或任何提交进版本库的文件里**。

### 1.3 灌表结构

两种方式任选其一。

**方式 A：Supabase CLI（推荐，可重复执行）**

```powershell
# 登录一次
supabase login

# 关联项目（把 <ref> 换成你的项目 ref）
supabase link --project-ref <ref>

# 应用迁移（Reading-DB-Supabase/supabase/migrations/）
cd Reading-DB-Supabase
supabase db push
```

**方式 B：Dashboard 网页**

Project Settings → SQL Editor → 新建查询，把
`Reading-DB-Supabase/supabase/migrations/20261111140000_init_reading_schema.sql`
整份贴进去执行。

迁移会建两张表 `source_log` / `articles`、索引、外键，以及 RLS 策略 —— 严格两表，没有第三张。

### 1.4 可选：灌演示数据

```powershell
cd Reading-DB-Supabase
supabase db execute --file supabase/seed.sql
```

seed.sql 是幂等的（包在 `DO` 守卫里），重复执行不会插重复文章。

### 1.5 验证权限隔离

```powershell
# 在 Reading-DB-Supabase/.env 里填好三个键，或用环境变量
$env:SUPABASE_URL = "https://<ref>.supabase.co"
$env:SUPABASE_ANON_KEY = "<anon 键>"
$env:SUPABASE_SERVICE_ROLE_KEY = "<service_role 键>"

py -3.12 Reading-DB-Supabase\scripts\verify_rls.py
```

预期输出：anon 能读已发布文章、读不到 `source_log`、写入被拒；service_role 全权。

---

## 二、后端服务（DeepSeek + 在线 Supabase）

两个后端是管理用的内部服务，**不需要也不应该暴露到公网**。它们各自监听 127.0.0.1，需要时从服务器本地或 SSH 隧道访问。

### 2.1 准备主机

一台 Linux 主机（Ubuntu 22.04+ / Debian 12+），装 Python 3.12 与 Docker：

```bash
sudo apt update && sudo apt install -y python3.12 python3.12-venv docker.io
```

把仓库 clone 或 rsync 上去，例如 `/opt/reading`。

### 2.2 装依赖、配环境变量

```bash
cd /opt/reading/Reading-Article-Generate-Service
python3.12 -m venv .venv
./.venv/bin/pip install -r requirements.txt
cp .env.production.example .env
vi .env            # 填 DeepSeek key + 在线 Supabase URL / service_role
```

```bash
cd /opt/reading/Reading-Material-Crawler-Service
python3.12 -m venv .venv
./.venv/bin/pip install -r requirements.txt
cp .env.production.example .env
vi .env
```

### 2.3 预检配置

仓库根目录带一个预检脚本，会指出漏改的本地地址、占位符和缺失的密钥：

```bash
cd /opt/reading
py -3.12 scripts/check_prod_config.py Reading-Article-Generate-Service/.env
py -3.12 scripts/check_prod_config.py Reading-Material-Crawler-Service/.env
```

全部输出 `[OK]` 才算通过。

### 2.4 一起部署 SearXNG

采集服务依赖 SearXNG 做检索。它是纯静态服务，和采集服务放同一台机器即可：

```bash
cd /opt/reading/Reading-Material-Crawler-Service/deploy
docker compose up -d searxng          # 监听 127.0.0.1:8080
```

> SearXNG 的上游引擎在部分网络环境下不可用（验证码 / 超时 / JS 壳）。采集服务已内置
> **RSS 直采兜底通道**：SearXNG 拿不到候选时自动改走白名单媒体的 RSS 频道，
> 过滤规则完全一致，管理台会显式提示用了兜底通道。

### 2.5 启动与常驻

用 systemd 拉起两个服务。生成服务示例：

```ini
# /etc/systemd/system/reading-generator.service
[Unit]
Description=Reading Article Generate Service
After=network-online.target

[Service]
Type=simple
User=reading
WorkingDirectory=/opt/reading/Reading-Article-Generate-Service
ExecStart=/opt/reading/Reading-Article-Generate-Service/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8010
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

采集服务同理，把目录、端口换成 `Reading-Material-Crawler-Service` / `8020`。

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now reading-generator reading-crawler
sudo systemctl status reading-generator
```

健康检查：

```bash
curl -s http://127.0.0.1:8010/health
curl -s http://127.0.0.1:8020/health
```

### 2.6 端到端验证

仓库根目录的 E2E 脚本会跑完整条链路（权限 → 采集 → 生成 → 前端只读）：

```bash
cd /opt/reading
./Reading-Article-Generate-Service/.venv/bin/python scripts/e2e_smoke.py
```

脚本默认打的是本地地址，验证线上时用环境变量指向线上：

```bash
export CRAWLER_URL=http://127.0.0.1:8020
export GENERATOR_URL=http://127.0.0.1:8010
export FRONTEND_URL=https://<user>.github.io/<repo>
export SUPABASE_URL=https://<ref>.supabase.co
export SUPABASE_ANON_KEY=<anon 键>
./Reading-Article-Generate-Service/.venv/bin/python scripts/e2e_smoke.py
```

---

## 三、前端 → GitHub Pages

前端是纯静态站点，**只直连 Supabase**，不请求后端服务，所以部署不需要任何 CORS 配置，后端可以一直留在内网。

### 3.1 推送代码

本地仓库已经初始化并提交好了（仓库根有 `.git`，已有一次提交），你只需要在
GitHub 上建一个**空仓库**（不要勾选 README / .gitignore / license），然后：

```powershell
cd <仓库根目录>
git remote add origin https://github.com/<user>/<repo>.git
git branch -M main
git push -u origin main
```

仓库根的 `.gitignore` 已经排除所有 `.env`、`node_modules`、`dist`、`.venv`，密钥不会被推上去。
推送前可以自查一遍：

```powershell
git ls-files | Select-String -Pattern '\.env$|node_modules|\.venv'   # 应该没有输出
```

### 3.2 配 Actions Secrets

仓库 → **Settings → Secrets and variables → Actions** → **New repository secret**：

| Name | Value |
| --- | --- |
| `VITE_SUPABASE_URL` | `https://<ref>.supabase.co` |
| `VITE_SUPABASE_ANON_KEY` | 在线 Supabase 的 publishable / anon 键 |

可选 Variables（Settings → Variables）：

| Name | Value | 说明 |
| --- | --- | --- |
| `VITE_BASE_PATH` | 留空 | 普通 `user.github.io/repo/` 部署时，工作流会用仓库名自动推导成 `/<repo>/` |
| `VITE_BASE_PATH` | `/` | 部署到自定义域名或用户主页根路径时填 `/` |

### 3.3 开启 Pages

仓库 → **Settings → Pages** → Build and deployment → Source 选 **GitHub Actions**。

### 3.4 触发部署

推 `main` 分支即触发 `.github/workflows/deploy-pages.yml`：装依赖 → 类型检查 → 构建 → 上传产物 → 发布。

在仓库 **Actions** 标签页能看进度，成功后 Pages 设置页会显示站点地址。

### 3.5 部署机制说明

| 环节 | 做法 | 为什么 |
| --- | --- | --- |
| 资源路径 | `vite.config.ts` 的 `base` 取 `/<repo>/` | Pages 站点挂在子路径下，绝对路径会 404 |
| 路由 | `BrowserRouter` 的 `basename` 跟随 `import.meta.env.BASE_URL` | 否则 `/read/<id>` 匹配不到路由 |
| 深链 | 构建后把 `index.html` 复制成 `404.html` | Pages 找不到文件时回落 404.html，SPA 才能在原 URL 启动；地址栏保持干净，不需要 `#/xxx` |
| 环境变量 | Vite 在**构建时**把 `VITE_*` 编译进产物 | 所以要配成 Actions Secrets，运行时改不了 |

前端环境变量模板见 `Reading-Web-Frontend/.env.production.example`。

---

## 四、验收清单

部署完成后逐项确认：

- [ ] `curl https://<ref>.supabase.co/rest/v1/articles?apikey=<anon键>` 返回 200 且只看得到已发布文章
- [ ] `verify_rls.py` 全绿
- [ ] 两个后端 `/health` 返回 `ok: true`，且 `llm_model` 显示 `deepseek-flash`
- [ ] 采集服务检索能返回候选（管理台 http://服务器IP:8020/ 或 SSH 隧道）
- [ ] `e2e_smoke.py` 全绿
- [ ] GitHub Pages 站点打开，首页能看到文章列表
- [ ] 点进一篇文章，`/read/<id>` 深链刷新后不 404，中英段落联动高亮正常
- [ ] 收藏刷新后仍在（localStorage）

---

## 五、常见问题

**Pages 打开是空白 / 资源 404**
资源路径少了仓库名前缀。检查 `vite.config.ts` 的 `resolveBase()`：没设 `VITE_BASE_PATH` 时会从 `GITHUB_REPOSITORY` 推导。本地手动 `npm run build` 预览时没有这个变量，要手动设：
`$env:VITE_BASE_PATH="/<repo>"; npm run build`

**深链刷新 404**
`404.html` 没生成。确认 `package.json` 的 build 脚本带 `node scripts/postbuild.mjs`，并检查 `dist/404.html` 是否存在。

**前端读不到数据**
多半是 `VITE_SUPABASE_URL` 填错，或 anon 键不是 publishable 那把。Anon 键在构建时编译进产物，改了要重新跑一次部署。

**DeepSeek 报 400 / JSON 相关错误**
DeepSeek 的 JSON 模式要求 prompt 里出现 `json` 字样。本项目的 Prompt 都含 "JSON"，若报这个错说明自定义 Prompt 被改坏了。
另外两种常见 400：① 模型名过期（`deepseek-chat` 已下线，换 `deepseek-flash`）；
② 输出被 `max_tokens` 截断（JSON 模式下截断会返回一片空白），调大 `LLM_MAX_TOKENS`。

**DeepSeek 返回内容是空白**
JSON 模式的内容被输出上限截断时，DeepSeek 会把非 JSON 部分替换成空格。调大
`LLM_MAX_TOKENS`（默认 4096）即可；本服务已把「解析失败」按可重试的偶发失败处理。

**DeepSeek 超时**
云端模型比本机慢，把 `LLM_TIMEOUT` 调到 300 以上（默认值已是 300）。生成服务一篇 L3 文章可能要跑 1–2 分钟。

**SearXNG 检索 0 候选**
上游引擎在服务器网络环境下同样可能不可用。采集服务会自动切 RSS 兜底通道，管理台会显示提示。若想彻底解决，给 SearXNG 配代理（`deploy/searxng/settings.yml` 的 `outgoing.proxies.yml`）。

**RLS 挡住了 service_role**
`service_role` 键用错了 —— 确认用的是 Dashboard → API 里的 **service_role**（不是 anon、不是 publishable）。新版 Supabase 的密钥格式是 `sb_secret_...` / `sb_publishable_...`，两个服务都要放在 `Authorization: Bearer <key>` 头上。

---

## 六、密钥放哪（速查）

| 密钥 | 允许出现的位置 | 禁止出现的位置 |
| --- | --- | --- |
| Supabase anon / publishable | 前端 `.env`、Actions Secrets `VITE_SUPABASE_ANON_KEY` | —— |
| Supabase service_role | 两个后端的 `.env`（服务器上）、Actions Secrets（若用 Actions 跑后端） | 前端、GitHub 仓库内任何文件、日志 |
| DeepSeek API key | 两个后端的 `.env`（服务器上） | 前端、仓库内任何文件 |
