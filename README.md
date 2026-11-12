# Reading-English-Web

面向初一学生的**中英双语泛读**系统。四个子项目组成一条完整流水线：

```
Reading-Material-Crawler-Service   采集：检索 → 清洗 → 梗概 → 查重 → 素材库
              │  素材梗概 (source_log)
              ▼
Reading-Article-Generate-Service    生成：扩写 → 自检 → 预览 → 入库
              │  双语文章 (articles)
              ▼
Reading-DB-Supabase                 数据底座：Postgres + RLS 权限隔离
              │  anon 只读
              ▼
Reading-Web-Frontend                展示：日历 / 筛选 / 列表 / 联动高亮 / 收藏
```

| 子项目 | 技术栈 | 默认端口 | 职责 |
| --- | --- | --- | --- |
| `Reading-DB-Supabase` | Postgres 17 + RLS | 54321 (API) / 54322 (DB) | 两张表、索引、外键、行级安全策略 |
| `Reading-Material-Crawler-Service` | Python 3.12 + FastAPI | 8020 | 素材采集与素材库管理（管理员） |
| `Reading-Article-Generate-Service` | Python 3.12 + FastAPI | 8010 | 语篇生成与自检入库 |
| `Reading-Web-Frontend` | React 18 + Vite + TS | 5173 | 学生阅读站点（只读） |

每个子项目都有自己的 `docs/prd.md`，本仓库代码严格对齐各自 PRD。

**开发用本机 Ollama + 本地 Docker Supabase，生产用 DeepSeek + Supabase 在线托管版，前端发布到 GitHub Pages**
—— 同一套代码，只换环境变量。完整部署步骤见 [docs/deployment.md](docs/deployment.md)。

| | 开发环境（本机） | 生产环境 |
| --- | --- | --- |
| LLM | Ollama `qwen3.5:9b` | DeepSeek `deepseek-flash`（`https://api.deepseek.com`） |
| Supabase | Docker 本地栈 `127.0.0.1:54321` | 在线托管版 `https://<ref>.supabase.co` |
| 前端 | `vite dev` → `127.0.0.1:5173` | GitHub Pages `https://<user>.github.io/<repo>/` |
| 配置模板 | 各服务 `.env.example` | 各服务 `.env.production.example` |

### 服务与端口

**对外提供（公网可达的只有两个）**

| 服务 | 地址 | 说明 |
| --- | --- | --- |
| 学生阅读站（前端） | `https://<user>.github.io/<repo>/`（443） | GitHub Actions 推 main 自动构建发布；**首屏读同域 `articles.json` 快照，不请求后端** |
| Supabase 在线托管版 REST | `https://<ref>.supabase.co`（443） | 数据底座。anon 键只能 `SELECT` 已发布文章，读不到 `source_log`，写入一律被 RLS 拒 |

**内网服务（只监听 `127.0.0.1`，不对外暴露）**

| 服务 | 默认端口 | 用途 |
| --- | --- | --- |
| 素材采集服务 | 8020 | 管理员；自带素材库管理页面 `/` 与接口文档 `/docs` |
| 语篇生成服务 | 8010 | 管理员；接口文档 `/docs` |
| 前端 `vite dev` | 5173 | 本地开发 |
| Supabase 本地栈 REST（kong） | 54321 | 开发环境前后端访问 |
| Supabase 本地栈 Postgres | 54322 | 直连调试 |

两个后端的 CORS 只放行 `127.0.0.1` / `localhost`（采集服务：5173、8020；
生成服务：5173、4173，即 vite dev 与 vite preview），所以它们部署到服务器后也只在本机监听，
不需要反代、不需要额外鉴权。

**依赖的外部服务**

| 服务 | 地址 / 端口 | 用途 | 缺失时的行为 |
| --- | --- | --- | --- |
| SearXNG 元搜索 | `127.0.0.1:8080` | 检索候选新闻 | 自动切 RSS 兜底通道（白名单媒体直采） |
| Crawl4AI 网页清洗 | `127.0.0.1:11235` | 正文清洗（**可选**） | `CRAWLER_MODE=auto` 自动降级到内置提取器 |
| Ollama | `127.0.0.1:11434` | 开发环境 LLM | 改 `LLM_PROVIDER=openai` 切 DeepSeek |
| DeepSeek | `api.deepseek.com`（443） | 生产环境 LLM | —— |
| 白名单新闻站 | 出网 | 抓取素材正文 | —— |

> **SearXNG 与 Crawl4AI 由共享栈 `searxng-crawl4ai` 提供**（同机三个容器：
> `searxng`:8080 / `crawl4ai`:11235 / `api`:8000），本仓库不再自带这两个容器 ——
> 两个 SearXNG 抢同一个 8080 端口只会有一台能起来，另一台直接
> `port is already allocated`。共享栈没起也不影响本项目：检索走 RSS 兜底通道，
> 清洗走内置降级提取器。
>
> Crawl4AI 0.9.x 默认开 Bearer 鉴权，采集服务 `.env` 里的 `CRAWLER_API_TOKEN`
> 要和共享栈 `.env` 里的 `CRAWL4AI_API_TOKEN` 是同一个值，否则抓取一律 401。

> ⚠️ 本地 Supabase 栈的 54321 / 54322 由 Supabase CLI 发布到 `0.0.0.0`，
> **局域网内其他机器能连上**（SearXNG 则显式绑 `127.0.0.1`）。只在本机开发时无妨，
> 共享网络下用 `supabase/config.toml` 的 `[db.network_restrictions]` 限制来源 CIDR，
> 或在防火墙里拦掉这两个端口 —— 详见 `Reading-DB-Supabase/README.md`。

---

## 快速开始

### 0. 依赖

- Node ≥ 20、Python 3.12、Docker（跑本地 Supabase / SearXNG）
- 本机 Ollama（默认 LLM 后端）：`ollama pull qwen3.5:9b`

### 1. 起数据底座

```powershell
cd Reading-DB-Supabase
npm install -g supabase          # 若尚未安装
supabase start                   # 首次会拉镜像，约 3-5 分钟
supabase status                  # 记下 Publishable / Secret 两个 key
```

迁移与种子数据会在 `supabase start` 时自动应用。校验权限隔离：

```powershell
py -3.12 -m pip install httpx     # 首次，自测脚本用到 httpx
py -3.12 scripts\verify_rls.py
```

### 2. 起采集服务

```powershell
# ① 先起共享依赖栈（SearXNG + Crawl4AI，在 searxng-crawl4ai 仓库里）
cd <searxng-crawl4ai 所在目录>
docker compose up -d          # searxng:8080 / crawl4ai:11235 / api:8000

# ② 再起采集服务
cd <回到本仓库>\Reading-Material-Crawler-Service
py -3.12 -m venv .venv
.\.venv\Scripts\pip.exe install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8020
```

采集服务读 `.env`（复制自 `.env.example`）。要连共享栈的 Crawl4AI 容器，
把共享栈 `.env` 里的 `CRAWL4AI_API_TOKEN` 填到本服务 `.env` 的 `CRAWLER_API_TOKEN`。

> 独立部署（这台机器上没有共享栈）时，用本仓库自带的编排：
> `docker compose -f deploy/docker-compose.yml --profile standalone up -d searxng`
> —— `--profile standalone` 是必须的，否则它不会启动（默认不启，避免和共享栈抢端口）。

管理页面：<http://127.0.0.1:8020/>

### 3. 起生成服务

```powershell
cd Reading-Article-Generate-Service
py -3.12 -m venv .venv
.\.venv\Scripts\pip.exe install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8010
```

接口文档：<http://127.0.0.1:8010/docs>

### 4. 起前端

```powershell
cd Reading-Web-Frontend
npm install
npm run dev
```

站点：<http://127.0.0.1:5173/>

### 一键启动 / 停止

```powershell
.\scripts\start.ps1        # 起全部
.\scripts\stop.ps1         # 停全部
.\scripts\status.ps1       # 看状态
```

> `start.ps1` 启动前会先清掉占用 5173 / 8010 / 8020 的残留进程，启动后逐个探活并
> 点名失败的服务；`stop.ps1` 杀进程树 + 按端口兜底，避免留下占着端口的孤儿进程。
> 脚本存为带 BOM 的 UTF-8，Windows PowerShell 5.1 与 PowerShell 7 都能直接运行。

### 按日采集工作流（Bing 新闻 + 本机代理）

Bing 新闻垂直引擎依赖本机代理 `jumengcloudCore`（监听 `127.0.0.1:7892`）。
共享栈 `searxng-crawl4ai/docker-compose.yml` 已给 `searxng` 注入
`HTTP_PROXY` / `HTTPS_PROXY` / `NO_PROXY`，`bing news` 引擎已启用。每天的顺序：

```powershell
# ① 先打开代理客户端（7892 开始监听），再起共享栈 SearXNG
cd <searxng-crawl4ai 所在目录>
docker compose up -d searxng
docker compose ps                  # 确认 healthy

# ② 起本项目服务（start.ps1 只探活共享栈，不代管它的生命周期）
cd <回到本仓库>
.\scripts\start.ps1
# 浏览器打开 http://127.0.0.1:5173/ ：找素材 → 打分/提炼 → 生成服务预览并 commit

# ③ 用完先停共享栈容器，再关代理客户端
cd <searxng-crawl4ai 所在目录>
docker compose stop searxng
cd <回到本仓库>
.\scripts\stop.ps1
```

几个容易踩的点：

- 代理是**按请求实时连接**的，环境变量只是固定地址。代理重新打开后**不需要重建容器**，
  `docker compose up -d --force-recreate` 只在改过 compose 时才需要（改环境变量不能靠 `restart`）。
- 代理关闭期间若 `searxng` 仍在运行，所有引擎（含国内引擎）都会 `curl(7) over proxy` 失败；
  但 `healthz` 走 `NO_PROXY=127.0.0.1,localhost,::1`，仍返回 200 —— 容器**看起来 healthy 实则不可用**，
  共享栈的其他使用方也会受影响。所以务必先停容器再关代理。
- `start.ps1` / `stop.ps1` 有意不代管共享栈（见脚本注释），别以为 `stop.ps1` 会停掉 SearXNG。
- 代理没开仍能采集：检索会自动切到 `config/search.yaml` 的 RSS 直采兜底，只是没有 Bing 新闻结果。
  实测代理开启时 Bing 贡献约 8~11 条候选/主题。
- `config/search.yaml` 每个主题末尾的 `site:` 限定 Query 让 Bing 结果落在
  `domain_whitelist` 内（实测命中 10/10），因此**不需要放宽媒体白名单**。

---

## 端到端冒烟测试

需要四个服务都已启动：

```powershell
# 脚本依赖 httpx，直接复用生成服务的虚拟环境
.\Reading-Article-Generate-Service\.venv\Scripts\python.exe scripts\e2e_smoke.py
```

依次验证：数据底座权限隔离 → 采集检索/清洗/梗概/查重/入库 → 生成预览/自检/入库 → 前端只读链路。

单独排查采集检索用这两个探针：

```powershell
# 四个主题各检索一次，看耗时、兜底状态、候选分布和主题区分度
.\Reading-Material-Crawler-Service\.venv\Scripts\python.exe scripts\probe_themes.py

# 抓一条白名单新闻，验证「抓取 → 梗概 → 查重 → 入库」链路
.\Reading-Material-Crawler-Service\.venv\Scripts\python.exe scripts\probe_material.py

# 三档各生成若干次，看词数落进难度区间的比例（质量回归用）
.\Reading-Article-Generate-Service\.venv\Scripts\python.exe scripts\probe_gen_rate.py 5
```

---

## 设计要点

**权限隔离**：前端只拿 Supabase publishable（anon）密钥。RLS 保证匿名角色
只能 `SELECT` 已发布的 `articles`，对 `source_log` 完全无权限，任何写入都被拒绝。
两个后端服务用 service_role 密钥写入，该角色自带 BYPASSRLS。

**LLM 可插拔**：两个后端服务共用一套适配器，默认本机 Ollama（离线免费），
改环境变量即可切到任何 OpenAI 兼容接口：

```env
LLM_PROVIDER=openai
LLM_BASE_URL=https://your-endpoint/v1
LLM_MODEL=your-model
LLM_API_KEY=sk-xxx
```

**Prompt 可配置**：扩写模板、自检模板、梗概提炼模板全部放在 `config/prompts.yaml`，
白名单/黑名单/Query 模板放在 `config/search.yaml`，改完重启服务生效。

**素材查重是两重判据**：① 梗概文本的 SHA256 指纹（比较时忽略全部空白差异）；
② 来源链接（按 PRD §2.7 存进 `remark`，比较时忽略 http/https、www 前缀与末尾斜杠）。
第二重是必要的：同一篇报道抓两次时，LLM 两次提炼的梗概文字有细微差异、指纹不同，
只靠指纹会让同一篇素材进库两遍。

**段落绑定**：`english_paras` 与 `chinese_paras` 按数组下标一一配对，生成阶段强制校验
两者数量一致；前端阅读页据此实现"选中一侧文字 → 另一侧对应段落高亮"。

**收藏只存本地**：收藏快照存在浏览器 localStorage，不上传云端，换浏览器或清缓存即丢失。

**依赖服务共享化**：SearXNG 与 Crawl4AI 由本机的共享栈 `searxng-crawl4ai` 提供
（`searxng`:8080 / `crawl4ai`:11235 / `api`:8000），本仓库不重复起容器 —— 两个 SearXNG
抢同一个端口只会有一台能起来。采集端做了两层兼容：SearXNG 实例的引擎池不支持
`time_range` 时，自动降级为不限时检索并改由本地按 `publishedDate` 过滤时效；
Crawl4AI 0.9.x 要求 Bearer 鉴权且请求体格式与老版本不同，客户端按 422 回退，两种版本都能跑。

---

## 目录

```
Reading-English-Web/
├── docs/
│   ├── architecture-diagrams.html  流程图 + 时序图（浏览器直接打开，离线可用）
│   └── deployment.md               生产部署手册（Supabase 在线版 / 后端 / Pages）
├── Reading-DB-Supabase/
│   ├── supabase/migrations/     建表 / 索引 / RLS 策略
│   ├── supabase/seed.sql        演示素材与文章
│   └── scripts/verify_rls.py    权限隔离自测
├── Reading-Material-Crawler-Service/
│   ├── app/clients/             SearXNG / Crawl4AI / LLM / Supabase
│   ├── app/pipeline/            search / summarize / dedupe
│   ├── app/static/              内置素材库管理页面
│   └── deploy/                  独立部署模式用的 SearXNG / Crawl4AI 编排（standalone profile，默认不启动）
├── Reading-Article-Generate-Service/
│   ├── app/clients/             LLM / Supabase
│   ├── app/generator.py         生成 → 自检 → 预览 → 入库
│   ├── config/prompts.yaml      扩写 / 自检模板
│   └── logs/                    生成日志（JSONL）
├── Reading-Web-Frontend/
│   ├── src/
│   │   ├── components/          Calendar / FilterPanel / ArticleCard
│   │   ├── pages/               Home / Reader / Favorites
│   │   └── lib/                 supabase 客户端、收藏存储
│   └── scripts/postbuild.mjs    生成 dist/404.html（SPA 深链回退）
├── .github/workflows/
│   └── deploy-pages.yml         构建前端并发布到 GitHub Pages
└── scripts/                     一键启停 + 端到端冒烟 + 生产配置预检
```

---

## 生产部署

完整步骤见 **[docs/deployment.md](docs/deployment.md)**，三步：

1. **Supabase 在线版** —— 建项目 → `supabase link` + `supabase db push` 应用迁移 → 从 Project Settings → API 拿 URL / anon 键 / service_role 键 → 跑 `verify_rls.py` 验权限隔离
2. **后端服务** —— 服务器上装依赖，拷 `.env.production.example` 填 DeepSeek 密钥 + 在线 Supabase 密钥，用 systemd 常驻；采集服务旁边的 SearXNG 用 `deploy/docker-compose.yml` 一起起
3. **前端 → GitHub Pages** —— 推 main 分支触发 `.github/workflows/deploy-pages.yml`；在 Actions Secrets 里配 `VITE_SUPABASE_URL` 与 `VITE_SUPABASE_ANON_KEY`，Settings → Pages 的 Source 选 GitHub Actions。构建会用 anon 密钥导出 `dist/articles.json` 快照，缺快照时部署直接失败

几个部署前值得知道的事：

- **开发/生产两套配置并存，靠 `APP_ENV` 切换**：后端默认读 `.env`（本机 Ollama + 本地 Docker Supabase），
  `APP_ENV=production` 时读 `.env.production`（DeepSeek + 在线 Supabase）。
  `/health` 里的 `env_file` 字段会告诉你当前到底加载了哪份
- **DeepSeek 的模型名以官网为准**：现役是 `deepseek-flash` / `deepseek-v4-pro`，
  旧的 `deepseek-chat` 已下线；base 用 `https://api.deepseek.com`。
  另外它的**思考模式默认是开的**，模板里已用 `LLM_THINK=false` 显式关掉
- **上线前跑两次自检**：`check_prod_config.py`（静态：占位符/本地地址/老模型名/前端混入 service_role）
  与 `check_prod_connectivity.py`（真实打一次线上接口：表结构在不在、RLS 是否隔离、DeepSeek 能否回话）
- **密钥不写死在代码里**：`verify_rls.py` 与 `e2e_smoke.py` 改成从环境变量 / `.env` 读，
  根 `.gitignore` 排除了所有 `.env`、`node_modules`、`dist`、`.venv`
- **前端首屏读同域文章快照**：构建时 `scripts/export-articles.mjs` 用 anon 密钥把已发布文章导出成
  `dist/articles.json`，随 Pages 一起发布。国内手机网络常连不上 `*.supabase.co`（表现为
  `TypeError: Failed to fetch`、整页 0 篇），浏览器只读同域文件就不受影响；Supabase 退为
  「能连上时」的后台增强，失败静默。工作流每天 20:30（北京）定时重建刷新快照，**缺快照时部署直接失败**，
  避免发出读不到文章的版本。前端始终不请求后端服务，后端可一直留在内网
- **Vite 环境变量在构建时编译进产物**：改了 Supabase 地址要重新跑一次部署才生效
- **Pages 站点挂在子路径**：`vite.config.ts` 的 `base` 自动取 `/<仓库名>/`，
  `BrowserRouter` 的 `basename` 跟着走；深链靠构建时复制出的 `404.html` 回退
- **本地想预览 Pages 效果**：

  ```powershell
  $env:VITE_BASE_PATH="/<仓库名>"
  cd Reading-Web-Frontend; npm run build
  cd ..; .\Reading-Article-Generate-Service\.venv\Scripts\python.exe scripts\serve_pages_preview.py 8099 <仓库名>
  # → http://127.0.0.1:8099/<仓库名>/
  ```

- **上线前跑一次配置预检**：

  ```powershell
  py -3.12 scripts\check_prod_config.py Reading-Article-Generate-Service\.env
  ```
