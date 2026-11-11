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

## 功能对照

| PRD | 实现 |
| --- | --- |
| §2.1 日历导航 | `components/Calendar.tsx`：收起/展开（默认收起）、点选日期筛选、只给有文章的日期打点 |
| §2.2 筛选面板 | `components/FilterPanel.tsx`：收起/展开、主题/文体/难度多选、彩色标签取自 `color_tag` |
| §2.3 文章列表卡片 | `components/ArticleCard.tsx`：英文标题、中文标题、主题/难度/文体标签、发布日期、收藏按钮 |
| §2.4 阅读详情页 | `pages/ReaderPage.tsx` |
| §2.5 收藏 | `lib/favorites.ts` + `pages/FavoritesPage.tsx`：localStorage 存储，独立收藏页，可取消收藏 |
| §2.6 响应式 | `index.css` 断点 640px，另有 `prefers-color-scheme` 深色适配 |

### 阅读详情页的三档视图与联动高亮

视图切换：**仅英文 ｜ 仅中文 ｜ 双语同显**。

联动高亮的做法（PRD §2.4-4）：`english_paras` 与 `chinese_paras` 按**数组下标一一配对**。
每段绑一个 `onMouseUp`，在段落内检测到非空选区时记录 `(index, side)`，
另一侧同下标的段落加 `.linked` 高亮。排版固定一套（英文段落在上、中文译文在下），
不提供左右/上下对照版式切换。

按 PRD 要求：**没有**内置生词标注、点击查词弹窗、练习题、解析、思考题。

### 收藏

存浏览器 `localStorage`（key `reading.favorites.v1`），保存整篇文章快照，
即使文章后来下架，收藏页仍能显示。换浏览器或清缓存后数据丢失 —— 这是 PRD 明确的行为。

## 目录

```
src/
├── components/     Calendar / FilterPanel / ArticleCard
├── pages/          HomePage / ReaderPage / FavoritesPage
├── hooks/          useArticles / useFavorites
├── lib/            supabase 客户端、只读查询、收藏存储
├── types.ts        与 articles 表一一对应的类型
└── index.css       全站样式（含深色模式与响应式）
```

## 数据获取

一次拉取全部已发布文章（`limit 1000`），日历打点与多维筛选都在本地内存完成，
交互零往返。阅读详情页单独按 id 取单篇。

## 体积

生产构建约 **122 KB gzip**（react 53.5 + supabase 59.2 + 应用 6 + CSS 2.6）。
vendor 已分包，便于长缓存。
