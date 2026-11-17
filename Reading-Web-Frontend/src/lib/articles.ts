/**
 * 文章读取（只读、按日期分片按需加载）。
 *
 * 数据源策略：同域静态快照优先，Supabase 只作兜底。
 * GitHub Pages 页面本身能打开，但浏览器直连 *.supabase.co 在部分运营商 /
 * 移动网络下会 DNS 或路由失败，整页报 `TypeError: Failed to fetch`。
 * 构建期已把已发布文章导出到同域 <base>/ 下（见 scripts/export-articles.mjs）：
 *   - articles-index.json    有文章的日期数组（倒序），首屏第一个请求，极小
 *   - articles-<date>.json   每天一个分片，滚动到该日期才请求
 *   - articles.json          全量，仅用于阅读页深链按 id 兜底
 * 首页首屏只取 index + 最新一天分片，避免一次性下载全量 —— 这是加载时效优化。
 */
import { supabase } from "./supabase";
import type { Article } from "../types";

const COLUMNS =
  "id,publish_date,title_en,title_cn,level,theme,sub_theme,style,color_tag," +
  "english_paras,chinese_paras,reflection_en,reflection_cn," +
  "sort,is_published,source_id";

/** Supabase 兜底查询最多等这么久，不能让一次注定失败的外网请求拖住页面。 */
const LIVE_TIMEOUT_MS = 6000;

function snapshotUrl(name: string): string {
  // BASE_URL 由 vite 注入，线上是 /reading-english-web/，本地是 /
  return `${import.meta.env.BASE_URL}${name}`;
}

/** 接受 PromiseLike，兼容 supabase-js 的 thenable 查询构造器。 */
function withTimeout<T>(task: PromiseLike<T>, ms: number): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error("Supabase 请求超时")), ms);
    Promise.resolve(task).then(
      (value) => {
        clearTimeout(timer);
        resolve(value);
      },
      (err: unknown) => {
        clearTimeout(timer);
        reject(err);
      },
    );
  });
}

/**
 * 有文章的日期列表（倒序）。首屏第一个请求，体积极小。
 * 快照读不到时（本地 dev 未构建）退回 Supabase 的轻量聚合查询。
 */
export async function fetchArticleIndex(): Promise<string[]> {
  try {
    const res = await fetch(snapshotUrl("articles-index.json"), { cache: "no-store" });
    if (!res.ok) throw new Error(`日期索引读取失败 (HTTP ${res.status})`);
    const rows: unknown = await res.json();
    if (!Array.isArray(rows) || !rows.every((d) => typeof d === "string")) {
      throw new Error("日期索引格式错误");
    }
    return rows as string[];
  } catch {
    if (!supabase) throw new Error("日期索引读取失败且 Supabase 未配置");
    const { data, error } = await withTimeout(
      supabase
        .from("articles")
        .select("publish_date")
        .eq("is_published", true)
        .order("publish_date", { ascending: false }),
      LIVE_TIMEOUT_MS,
    );
    if (error) throw new Error(error.message);
    const dates = [...new Set((data ?? []).map((r) => r.publish_date as string))];
    return dates.sort((a, b) => b.localeCompare(a));
  }
}

/** 某一天的分片。分片内已按 sort 升序；跨天顺序由 index 的日期倒序保证。 */
export async function fetchDateSlice(date: string): Promise<Article[]> {
  const res = await fetch(snapshotUrl(`articles-${date}.json`), { cache: "no-store" });
  if (!res.ok) throw new Error(`日期分片读取失败 (HTTP ${res.status}): ${date}`);
  const rows: unknown = await res.json();
  if (!Array.isArray(rows)) throw new Error("日期分片格式错误");
  return (rows as Article[]).filter((a) => a && a.is_published);
}

/**
 * 按 id 读单篇（阅读详情页用）。
 * 深链可能是用户直接输入 URL / 从收藏页点进来，首页分片缓存不一定在，
 * 所以走两条路：① 快照全量 articles.json 按 id 找（同域、国内可用）；
 * ② 找不到再查 Supabase（覆盖快照尚未重建、刚发布的新文章）。
 */
export async function fetchArticleById(id: string): Promise<Article | null> {
  // ① 快照全量兜底（同域静态文件，不受运营商拦 Supabase 影响）
  try {
    const res = await fetch(snapshotUrl("articles.json"), { cache: "no-store" });
    if (res.ok) {
      const rows: unknown = await res.json();
      if (Array.isArray(rows)) {
        const hit = (rows as Article[]).find((a) => a && a.id === id && a.is_published);
        if (hit) return hit;
      }
    }
  } catch {
    /* 快照读不到就继续走 Supabase */
  }

  // ② Supabase 兜底：快照还是旧版、文章刚发布时会命中这里
  if (!supabase) return null;
  const { data, error } = await withTimeout(
    supabase
      .from("articles")
      .select(COLUMNS)
      .eq("id", id)
      .eq("is_published", true)
      .limit(1)
      .maybeSingle(),
    LIVE_TIMEOUT_MS,
  );
  if (error) throw new Error(error.message);
  return (data as unknown as Article) ?? null;
}
