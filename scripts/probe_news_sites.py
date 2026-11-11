"""探测白名单新闻站点的可达性并抓取示例文章链接。"""

from __future__ import annotations

import re
import sys

import httpx

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9",
}

SITES = [
    "http://www.news.cn/",
    "http://www.people.com.cn/",
    "https://news.cctv.com/",
    "http://www.chinanews.com.cn/",
]

LINK_RE = re.compile(r'href=["\'](https?://[^"\']+?\.(?:htm|html|shtml))["\']')


def main() -> int:
    found = []
    for site in SITES:
        try:
            r = httpx.get(site, headers=HEADERS, timeout=25, follow_redirects=True)
        except Exception as exc:
            print(f"{site} -> ERR {type(exc).__name__} {str(exc)[:100]}")
            continue
        links = LINK_RE.findall(r.text)
        print(f"{site} -> {r.status_code} bytes={len(r.text)} links={len(links)}")
        for link in links[:5]:
            print("    ", link)
            found.append(link)

    print("\n== 抽样抓正文长度 ==")
    for link in found[:8]:
        try:
            r = httpx.get(link, headers=HEADERS, timeout=25, follow_redirects=True)
            text = re.sub(r"<[^>]+>", " ", r.text)
            text = re.sub(r"\s+", " ", text)
            print(f"{len(text):>7} chars  {r.status_code}  {link[:100]}")
        except Exception as exc:
            print(f"   ERR {type(exc).__name__} {link[:80]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
