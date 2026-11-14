-- =============================================================================
-- P0 语言修复 R5 · articles 增加「读后思考」两列
--
-- 「正向导向」原本被逐句派进阅读正文，导致 8 篇线上文章有 7 篇以面向初一
-- 学生的教育评论结尾。现在它由生成服务单独输出成 reflection_en / reflection_cn，
-- 前端在阅读页折叠展示，正文保持纯新闻文体。
--
-- 两列可空：存量文章与尚未升级的素材都没有读后思考，前端遇到 null 不渲染。
-- RLS 无需改动 —— anon 的 SELECT 策略按行放行，新增列自动落在同一策略下。
-- =============================================================================

alter table public.articles
  add column if not exists reflection_en text,
  add column if not exists reflection_cn text;

comment on column public.articles.reflection_en is '读后思考（英文一句），与正文分离，仅折叠展示';
comment on column public.articles.reflection_cn is '读后思考（中文一句），与正文分离，仅折叠展示';
