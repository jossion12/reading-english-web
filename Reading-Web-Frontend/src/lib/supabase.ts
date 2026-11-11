/**
 * Supabase 只读客户端。
 *
 * 只使用 publishable（anon）密钥 —— RLS 保证匿名角色只能 SELECT 已发布的 articles，
 * 读不到 source_log，也无法做任何写入。前端代码里不存在任何写入路径（PRD §4.2）。
 */
import { createClient } from "@supabase/supabase-js";

const url = import.meta.env.VITE_SUPABASE_URL as string | undefined;
const anonKey = import.meta.env.VITE_SUPABASE_ANON_KEY as string | undefined;

export const isConfigured = Boolean(url && anonKey);

export const supabase = isConfigured
  ? createClient(url as string, anonKey as string, {
      auth: { persistSession: false, autoRefreshToken: false },
      db: { schema: "public" },
    })
  : null;

export const configMissingMessage =
  "缺少 Supabase 配置：请在 .env 中设置 VITE_SUPABASE_URL 与 VITE_SUPABASE_ANON_KEY";
