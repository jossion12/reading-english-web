/**
 * Supabase 只读客户端。
 *
 * 只使用 publishable（anon）密钥 —— RLS 保证匿名角色只能 SELECT 已发布的 articles，
 * 读不到 source_log，也无法做任何写入。前端代码里不存在任何写入路径（PRD §4.2）。
 */
import { createClient } from "@supabase/supabase-js";

/**
 * 环境变量清洗：去掉 BOM 与首尾空白。
 *
 * Windows 上用 PowerShell 管道把密钥写进 GitHub Secrets 时，很容易带上一个
 * U+FEFF（BOM）。它在 JS 字符串里是合法字符，但浏览器建 HTTP 头时会报
 * "String contains non ISO-8859-1 code point"，整页读不到数据 —— 这里统一兜住。
 */
function clean(value: string | undefined): string {
  return (value ?? "").replace(/^\uFEFF/, "").trim();
}

const url = clean(import.meta.env.VITE_SUPABASE_URL as string | undefined);
const anonKey = clean(import.meta.env.VITE_SUPABASE_ANON_KEY as string | undefined);

export const isConfigured = Boolean(url && anonKey);

export const supabase = isConfigured
  ? createClient(url as string, anonKey as string, {
      auth: { persistSession: false, autoRefreshToken: false },
      db: { schema: "public" },
    })
  : null;

export const configMissingMessage =
  "缺少 Supabase 配置：请在 .env 中设置 VITE_SUPABASE_URL 与 VITE_SUPABASE_ANON_KEY";
