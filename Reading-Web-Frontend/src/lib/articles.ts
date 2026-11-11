/** 文章读取（只读）。 */
import { supabase } from "./supabase";
import type { Article } from "../types";

/** 单次拉取上限，够家庭自用规模；超出再分页。 */
const PAGE_SIZE = 1000;

/**
 * 拉取全部已发布文章。
 *
 * 走 anon 密钥，RLS 只放行 is_published = true 的行（Reading-DB-Supabase 迁移）。
 * 一次取全量是为了让日历标记与多维筛选都在本地即时完成，避免频繁往返。
 */
export async function fetchPublishedArticles(): Promise<Article[]> {
  if (!supabase) throw new Error("Supabase 未配置");

  const { data, error } = await supabase
    .from("articles")
    .select(
      "id,publish_date,title_en,title_cn,level,theme,sub_theme,style,color_tag," +
        "english_paras,chinese_paras,sort,is_published,source_id",
    )
    .eq("is_published", true)
    .order("publish_date", { ascending: false })
    .order("sort", { ascending: true })
    .limit(PAGE_SIZE);

  if (error) throw new Error(error.message);
  return (data as unknown as Article[]) ?? [];
}

/** 按 id 读取单篇（阅读详情页用，避免为了读一篇把全量都拉下来）。 */
export async function fetchArticleById(id: string): Promise<Article | null> {
  if (!supabase) throw new Error("Supabase 未配置");

  const { data, error } = await supabase
    .from("articles")
    .select(
      "id,publish_date,title_en,title_cn,level,theme,sub_theme,style,color_tag," +
        "english_paras,chinese_paras,sort,is_published,source_id",
    )
    .eq("id", id)
    .eq("is_published", true)
    .limit(1)
    .maybeSingle();

  if (error) throw new Error(error.message);
  return (data as unknown as Article) ?? null;
}
