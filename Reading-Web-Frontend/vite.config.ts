import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

/**
 * GitHub Pages 部署时，站点挂在 https://<user>.github.io/<repo>/ 下，
 * 所有资源路径都要带上 /<repo>/ 前缀。本地开发时 base 为 "/"。
 *
 * 优先读 VITE_BASE_PATH（.env.production 或 CI 注入）；
 * 没给时退回环境变量推导的仓库名（GitHub Actions 里 GITHUB_REPOSITORY 可用）。
 */
function resolveBase(): string {
  const explicit = process.env.VITE_BASE_PATH?.trim();
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

export default defineConfig({
  base: resolveBase(),
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
});
