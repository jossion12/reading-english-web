-- =============================================================================
-- Reading-English-Web · Reading-DB-Supabase
-- 依据 docs/prd.md 第 2~6 节建立共享存储底座
--
--   表 1: source_log  素材梗概表
--   表 2: articles    阅读文章表
--   权限: RLS 行级安全，anon 只读 articles（且仅已发布），管理员全权
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 1. source_log（素材梗概表）
-- -----------------------------------------------------------------------------
create table if not exists public.source_log (
  id                  uuid        primary key default gen_random_uuid(),
  source_fingerprint  text        not null,
  source_summary      text        not null,
  create_at           timestamptz not null default now(),
  remark              text
);

comment on table  public.source_log is '素材梗概表：采集服务产出的标准化素材全文';
comment on column public.source_log.source_fingerprint is 'SHA256 梗概指纹，唯一索引，素材查重依据';
comment on column public.source_log.create_at is '创建时间';
comment on column public.source_log.remark is '备注：来源链接、备注说明';

-- PRD §3.1 —— source_fingerprint UNIQUE 索引
create unique index if not exists source_log_source_fingerprint_uniq
  on public.source_log (source_fingerprint);

-- -----------------------------------------------------------------------------
-- 2. articles（阅读文章表）
-- -----------------------------------------------------------------------------
create table if not exists public.articles (
  id             uuid      primary key default gen_random_uuid(),
  publish_date   date      not null,
  title_en       text      not null,
  title_cn       text      not null,
  level          text      not null check (level in ('L1', 'L2', 'L3')),
  theme          text      not null,
  sub_theme      text,
  style          text      not null,
  color_tag      text      not null check (color_tag ~ '^#[0-9A-Fa-f]{6}$'),
  english_paras  jsonb     not null check (jsonb_typeof(english_paras) = 'array'),
  chinese_paras  jsonb     not null check (jsonb_typeof(chinese_paras) = 'array'),
  "sort"         integer   not null default 0,
  is_published   boolean   not null default false,
  source_id      uuid      references public.source_log (id) on delete set null
);

comment on table  public.articles is '阅读文章表：生成服务产出的中英双语泛读短文';
comment on column public.articles.publish_date is '发布日期，日历查询使用';
comment on column public.articles.level is '难度 L1 / L2 / L3';
comment on column public.articles.theme is '主题大类';
comment on column public.articles.sub_theme is '子话题';
comment on column public.articles.style is '文体：记叙文 / 说明文 / 应用文 / 议论文';
comment on column public.articles.color_tag is '标签颜色色值 #xxxxxx，与后台配置一致';
comment on column public.articles.english_paras is '英文段落数组';
comment on column public.articles.chinese_paras is '中文段落数组';
comment on column public.articles."sort" is '同一天文章排序序号';
comment on column public.articles.is_published is '是否对外展示';
comment on column public.articles.source_id is '外键关联 source_log.id，常青素材可为 null';

-- PRD §3.2 —— publish_date 索引（日历按日期查询）
create index if not exists articles_publish_date_idx
  on public.articles (publish_date);

-- PRD §3.2 —— theme, level, style 复合索引（筛选加速）
create index if not exists articles_theme_level_style_idx
  on public.articles (theme, level, style);

-- 支撑 PRD 2.7「查看该素材已经生成的阅读文章」的关联跳转
create index if not exists articles_source_id_idx
  on public.articles (source_id);

-- 前端主查询：已发布 + 按日期排序。用部分索引精确覆盖。
create index if not exists articles_published_date_sort_idx
  on public.articles (publish_date, "sort")
  where is_published;

-- -----------------------------------------------------------------------------
-- 3. 管理员判定函数
--
-- 管理员 = Supabase Auth 已登录用户（authenticated 角色）且邮箱命中管理员名单。
-- 名单写在数据库级 GUC `app.admin_emails`（逗号分隔），不建额外表，保持 PRD
-- 「仅两张业务表」的边界。默认置空 => 无任何 authenticated 用户获得管理员权限。
--
-- 服务端写入走 service_role 键，本就 BYPASSRLS，不经过本函数。
-- -----------------------------------------------------------------------------
create or replace function public.is_admin()
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select exists (
    select 1
    from unnest(
           string_to_array(
             coalesce(current_setting('app.admin_emails', true), ''),
             ','
           )
         ) as entry(email)
    where btrim(entry.email) <> ''
      and lower(btrim(entry.email)) = lower(coalesce(auth.jwt() ->> 'email', ''))
  );
$$;

comment on function public.is_admin() is '当前请求是否为管理员（authenticated 且邮箱命中 app.admin_emails）';

-- 数据库级默认值：留空表示不启用 authenticated 管理员通道。
-- 用 ALTER ROLE ... IN DATABASE 而不是 ALTER DATABASE —— 迁移以 postgres 角色执行，
-- 它不是数据库属主，ALTER DATABASE 会报 permission denied。
do $$
begin
  execute 'alter role postgres in database postgres set "app.admin_emails" = ' || quote_literal('');
exception when others then
  raise notice '未能设置 app.admin_emails 默认值（管理员通道将保持关闭）: %', sqlerrm;
end;
$$;

-- -----------------------------------------------------------------------------
-- 4. RLS 行级安全策略（PRD §4）
-- -----------------------------------------------------------------------------
alter table public.source_log enable row level security;
alter table public.articles  enable row level security;

-- 显式收回默认权限：anon / authenticated 一律先无表级权限，再按策略精确放行
revoke all on table public.source_log from anon, authenticated;
revoke all on table public.articles  from anon, authenticated;

-- service_role 拥有全部读写（并自带 BYPASSRLS）
grant all on table public.source_log to service_role;
grant all on table public.articles  to service_role;

-- --- source_log ---------------------------------------------------------
-- anon：禁止 SELECT / INSERT / UPDATE / DELETE
--   不建立任何 anon 策略，配合上面的 revoke 实现「完全不可见」；
--   同时把 anon 显式列进策略黑名单，便于后续审计时一眼看懂意图。
create policy "anon_no_access_source_log"
  on public.source_log
  for select
  to anon
  using (false);

-- 管理员：全部读写
create policy "admin_all_source_log"
  on public.source_log
  for all
  to authenticated
  using (public.is_admin())
  with check (public.is_admin());

-- --- articles ------------------------------------------------------------
-- anon：仅允许 SELECT，且只暴露已发布文章
grant select on table public.articles to anon;

create policy "anon_select_published_articles"
  on public.articles
  for select
  to anon
  using (is_published = true);

-- 管理员：全部读写（含未发布草稿）
create policy "admin_all_articles"
  on public.articles
  for all
  to authenticated
  using (public.is_admin())
  with check (public.is_admin());
