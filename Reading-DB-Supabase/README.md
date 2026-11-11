# Reading-DB-Supabase

共享数据底座：Postgres + Supabase 托管，配置 RLS 行级安全做权限隔离。

依据 `docs/prd.md`。本项目**只负责存储与权限控制**，不含业务代码。

## 数据表

| 表 | 说明 |
| --- | --- |
| `source_log` | 素材梗概表：`source_fingerprint`(SHA256，唯一索引) / `source_summary` / `create_at` / `remark` |
| `articles` | 阅读文章表：标题、难度、主题、文体、标签色、双语段落 JSONB、发布日、排序、是否发布、素材外键 |

## 索引

- `source_log.source_fingerprint` — UNIQUE（素材查重依据）
- `articles.publish_date` — 日历按日期查询
- `articles (theme, level, style)` — 复合索引，筛选加速
- `articles.source_id` — 素材库「关联跳转」
- `articles (publish_date, sort) WHERE is_published` — 前端主查询的部分索引

## RLS 权限

| 角色 | `source_log` | `articles` |
| --- | --- | --- |
| `anon`（前端 publishable key） | 完全禁止（HTTP 401） | 仅 `SELECT`，且只暴露 `is_published = true` 的行 |
| `authenticated` + 管理员邮箱 | 全部读写 | 全部读写（含未发布草稿） |
| `service_role`（两个后端服务） | 全部读写 | 全部读写 |

管理员判定函数 `public.is_admin()` 读数据库级参数 `app.admin_emails`（逗号分隔的邮箱名单）。
名单默认为空 ⇒ 没有任何 authenticated 用户具备管理员权限。要启用：

```sql
-- 以数据库属主身份执行
alter role postgres in database postgres set "app.admin_emails" = 'you@example.com';
```

## 本地运行

```powershell
npm install -g supabase      # 若尚未安装
supabase start               # 首次会拉镜像（postgres / kong / gotrue / postgrest）
supabase status              # 查看 Project URL 与 Publishable / Secret key
supabase stop
```

`supabase start` 会自动应用 `supabase/migrations/` 下的迁移并导入 `supabase/seed.sql`。

> 本项目 `supabase/config.toml` 里关掉了 studio / storage / realtime / analytics / edge-runtime，
> 只保留 db + api + auth，减少镜像下载量与内存占用。

## 迁移文件

- `supabase/migrations/20261111140000_init_reading_schema.sql` —— 建表、索引、外键、RLS 策略、管理员函数
- `deploy/online_setup.sql` —— **在线托管版一键脚本**：建表 + RLS + 种子数据合成一份，
  粘到 Supabase 控制台 → SQL Editor 执行即可（可重复执行）

## 在线托管版

```powershell
# 方式 A：CLI（可重复执行）
supabase link --project-ref <ref>
cd Reading-DB-Supabase; supabase db push

# 方式 B：控制台 SQL Editor —— 整份粘贴 deploy\online_setup.sql
```

灌完表必须验证（表不存在时 REST 会报 `PGRST205`，前端一片空白）：

```powershell
py -3.12 scripts\check_prod_connectivity.py
```

## 权限自测

```powershell
py -3.12 -m pip install httpx     # 首次，自测脚本用到 httpx
py -3.12 scripts\verify_rls.py
# 在线版：指定配置文件
py -3.12 scripts\verify_rls.py --env Reading-DB-Supabase\.env.production
```

覆盖：anon 只能读已发布文章 / 读不到 `source_log` / 写入被拒 / service_role 全权 / 外键生效。

## 给其他项目的配置

| 项目 | 变量 | 取值 |
| --- | --- | --- |
| 前端 | `VITE_SUPABASE_URL` | `supabase status` 的 Project URL |
| 前端 | `VITE_SUPABASE_ANON_KEY` | Publishable（anon）key —— **绝不能放 service_role** |
| 两个后端服务 | `SUPABASE_URL` | 同上 |
| 两个后端服务 | `SUPABASE_SERVICE_ROLE_KEY` | Secret（service_role）key |

## 边界

- ❌ 不含业务代码、接口逻辑
- ❌ 收藏、阅读打卡状态存在浏览器 localStorage，不入库
