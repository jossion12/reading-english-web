/**
 * 构建后处理：把 index.html 复制成 404.html。
 *
 * GitHub Pages 是纯静态托管，直接访问 /read/<id> 这类深链时找不到文件，
 * 会回落到 404.html。把入口页复制一份过去，SPA 就能在原 URL 上正常启动，
 * React Router 再按 basename 解析出对应路由 —— 不需要 HashRouter 那种 #/xxx 的地址。
 */
import { copyFileSync, existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const dist = join(root, "dist");
const index = join(dist, "index.html");
const notFound = join(dist, "404.html");

if (!existsSync(index)) {
  console.error("[postbuild] 找不到 dist/index.html，跳过 404.html 生成");
  process.exit(0);
}

copyFileSync(index, notFound);
console.log("[postbuild] 已生成 dist/404.html（SPA 深链回退）");
