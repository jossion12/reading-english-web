/**
 * 构建后导出「已发布文章」静态快照 → dist/articles.json。
 *
 * 为什么需要它：GitHub Pages 在国内手机网络下能打开，但浏览器直连
 * *.supabase.co 常被运营商 DNS / 路由拦掉，表现为 `TypeError: Failed to fetch`，
 * 整个阅读站 0 篇。把文章在 CI 构建时用 anon 密钥拉一次、随站点一起发布，
 * 浏览器就只需请求同域静态文件；Supabase 退为「能连上时」的后台增强。
 *
 * 产物（都在 dist/）：
 *   - articles.json           全量已发布文章，供阅读页深链按 id 兜底 + 向后兼容
 *   - articles-index.json     有文章的日期数组（倒序），首屏第一个请求，极小
 *   - articles-<date>.json    每天一个分片，滚动到对应日期才请求
 * 首屏只拉 index + 最新一天分片，避免一次性下载全量；这正是「加载时效」优化。
 *
 * 只用 VITE_SUPABASE_ANON_KEY（publishable / anon，RLS 只允许读已发布文章），
 * 绝不引入 service_role。写出的 JSON 与 articles 表的公开字段一一对应。
 *
 * 优先级：CI 注入的环境变量 > 本地 .env.production > 跳过。
 * 导出失败只警告不抛错（本地开发不该被网络拖垮），CI 由 workflow 的
 * 「校验文章快照」步骤兜住，避免部署出没有快照的坏版本。
 */
import { existsSync, readFileSync, readdirSync, unlinkSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const dist = join(root, "dist");

const COMMON_COLUMNS =
  "id,publish_date,title_en,title_cn,level,theme,sub_theme,style,color_tag," +
  "english_paras,chinese_paras";
const TAIL_COLUMNS = "sort,is_published,source_id";
// P0 R6：读后思考两列必须进快照，否则国内学生首屏看不到折叠区。
const COLUMNS = `${COMMON_COLUMNS},reflection_en,reflection_cn,${TAIL_COLUMNS}`;
const LEGACY_COLUMNS = `${COMMON_COLUMNS},${TAIL_COLUMNS}`;
const PAGE_SIZE = 1000;

/** Windows 上用 PowerShell 管道写配置容易带 U+FEFF，统一清掉。 */
function clean(value) {
  return (value ?? "").replace(/^\uFEFF/, "").trim();
}

function readEnv() {
  let url = clean(process.env.VITE_SUPABASE_URL);
  let key = clean(
    process.env.VITE_SUPABASE_ANON_KEY || process.env.VITE_SUPABASE_PUBLISHABLE_KEY,
  );
  if (url && key) return { url, key };

  const file = join(root, ".env.production");
  if (!existsSync(file)) return { url, key };
  for (const line of readFileSync(file, "utf8").split(/\r?\n/)) {
    const text = line.trim();
    if (!text || text.startsWith("#") || !text.includes("=")) continue;
    const idx = text.indexOf("=");
    const name = text.slice(0, idx).trim();
    const value = clean(text.slice(idx + 1).replace(/^["']|["']$/g, ""));
    if (name === "VITE_SUPABASE_URL" && !url) url = value;
    if ((name === "VITE_SUPABASE_ANON_KEY" || name === "VITE_SUPABASE_PUBLISHABLE_KEY") && !key) {
      key = value;
    }
  }
  return { url, key };
}

/** 逗号在 query 里是合法分隔符，不编码，PostgREST 原样解析 select / 多列 order。 */
async function requestArticles(url, key, columns) {
  const endpoint =
    `${url.replace(/\/+$/, "")}/rest/v1/articles` +
    `?select=${columns}&is_published=eq.true` +
    `&order=publish_date.desc,sort.asc&limit=${PAGE_SIZE}`;

  const resp = await fetch(endpoint, {
    headers: { apikey: key, Authorization: `Bearer ${key}` },
    signal: AbortSignal.timeout(20_000),
  });
  if (!resp.ok) {
    throw new Error(`Supabase 返回 HTTP ${resp.status}: ${(await resp.text()).slice(0, 200)}`);
  }
  const rows = await resp.json();
  if (!Array.isArray(rows)) throw new Error("Supabase 返回的不是数组");
  return rows;
}

async function main() {
  const { url, key } = readEnv();
  if (!url || !key) {
    console.warn("[export-articles] 未配置 Supabase 只读变量，跳过快照（前端将直连 Supabase）");
    return;
  }

  let rows;
  try {
    rows = await requestArticles(url, key, COLUMNS);
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    // 生产库还没应用 R5 迁移时，PostgREST 因未知列回 400 / PGRST204。
    // 降级按旧字段导出，首屏仍能出快照，不至于代码先上、迁移后做就整站归零。
    if (!/reflection|PGRST204|column|42703|HTTP 400|HTTP 404/i.test(message)) throw err;
    console.warn("[export-articles] 线上库尚无 reflection 两列，按旧字段导出；请先应用 R5 迁移");
    rows = await requestArticles(url, key, LEGACY_COLUMNS);
  }

  const published = rows.filter((row) => row && row.is_published === true);
  // 全量文件保留两用途：① 阅读页深链按 id 查找的快照兜底；② 老版本前端的向后兼容。
  writeFileSync(join(dist, "articles.json"), JSON.stringify(published), "utf8");

  // 首屏只拉「最新一天」+ 一个极小的日期索引；更早的日期等滚动到列表底部再按需取。
  // Supabase 查询已是 publish_date.desc, sort.asc，这里分组时保持该顺序：
  //   dates 数组按日期倒序，每个分片内按 sort 升序。
  const byDate = new Map();
  for (const row of published) {
    const date = row.publish_date;
    if (!byDate.has(date)) byDate.set(date, []);
    byDate.get(date).push(row);
  }
  const dates = [...byDate.keys()]; // Map 保序 → 已是日期倒序

  // 清理上一次构建残留的旧分片（某天文章全部下架时，旧文件不该继续留在产物里）。
  for (const name of readdirSync(dist)) {
    if (/^articles-\d{4}-\d{2}-\d{2}\.json$/.test(name)) unlinkSync(join(dist, name));
  }

  writeFileSync(join(dist, "articles-index.json"), JSON.stringify(dates), "utf8");
  for (const [date, items] of byDate) {
    writeFileSync(join(dist, `articles-${date}.json`), JSON.stringify(items), "utf8");
  }
  console.log(
    `[export-articles] 已写入 dist/articles.json（全量 ${published.length} 篇）+ ` +
      `articles-index.json（${dates.length} 个日期）+ ${dates.length} 个按日期分片`,
  );
}

main().catch((err) => {
  console.warn(`[export-articles] 导出失败：${err.message}；保留原有行为（前端直连 Supabase）`);
});
