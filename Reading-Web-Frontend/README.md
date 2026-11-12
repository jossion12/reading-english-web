# Reading-Web-Frontend

学生阅读前端站点：**只读应用**，仅通过 Supabase anon 密钥读取 `articles` 表。

依据 `docs/prd.md`。React 18 + Vite + TypeScript。

## 快速开始

```powershell
npm install
copy .env.example .env       # 填 VITE_SUPABASE_URL / VITE_SUPABASE_ANON_KEY
npm run dev
```

站点 <http://127.0.0.1:5173/>

```powershell
npm run build        # 产物到 dist/
npm run preview      # 本地预览产物
npm run typecheck    # 只跑类型检查
```

## 部署到 GitHub Pages

仓库根的 `.github/workflows/deploy-pages.yml` 会在推 `main` 分支时自动构建并发布。

### 1. 配 Actions Secrets

仓库 → **Settings → Secrets and variables → Actions**：

| Name | Value |
| --- | --- |
| `VITE_SUPABASE_URL` | 在线 Supabase 项目地址 |
| `VITE_SUPABASE_ANON_KEY` | publishable / anon 键（**绝不能**放 service_role） |

可选 Variable `VITE_BASE_PATH`：普通 `user.github.io/<repo>/` 部署时留空即可，
工作流会用仓库名自动推导成 `/<repo>/`；自定义域名或用户主页根路径时填 `/`。

### 2. 开启 Pages

**Settings → Pages → Build and deployment → Source** 选 **GitHub Actions**。

### 3. 机制说明

| 环节 | 做法 | 为什么 |
| --- | --- | --- |
| 资源路径 | `vite.config.ts` 的 `base` 取 `/<repo>/` | Pages 挂在子路径下，绝对路径会 404 |
| 路由 | `BrowserRouter` 的 `basename` 跟随 `import.meta.env.BASE_URL` | 否则 `/read/<id>` 匹配不到路由 |
| 深链 | 构建后 `scripts/postbuild.mjs` 复制出 `dist/404.html` | Pages 找不到文件时回落 404.html，SPA 在原 URL 启动；地址栏干净，不用 `#/xxx` |
| 环境变量 | Vite **构建时**把 `VITE_*` 编译进产物 | 改了 Supabase 地址要重新跑一次部署 |

### 本地预览 Pages 效果

```powershell
$env:VITE_BASE_PATH = "/<仓库名>"
npm run build
cd ..
.\Reading-Article-Generate-Service\.venv\Scripts\python.exe scripts\serve_pages_preview.py 8099 <仓库名>
# → http://127.0.0.1:8099/<仓库名>/
```

这个预览服务器会模拟 Pages 的行为：未知路径回落到站点根的 `404.html`。

---

## 权限

前端**只拿 publishable（anon）密钥**。RLS 保证匿名角色：

- 只能 `SELECT articles`，且只拿得到 `is_published = true` 的行
- 对 `source_log` 完全没有权限（HTTP 401）
- 任何 `INSERT` / `UPDATE` / `DELETE` 都会被拒绝

代码里不存在任何写入路径（PRD §4.2）。

## 设计语言「墨与朱」

面向初一学生的阅读站点，视觉上定成**一本摊在课桌上的双语活页本**，而不是一个信息流页面。

| 角色 | 用法 |
| --- | --- |
| 墨（`--cover` #141c2e） | 顶栏与底部导航 = 书本封面，全站唯一的大块深色 |
| 课桌（`--desk`） | 内容区底色，冷灰，白色纸片浮在上面 |
| 纸（`--sheet`） | 文章正文所在的纸面 |
| 朱砂（`--cinnabar`） | 老师的红笔色，只用于收藏星标、阅读进度、当前选中的那一段 |
| 难度冷色阶 | L1 青绿 / L2 靛蓝 / L3 紫，避免和朱砂撞色 |

**签名元素**：阅读页左侧一条贯穿全文的主题色「高亮笔竖轨」（颜色由后台 `color_tag` 派生），
竖轨左边是段号栏，右边英文正文与中文译文共用一栏 —— 中文缩进成边注。
这套栅格在手机、平板、桌面完全一致，不提供左右/上下对照版式切换（PRD §2.4-1）。

截图见仓库 `docs/screenshots/`。

## 功能对照

| PRD | 实现 |
| --- | --- |
| §2.1 日历导航 | `components/Calendar.tsx`：弹层内打开、点选日期筛选、只给有文章的日期打点 |
| §2.2 筛选面板 | `components/FilterPanel.tsx`：主题/文体/难度多选、彩色标签取自 `color_tag`；难度另有常驻快捷条 |
| §2.3 文章列表卡片 | `components/ArticleCard.tsx`：英文标题、中文标题、主题/难度/文体标签、发布日期、收藏按钮、左侧主题色书脊 |
| §2.4 阅读详情页 | `pages/ReaderPage.tsx` |
| §2.5 收藏 | `lib/favorites.ts` + `pages/FavoritesPage.tsx`：localStorage 存储，独立收藏页，可取消收藏 |
| §2.6 响应式 | `index.css` 断点 640px，另有 `prefers-color-scheme` 深色适配 |
| 增补 · 中英文分别换字体 | `components/FontPicker.tsx` + `hooks/useFonts.tsx`：中英文各 6 款系统字体，顶栏 / 底部导航 / 阅读页三处入口 |

### 手机优先的交互

站点主要在手机和平板上被打开，所以下面这些是按触屏重做的：

- **底部标签栏**（≤640px）：文章 / 收藏 / 字体，拇指够得着；平板与桌面沿用顶栏导航
- **点一下就联动高亮**：手机用户几乎不会去划词，划词高亮等于没有。
  现在点任意一段，该段加 `.is-active`（朱砂），配对译文加 `.is-linked`（主题色）；
  桌面端划词仍然可用
- **难度快捷条常驻**：顶部吸顶一行「全部 / L1 较易 / L2 中等 / L3 较难」，
  最常用的筛选不必进抽屉
- **筛选 / 日历 / 字体走弹层**：手机从底部升起，平板与桌面居中成对话框
- **安全区适配**：`env(safe-area-inset-*)` 覆盖刘海屏与底部指示条

### 阅读详情页的三档视图与联动高亮

视图切换：**仅英文 ｜ 仅中文 ｜ 双语同显**，控制条吸顶。

联动高亮的做法（PRD §2.4-4）：`english_paras` 与 `chinese_paras` 按**数组下标一一配对**。
每段同时挂 `onMouseUp`（检测段内非空选区）与 `onClick`（点按），
记录 `(index, side)`，另一侧同下标的段落加 `.is-linked` 高亮。
排版固定一套（英文段落在上、中文译文在下），不提供左右/上下对照版式切换。

顶部有阅读进度条（朱砂色，贴在封面与纸的接缝上），右侧同步显示「已读 N%」。

按 PRD 要求：**没有**内置生词标注、点击查词弹窗、练习题、解析、思考题。

### 收藏

存浏览器 `localStorage`（key `reading.favorites.v1`），保存整篇文章快照，
即使文章后来下架，收藏页仍能显示。换浏览器或清缓存后数据丢失 —— 这是 PRD 明确的行为。

### 中英文分别切换字体

顶栏的「Aa 字体」、手机底部导航的「字体」和阅读页控制条的「Aa 字体」
是同一个面板（`components/FontPicker.tsx`），三处状态实时同步，点一下立即生效。

- **英文字体**（6 款）：Georgia、Times New Roman、Palatino、Segoe UI、Verdana、Courier New
- **中文字体**（6 款）：微软雅黑、宋体、楷体、仿宋、黑体、等线

每个按钮用**该字体本身**渲染自己的名字，所见即所得。

只用**系统自带字体**，不加载任何字体文件：离线可用、包体不变、切换零延迟。
代价是同名字体在不同系统上形态略有差异（Windows / macOS / iOS / Android）。

#### 实现要点：按字符回退

字体栈写在 CSS 变量里，`--font-en` 管西文与数字、`--font-cn` 管汉字，
浏览器逐字符回退，所以英文段落里夹的汉字也会自动用中文字体：

```css
.para-en, .para-cn, .reader-title, .card-title, .sheet-title {
  font-family: var(--font-en), var(--font-cn), serif;
}
```

**两个栈里都不能放 `serif` / `sans-serif` 通用族** —— 通用族一旦命中就会截断后面的回退链，
汉字就再也用不上中文字体了。通用族统一写在规则末尾。

选择存 `localStorage`（key `reading.fonts.v1`），刷新、换页面都保持。
作用范围是**标题与正文**（英文段落、中文译文、标题、卡片标题）；
导航、按钮等界面元素保持系统无衬线字体，避免界面跟着正文换字体而变得难用。

## 目录

```
src/
├── components/     Calendar / FilterPanel / ArticleCard / FontPicker / BottomSheet / Icons
├── pages/          HomePage / ReaderPage / FavoritesPage
├── hooks/          useArticles / useFavorites / useFonts / useReadingProgress
├── lib/            supabase 客户端、只读查询、收藏存储、字体目录、难度元数据
├── types.ts        与 articles 表一一对应的类型
└── index.css       全站样式（含深色模式与响应式）
```

## 数据获取

一次拉取全部已发布文章（`limit 1000`），日历打点与多维筛选都在本地内存完成，
交互零往返。阅读详情页单独按 id 取单篇。

## 体积

生产构建约 **127 KB gzip**（react 53.5 + supabase 59.2 + 应用 9.5 + CSS 5.2）。
vendor 已分包，便于长缓存；无 webfont、无图片资源。
