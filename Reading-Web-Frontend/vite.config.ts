import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

/**
 * GitHub Pages 部署时，站点挂在 https://<user>.github.io/<repo>/ 下，
 * 所有资源路径都要带上 /<repo>/ 前缀。本地开发时 base 为 "/"。
 *
 * 优先读 VITE_BASE_PATH（shell / CI 注入，或 .env / .env.production 里的值）；
 * 没给时退回环境变量推导的仓库名（GitHub Actions 里 GITHUB_REPOSITORY 可用）。
 */
function resolveBase(mode: string): string {
  // 注意：Vite 是在配置解析完之后才把 .env 文件灌进 import.meta.env，
  // 配置文件里拿不到文件里的值，所以这里自己 loadEnv 一次。
  // loadEnv 内部会让真实的 process.env 优先于文件值。
  const fileEnv = loadEnv(mode, process.cwd(), "VITE_");
  const explicit = (process.env.VITE_BASE_PATH || fileEnv.VITE_BASE_PATH || "").trim();
  if (explicit) {
    // 允许写 "/" 或 "/repo/" 或 "repo"，统一规范化成 "/xxx/" 形式
    const v = explicit.replace(/^\/+|\/+$/g, "");
    return v ? `/${v}/` : "/";
  }
  const repo = process.env.GITHUB_REPOSITORY?.split("/")[1]?.trim();
  if (repo) {
    return `/${repo}/`;
  }
  return "/";
}

export default defineConfig(({ mode }) => ({
  base: resolveBase(mode),
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
  },
  preview: {
    host: "127.0.0.1",
    port: 4173,
    strictPort: true,
  },
  build: {
    target: "es2020",
    cssCodeSplit: true,
    rollupOptions: {
      output: {
        // 拆 vendor 包，利于 CDN 长缓存
        manualChunks: {
          react: ["react", "react-dom", "react-router-dom"],
          supabase: ["@supabase/supabase-js"],
        },
      },
    },
  },
}));
