"""本地模拟 GitHub Pages：静态托管 dist/，未知路径回落到 404.html（与 Pages 行为一致）。

用来在推送之前验证「子路径部署 + 深链回退」是否正常。

用法：
    .\\Reading-Article-Generate-Service\\.venv\\Scripts\\python.exe scripts\\serve_pages_preview.py [端口] [子路径]

例：
    python scripts\\serve_pages_preview.py 8099 reading-english-web
    → http://127.0.0.1:8099/reading-english-web/
"""

from __future__ import annotations

import os
import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "Reading-Web-Frontend" / "dist"


class PagesLikeHandler(SimpleHTTPRequestHandler):
    """像 GitHub Pages 一样：找不到文件时用站点根的 404.html 兜底（状态码仍是 404）。"""

    #: 站点根（= GitHub Pages 的 publish directory），404.html 放在这里
    site_root: Path = DIST

    def send_head(self):
        path = self.translate_path(self.path)
        if not Path(path).exists():
            fallback = self.site_root / "404.html"
            if fallback.exists():
                # translate_path 是相对 self.directory 解析的，这里换算成相对路径
                rel = os.path.relpath(fallback, Path(self.directory)).replace(os.sep, "/")
                self.path = "/" + rel
                return super().send_head()
        return super().send_head()

    def log_message(self, fmt: str, *args) -> None:  # 少打点日志
        if "404" in (fmt % args):
            sys.stderr.write("[pages] %s\n" % (fmt % args))


def main() -> int:
    if not DIST.exists():
        print("找不到 Reading-Web-Frontend/dist，先跑一次 npm run build")
        return 1

    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8099
    subpath = sys.argv[2] if len(sys.argv) > 2 else ""

    # 把 dist 挂到子路径下，模拟 https://<user>.github.io/<repo>/
    webroot = ROOT / ".runtime" / "pages-preview"
    mount = webroot / subpath if subpath else webroot
    mount.mkdir(parents=True, exist_ok=True)
    for item in DIST.iterdir():
        target = mount / item.name
        if item.is_dir():
            target.mkdir(exist_ok=True)
            for f in item.iterdir():
                (target / f.name).write_bytes(f.read_bytes())
        else:
            target.write_bytes(item.read_bytes())

    handler = partial(PagesLikeHandler, directory=str(webroot))
    PagesLikeHandler.site_root = mount
    with ThreadingHTTPServer(("127.0.0.1", port), handler) as httpd:
        prefix = f"/{subpath}" if subpath else ""
        print(f"模拟 GitHub Pages: http://127.0.0.1:{port}{prefix}/")
        print(f"深链测试: http://127.0.0.1:{port}{prefix}/read/<文章id>")
        print("Ctrl+C 停止")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n已停止")
    return 0


if __name__ == "__main__":
    sys.exit(main())
