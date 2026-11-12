/**
 * 文章读取（只读）。
 *
 * 数据源策略：同域静态快照优先，Supabase 只作后台增强。
 * GitHub Pages 页面本身能打开，但浏览器直连 *.supabase.co 在部分运营商 /
 * 移动网络下会 DNS 或路由失败，整页报 `TypeError: Failed to fetch`。
 * 构建期已把已发布文章导出到 <base>/articles.json（见 scripts/export-articles.mjs），
 * 所以首屏只需读同域文件；能连上 Supabase 时再静默替换成最新数据。
 */
import { supabase } from "./supabase";
import type { Article } from "../types";

/** 单次拉取上限，够家庭自用规模；超出再分页。 */
const PAGE_SIZE = 1000;

const COLUMNS =
  "id,publish_date,title_en,title_cn,level,theme,sub_theme,style,color_tag," +
  "english_paras,chinese_paras,sort,is_published,source_id";

/** 后台增强最多等这么久，不能让一次注定失败的外网请求拖住页面。 */
const LIVE_TIMEOUT_MS = 6000;

function snapshotUrl(): string {
  // BASE_URL 由 vite 注入，线上是 /reading-english-web/，本地是 /
  return `${import.meta.env.BASE_URL}articles.json`;
}

async function loadSnapshot(): Promise<Article[]> {
  const res = await fetch(snapshotUrl(), { cache: "no-store" });
  if (!res.ok) throw new Error(`文章快照读取失败 (HTTP ${res.status})`);
  const rows: unknown = await res.json();
  if (!Array.isArray(rows)) throw new Error("文章快照格式错误");
  return rows as Article[];
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

async function loadLive(): Promise<Article[]> {
  if (!supabase) throw new Error("Supabase 未配置");
  const query = supabase
    .from("articles")
    .select(COLUMNS)
    .eq("is_published", true)
    .order("publish_date", { ascending: false })
    .order("sort", { ascending: true })
    .limit(PAGE_SIZE);

  const { data, error } = await withTimeout(query, LIVE_TIMEOUT_MS);
  if (error) throw new Error(error.message);
  return (data as unknown as Article[]) ?? [];
}

function sameArticles(a: Article[], b: Article[]): boolean {
  return a.length === b.length && a.every((row, i) => row.id === b[i].id);
}

/**
 * 拉取全部已发布文章。
 *
 * 快照立即返回用于首屏；onRefresh 在后台拿到更新的 Supabase 数据时被调用。
 * 后台失败一律静默 —— 国内手机直连不到 Supabase 是常态，不该弹错误条。
 * 只有「快照与 Supabase 都拿不到」（例如本地 dev 未构建快照且断网）才抛错。
 */
export async function fetchPublishedArticles(
  onRefresh?: (rows: Article[]) => void,
): Promise<Article[]> {
  let snapshot: Article[];
  try {
    snapshot = await loadSnapshot();
  } catch {
    // 本地 dev / 尚未导出快照：退回原来的直连行为
    return await loadLive();
  }

  void loadLive().then(
    (live) => {
      if (live.length > 0 && !sameArticles(live, snapshot)) onRefresh?.(live);
    },
    () => {
      /* 直连失败属预期，静默保留快照 */
    },
  );

  return snapshot;
}

/** 按 id 读取单篇（阅读详情页用，避免为了读一篇把全量都拉下来）。 */
export async function fetchArticleById(id: string): Promise<Article | null> {
  let snapshot: Article[] | null = null;
  try {
    snapshot = await loadSnapshot();
  } catch {
    /* 无快照时继续走 Supabase */
  }
  const cached = snapshot?.find((row) => row.id === id && row.is_published);
  if (cached) return cached;

  if (!supabase) return null;
  const query = supabase
    .from("articles")
    .select(COLUMNS)
    .eq("id", id)
    .eq("is_published", true)
    .limit(1)
    .maybeSingle();

  const { data, error } = await withTimeout(query, LIVE_TIMEOUT_MS);
  if (error) throw new Error(error.message);
  return (data as unknown as Article) ?? null;
}
