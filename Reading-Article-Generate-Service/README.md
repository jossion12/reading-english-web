# Reading-Article-Generate-Service

语篇生成服务：素材梗概 → 中英双语泛读短文 → 自检 → 预览 → 入库。

依据 `docs/prd.md`。默认绑定 `127.0.0.1:8010`，仅内网访问。

## 流程

```
入参(素材梗概/常青主题) → 素材拆成事实清单 → 扩写 Prompt → LLM 生成 → 结构化解析
                                              ↓
                       确定性自检(词数/段落配对/中文纯度) ←── 不合格则回喂重写(最多 4 次)
                                              ↓
                       LLM 二次自检(编造事实/敏感内容/段落对应)
                                              ↓
                       预览(草稿 + 自检报告) → 管理员确认 → 写入 articles
```

## 事实清单：把「凑字数」的编造挤掉

一条梗概真正支撑得了的事实只有 7~8 条，而 L2 要求 4 段 × 4~5 句（16~20 句）。
差额只能靠编造填满 —— 实测模型确实这么干：凭空造出「学生需要帮助」「她从学校出发」
「今天在下雪」，一次自检就挂。

所以扩写前先把梗概按标签拆开（`app/material.py`）：

```
F1. 贵州省黔东南某山区小学教师李雨在暴雪天气独自徒步三小时
F2. 翻越两座山头
F3. 到学生家中进行家访并送上课本
F4. 乡村教育工作者在恶劣天气下仍坚持家访
F5. 保障了偏远山区学生不因天气缺课
F6. 展现教师的责任心与奉献精神
F7. 引导学生理解什么是真正的关爱与坚持
```

再按段派活（叙事事实占前面，意义类事实落结尾），写进 Prompt：

```
- Paragraph 1 (English + Chinese): F1, F2
- Paragraph 2 (English + Chinese): F3
- Paragraph 3 (English + Chinese): F4, F5
- Paragraph 4 (English + Chinese): F6, F7
```

素材自带的「禁止加入内容」也原样传给模型（不得编造教师姓名、学校名称……）。
模型有了明确且有限的活儿，编造空间被压到最小；自检那一侧拿到同一份事实清单，
判定口径也跟着对齐（中文里的 独自 / 没有 / 已经 都是事实，别误判）。

## 快速开始

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\pip.exe install -r requirements.txt
copy .env.example .env      # 填 SUPABASE_SERVICE_ROLE_KEY / LLM_MODEL
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8010
```

接口文档 <http://127.0.0.1:8010/docs>

## 接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/health` | 健康检查 |
| `GET` | `/api/v1/meta` | 难度 / 文体 / 主题 / 子话题 / 默认标签色 |
| `POST` | `/api/v1/generate/preview` | 生成预览（不写库），返回草稿 id + 自检报告 |
| `POST` | `/api/v1/generate/commit` | 按草稿 id 确认入库 |
| `GET` | `/api/v1/generation-logs` | 生成日志（入参梗概 / LLM 原始返回 / 入库状态 / 时间） |
| `GET` | `/api/v1/articles` | 管理端查看文章（service_role，可见未发布） |
| `GET` | `/api/v1/articles/{id}` | 单篇详情 |

### 生成预览

```jsonc
POST /api/v1/generate/preview
{
  "source_id": null,          // 素材 id；常青素材可为 null
  "summary": "",              // 标准化素材梗概文本
  "level": "L2",              // L1 / L2 / L3
  "style": "记叙文",
  "theme": "人与社会",
  "sub_theme": "邻里互助",
  "color_tag": "#E8F1FF",
  "publish_date": "2026-11-11",
  "sort": 0,
  "is_published": true,
  "evergreen": false          // true = 常青模式，不依赖梗概
}
```

响应里的 `validation` 是自检报告，`ready_to_commit` 为 `false` 时说明有未通过项
（词数不达标、中英段落数不一致、中文段落残留英文、编造事实、敏感内容）。
此时要么修正参数重新预览，要么用 `commit` 传 `force: true` 强制入库。

## 难度规格

| 难度 | 词数 | 段落数 | 每段句数 | 每段词数 | 语言要求 |
| --- | --- | --- | --- | --- | --- |
| L1 | 80–120 | 3–5 | 3 | 22–28 | 短句为主（多在 15 词以内），极少从句，词汇常见具体 |
| L2 | 120–180 | 3–5 | 4 | 33–42 | 少量定语/状语从句，对标中考 B 篇 |
| L3 | 180–240 | 4–6 | 4 | 40–46 | 复合句增多，对标中考 C/D 篇 |

「段落数」取 `para_range` 的中值，「每段句数」在 `config/prompts.yaml` 的
`levels.<难度>.sentences_per_para` 里配（**写成单值**，模型才不会往区间上界写），
「每段词数」由 `para_target × 1.1` 算出，是 prompt 里的软约束。

### 长度为什么最后要由代码兜底

小模型（`qwen3.5:9b`）数不准词数，所以一开始把长度控制押在「句数」上。但换到强模型
（`deepseek-flash`）后发现：**同一份素材下模型写出的总词数几乎恒定** —— 素材有多少条事实
它就展开多少，长度由素材决定，不是指令决定。实测把「每段 3–4 句」钉成「exactly 3 句」，
模型只会把句子写更长（L2 从 182 词涨到 208 词）；把每段词数写进 prompt 也会被无视。

所以现在这层硬约束由 `app/trim.py` 兜底：

- 超出难度上限时，从**最长段落尾部整句裁掉**，英文与中文同步裁
- 段落数量不变，中英仍按下标一一对应（前端联动高亮不受影响）
- 只整句裁、不改写、不引入新内容；至少保留每段一句，不产生空段落
- 被裁掉的多半是模型自己加的注水句，裁完反而更干净

自检报告里的 `trimmed` / `trimmed_words` 会记录本次裁剪了多少词。

### 为什么长度控制给的是「句数」而不是「词数」

本机默认模型 `qwen3.5:9b` **数不准词数**。同一素材（120–180 词 / 4 段）做 A/B，每版 3 次：

| 提示词写法 | 合格次数 |
| --- | --- |
| 「每段至少 33 词、约 38 词」 | 1/3 |
| 「每段约 38 词」 | 0/3 |
| 「每段 33–38 词 + 乘法换算」 | 0/3 |
| 「每段约 38 词 + 明确说别早停」 | 0/3 |
| **「每段 4–5 个句子」** | **3/3** |

所以模板里以**句数**为主约束（`levels.<难度>.sentences_per_para`），词数只作参考。
自检反馈里同样必须给出「你写了 N 段，需要 M 段」——小模型少写段落时自己发现不了，
回喂里不点名就会一直错。

同理，「每段几句」模型也只是弱遵循（实际约 2–3 句/段），真正能收敛的是
**回喂闭环**：反馈里写清「差多少词 → 每段补几句」，并把重写次数放宽到 3 次（共 4 轮）。

> 上面的 A/B 是小模型（`qwen3.5:9b`）的结果。**强模型（`deepseek-flash`）上句数杠杆会失效**，
> 甚至反向（钉死句数 → 句子写更长 → 总词数反而涨）。所以现在句数写成单值、
> 每段词数窄带当软约束，真正兜住上限的是 `app/trim.py` 的确定性裁剪。

## Prompt 可配置

`config/prompts.yaml`：

- `expansion` —— 扩写模板（common + levels.L1/L2/L3）
- `evergreen` —— 常青素材模板
- `self_check` —— 二次自检模板

`config/taxonomy.yaml` —— 难度 / 文体 / 主题 / 子话题 / 默认标签色。

改完重启服务生效。模板占位符用 `{{KEY}}`，渲染走 `str.replace`，不会与 JSON 花括号冲突。

## LLM 适配器

```env
LLM_PROVIDER=ollama      # ollama | openai
LLM_BASE_URL=http://127.0.0.1:11434
LLM_MODEL=qwen3.5:9b
LLM_API_KEY=             # openai 兼容模式必填
LLM_THINK=false          # 思考型模型需关闭，否则会混入 reasoning 段
```

`openai` 模式兼容 MiniMax / DeepSeek / OpenAI / vLLM / LM Studio 等所有 OpenAI 兼容接口。

### 生产环境用 DeepSeek

```env
LLM_PROVIDER=openai
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-flash
LLM_API_KEY=sk-xxxxxxxx
LLM_TIMEOUT=300
LLM_THINK=false
LLM_MAX_TOKENS=4096
```

四个注意点：

- **模型名以官网为准**：现役模型是 `deepseek-flash`（DeepSeek-V4.1-Flash-1017）与
  `deepseek-v4-pro`；早期的 `deepseek-chat` 已下线，配了会报错。
  `LLM_BASE_URL` 用官网的 `https://api.deepseek.com`（末尾加 `/v1` 也能用）。
- **思考模式默认是开的**：`LLM_THINK=false` 时适配器会下发 `thinking: {type: disabled}`；
  思考模式下 `temperature` 之类参数不生效。
- **JSON 模式要求 prompt 里出现 `json` 字样**，否则 DeepSeek 会返回 400。
  本项目的模板都含 "JSON"，改模板时别把这句删掉。
  另外 JSON 被输出上限截断时会返回一片空白内容，本服务已按「可重试的偶发失败」处理。
- **云端模型比本机小模型慢**：一篇 L3 文章（含自检与最多 4 轮重写）可能要 1–2 分钟，
  `LLM_TIMEOUT` 不要低于 300 秒。

DeepSeek 对 JSON 的遵循度比 9B 小模型好，但**词数控制仍然不稳**，
所以提示词里的句数约束和重写闭环在云端同样要保留。

## 自检口径

| 检查 | 由谁判定 |
| --- | --- |
| 英文词数是否在难度区间 | **代码计数**（LLM 自报数字会少算十几个词，不可信） |
| 中英段落数是否一致 | 代码 |
| 中文段落是否残留未翻译的英文 | 代码 |
| 是否编造梗概以外的事实 | LLM 二次自检 |
| 是否含敏感/负面内容 | LLM 二次自检 |
| 段落是否真的互为翻译 | LLM 二次自检 |

### 容易踩的坑：把素材里的模糊表述写具体

素材写「到学生家中……送上课本」时，扩写很容易变成「带着**一本重要的**课本」——
「一本」「重要」都是素材里没有的具体化，二次自检会判成编造事实。
提示词里已经加了硬约束（数量与形容词照抄素材措辞），自检口径也明确区分：

- **算编造**：给素材没有的东西加了一个具体值（数量、名字、地点、额外细节）
- **不算编造**：素材本身没说数量的地方（「学生家中」「课本」），单复数怎么说都行；
  漏掉素材里的某个细节也不算编造

自检不通过时，服务会把问题回喂给模型重写（最多 4 次，共 5 轮），
并从多个候选里挑「问题最少 + 词数最贴近区间中值」的那一版。

### 最常被抓住的四类「编造」

提示词规则 5d/5e/5f 已逐条禁掉，判官也会点名具体短语要求删除：

| 偷加的东西 | 典型写法 | 素材原话 |
| --- | --- | --- |
| 原因 / 病假 | the student was sick | 只说学生没去上课 |
| 出发点 | she left her school | 只说到学生家中家访 |
| 修饰语 | new textbooks / big hills | 课本 / 两座山头 |
| 否定句、时间限定、框架 | she did not stay home that day / today / news reports say | 素材里根本没有 |

**字数不够最容易「为了凑长度而编」**，所以提示词给了合法凑长度的手法
（拆句、换个说法复述、把素材的「背景意义」当结尾段），
重写回喂里也只允许这些手法，明确禁止「加更多细节」。

## 日志

`logs/generations.jsonl`，每行一条：入参梗概、LLM 原始返回、自检结果、入库状态、生成时间。

## 测试

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
```

## 边界

- ❌ 不搜索新闻、不调用爬虫
- ❌ 不负责素材查重（查重由采集服务完成）
- ❌ 不提供阅读页面、素材管理页面
