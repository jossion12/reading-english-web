/**
 * 构建后导出「已发布文章」静态快照 → dist/articles.json。
 *
 * 为什么需要它：GitHub Pages 在国内手机网络下能打开，但浏览器直连
 * *.supabase.co 常被运营商 DNS / 路由拦掉，表现为 `TypeError: Failed to fetch`，
 * 整个阅读站 0 篇。把文章在 CI 构建时用 anon 密钥拉一次、随站点一起发布，
 * 浏览器就只需请求同域静态文件；Supabase 退为「能连上时」的后台增强。
 *
 * 只用 VITE_SUPABASE_ANON_KEY（publishable / anon，RLS 只允许读已发布文章），
 * 绝不引入 service_role。写出的 JSON 与 articles 表的公开字段一一对应。
 *
 * 优先级：CI 注入的环境变量 > 本地 .env.production > 跳过。
 * 导出失败只警告不抛错（本地开发不该被网络拖垮），CI 由 workflow 的
 * 「校验文章快照」步骤兜住，避免部署出没有快照的坏版本。
 */
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const dist = join(root, "dist");

const COLUMNS =
  "id,publish_date,title_en,title_cn,level,theme,sub_theme,style,color_tag," +
  "english_paras,chinese_paras,sort,is_published,source_id";
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

async function main() {
  const { url, key } = readEnv();
  if (!url || !key) {
    console.warn("[export-articles] 未配置 Supabase 只读变量，跳过快照（前端将直连 Supabase）");
    return;
  }

  // 逗号在 query 里是合法分隔符，不编码，PostgREST 原样解析 select / 多列 order。
  const endpoint =
    `${url.replace(/\/+$/, "")}/rest/v1/articles` +
    `?select=${COLUMNS}&is_published=eq.true` +
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

  const published = rows.filter((row) => row && row.is_published === true);
  writeFileSync(join(dist, "articles.json"), JSON.stringify(published), "utf8");
  console.log(`[export-articles] 已写入 dist/articles.json（${published.length} 篇已发布文章）`);
}

main().catch((err) => {
  console.warn(`[export-articles] 导出失败：${err.message}；保留原有行为（前端直连 Supabase）`);
});
