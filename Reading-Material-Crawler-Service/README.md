# Reading-Material-Crawler-Service

素材采集与素材管理服务：检索 → 清洗 → 梗概 → 查重 → 素材库。

依据 `docs/prd.md`。默认绑定 `127.0.0.1:8020`，仅内网访问。
本服务**只产出素材梗概**，不生成英语阅读短文。

## 快速开始

```powershell
# 1. 本地元搜索
docker compose -f deploy/docker-compose.yml up -d searxng

# 2. 依赖
py -3.12 -m venv .venv
.\.venv\Scripts\pip.exe install -r requirements.txt
copy .env.example .env      # 填 SUPABASE_SERVICE_ROLE_KEY

# 3. 启动
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8020
```

- 管理页面：<http://127.0.0.1:8020/>
- 接口文档：<http://127.0.0.1:8020/docs>

## 内置素材库管理页面

服务自带一个零构建的单页管理台（`app/static/`），覆盖 PRD §2.3 / §2.7：

1. **采集**：选主题 + 时间范围 + 关键词 → 检索候选 → 点选一条 → 自动抓取清洗 + 提炼梗概 + 查重 → 填备注 → 确认入库
2. **素材库**：列表、编辑备注、删除、查看该素材已生成的阅读文章
3. **日志**：搜索记录、抓取 URL、查重结果、入库操作

## 接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/health` | 健康检查（含 SearXNG 探活） |
| `GET` | `/api/v1/config` | 主题 / Query 模板 / 时间范围 / 白名单 / 黑名单 |
| `POST` | `/api/v1/search` | 按主题检索候选新闻（PRD §2.1 / §2.2） |
| `POST` | `/api/v1/score` | 全自动打分模式（PRD §2.3 预留扩展） |
| `POST` | `/api/v1/crawl` | Crawl4AI 清洗单个 URL，输出 Markdown 正文 |
| `POST` | `/api/v1/summarize` | 清洗 + LLM 梗概 + 查重，返回预览（不入库） |
| `GET/POST` | `/api/v1/sources` | 素材库列表 / 确认入库 |
| `GET/PATCH/DELETE` | `/api/v1/sources/{id}` | 详情 / 改备注 / 删除 |
| `GET` | `/api/v1/sources/{id}/articles` | 该素材已生成的阅读文章 |
| `GET` | `/api/v1/logs` | 运行日志 |

## 检索

`config/search.yaml` 全部可配：

- **四大主题**（人与自我 / 人与社会 / 人与自然 / 人与科技），每个主题带预设 Query 模板
- **时间范围** day / week / month
- **域名白名单**：央视新闻、新华网、人民网、中新网等正向媒体域名（后缀匹配，`news.cctv.com` 命中 `cctv.com`）
- **关键词黑名单**：命中标题或摘要即丢弃（事故 / 灾害 / 犯罪 / 冲突 …）

过滤顺序：无效链接 → 域名不在白名单 → 命中黑名单 → 标题过短 → URL 去重。

### 关于 SearXNG 引擎可用性

SearXNG 只是**元搜索入口**，真正取结果的是它背后的各个上游引擎。在部分网络环境下：

- `baidu` 会返回验证码页
- `sogou` 在部分镜像版本里有兼容性 bug
- `duckduckgo` / `brave` / `google cse` / `wikipedia` 会超时
- `bing news` 走 JS 渲染，可能返回 0 条

本机实测：容器 IP 下上述引擎基本不可用，检索会返回 0 候选 —— 服务会如实记录
`dropped` / `errors` 并给出「无可用素材，切换备选主题或让上游用常青素材兜底」的提示（PRD §2.8）。

排查与修复：

```powershell
# 看引擎状态
Invoke-RestMethod "http://127.0.0.1:8080/config" | Select-Object -ExpandProperty engines

# 看某个引擎是否报错
docker logs reading-searxng --tail 100
```

- 换用可达的引擎：编辑 `deploy/searxng/settings.yml` 的 `engines:` 段后 `docker compose restart searxng`
- 给 SearXNG 配代理：在 `settings.yml` 的 `outgoing.proxies.yml` 里加代理
- 检索不可用时仍可用：**在管理页直接粘贴一条白名单新闻链接**（`/api/v1/summarize` 支持 `url` 入参），
  抓取 → 梗概 → 查重 → 入库这条链路不受影响

### RSS 直采兜底通道

当 SearXNG 检索**拿不到任何候选**时，服务会自动启用 RSS 直采通道兜底（PRD §2.8 兜底要求）。
它不是替代 SearXNG，而是并列的第二条取数路径，走白名单站点的官方 RSS 订阅源：

- **触发条件**：SearXNG 有响应但候选为空（引擎超时、验证码、JS 壳等），不是「请求失败」
- **过滤规则与主通道完全一致**：域名白名单 → 关键词黑名单 → 标题过短 → URL 去重 → 时间范围
- **排序方式**：全局相关度排序（主题关键词命中权重 + 发布时间），再按来源配额（每源不超过 `limit/3`）摊平，
  避免所有主题返回同一批头条
- **关键词未命中**：仍返回该主题的最新候选，并在响应里用 `keyword_unmatched: true` 显式标注，不给管理员空列表
- **串行限流**：与 SearXNG 一样，串行调用并遵守最小间隔（`RSS_MIN_INTERVAL`），禁止并发

配置项在 `config/search.yaml`：

```yaml
# 兜底通道的 RSS 订阅源（域名天然落在 domain_whitelist 内，不需要额外放行）
rss_sources:
  - name: 中新网·国内新闻
    url: https://www.chinanews.com.cn/rss/china.xml

# 主题关键词在 themes.<主题>.keywords 里定义，用于给候选算相关度
themes:
  人与社会:
    keywords: [社区, 志愿者, 邻里, 公益, 文化]
```

时间范围换算成天数是内置规则（day=1 / week=7 / month=31），不需要配。

接口层面会额外返回兜底状态，**管理台据此显示来源徽章与提示**：

```json
{
  "fallback_used": true,
  "sources_used": ["中新网·国内新闻", "中新网·社会新闻", "..."],
  "keyword_unmatched": false,
  "budget_exhausted": true,
  "candidates": [{ "title": "...", "engine": "rss:中新网·社会新闻", "url": "..." }]
}
```

当前可用源为中新网 9 个频道（`scroll-news / china / importnews / society / finance / world / health / edu / sports`）。
人民网、新华网的 RSS 已停更（内容分别停在 2025-06 / 2022-12），央视 RSS 返回 404，均已从配置中移除。

### 检索时间预算

上游引擎全挂时，每条 Query 都要等满 `SEARXNG_TIMEOUT`，一个主题 3 条 Query 会把管理员干等好几分钟。
所以 SearXNG 阶段有一个**总时间预算** `SEARXNG_TOTAL_BUDGET`（默认 45 秒）：

- 预算按「整轮检索」算，不是每条 Query 各给一份
- 单条 Query 的超时会被压到剩余预算内，不会拖过预算
- 预算耗尽 → 标记 `budget_exhausted: true` → 提前切到 RSS 兜底通道，管理员照样拿到候选
- 响应里会记一条可读错误：`SearXNG 检索时间预算 45s 已用尽，剩余 N 条 Query 未执行`

调参建议：引擎可达时可以把 `SEARXNG_TOTAL_BUDGET` 调大（120 以上），引擎不可达时调小（30 左右）响应更快。

## 网页清洗

`CRAWLER_MODE` 三种模式，`auto` 会依次降级：

| 模式 | 说明 |
| --- | --- |
| `library` | 直接 import 本地 `crawl4ai` 库（`pip install crawl4ai`），最贴近 PRD 描述 |
| `http` | 调用已启动的 Crawl4AI 服务（`deploy/docker-compose.yml` 里已留好注释掉的编排） |
| `builtin` | 内置降级提取器：解析器感知嵌套结构，剥掉导航/广告/页脚/侧栏后取正文 |

清洗后正文短于 `CRAWLER_MIN_CONTENT_LENGTH`（默认 200 字）直接丢弃，返回候选列表重选。

## 梗概提炼与查重

固定模板输出：**新闻标题 / 核心事实 / 背景意义 / 正向导向 / 禁止加入内容**，
并强制「仅使用原文信息，信息不足则省略，禁止编造事实」。

查重有两重判据，命中任意一条即阻断后续入库流程：

| 判据 | 依据 | 挡住的情况 |
| --- | --- | --- |
| 梗概指纹 | 梗概文本的 SHA256（比较时忽略全部空白差异），查 `source_log` 唯一索引 | 同一份梗概重复入库 |
| 来源链接 | 备注里的来源链接归一化后比对（忽略 http/https 与 www. 差异、末尾斜杠、锚点） | 同一篇报道被二次抓取 |

第二重是必要的：同一篇报道抓两次时，LLM 两次提炼的梗概文字会有细微差异，
**指纹不同但链接相同**，只靠指纹会漏检，素材库里就会出现两条同一篇的素材。

来源链接按 PRD §2.7 记在 `remark` 里。管理页抓取时会自动把链接填进备注，
也可以在调用 `/api/v1/sources` 时单独传 `source_url` 字段：

```json
{ "summary_text": "……", "remark": "新华社报道", "source_url": "https://…" }
```

备注里没有链接时，服务会自动把 `source_url` 补进备注，保证后续能按链接查重。

```env
FINGERPRINT_MODE=summary        # summary | summary_level
```

`summary_level` 时指纹 = 梗概 + 难度，同一梗概换难度算不同素材（PRD §2.6 的可选规则）。

## LLM 适配器

与生成服务同构，默认本机 Ollama，可切到任何 OpenAI 兼容接口：

```env
LLM_PROVIDER=ollama
LLM_BASE_URL=http://127.0.0.1:11434
LLM_MODEL=qwen3.5:9b
LLM_THINK=false
```

生产环境用 DeepSeek：

```env
LLM_PROVIDER=openai
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-flash
LLM_API_KEY=sk-xxxxxxxx
LLM_TIMEOUT=300
LLM_THINK=false
LLM_MAX_TOKENS=4096
```

DeepSeek 现役模型是 `deepseek-flash` / `deepseek-v4-pro`，旧的 `deepseek-chat` 已下线；
思考模式默认开着，结构化任务要用 `LLM_THINK=false` 关掉。

DeepSeek 的 JSON 模式要求 prompt 里出现 `json` 字样 —— 梗概提炼模板里写的是
"JSON"，别改掉。完整部署步骤见根目录 [docs/deployment.md](../docs/deployment.md)。

## 限流与稳定性

- SearXNG 调用串行 + 最小间隔（`SEARXNG_MIN_INTERVAL`，默认 2 秒），禁止并发
- SearXNG 阶段有总时间预算（`SEARXNG_TOTAL_BUDGET`，默认 45 秒），超时即切 RSS 兜底
- RSS 直采同样串行 + 最小间隔（`RSS_MIN_INTERVAL`，默认 1 秒）
- 网页抓取全局加锁，串行执行
- 抓取失败返回可读错误，不阻塞主流程

## 测试

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
```

## 边界

- ❌ 不生成英文阅读短文、不做翻译
- ❌ 不提供学生阅读界面
- ❌ 不存储最终双语语篇
- ❌ 不实现文章筛选、日历、收藏功能
