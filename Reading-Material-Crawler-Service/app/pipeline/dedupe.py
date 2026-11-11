"""素材查重（PRD §2.6）。

对标准化梗概文本计算 SHA256 指纹，再查 source_log 命中唯一索引。
可选口径 fingerprint_mode=summary_level：同一梗概搭配不同难度视为不同素材。

除了指纹，还做一次「来源链接」比对：同一篇报道被抓两次时，LLM 两次提炼的
梗概文字会有细微差异，指纹随之不同，单纯靠指纹会漏检。因此把备注里的来源
链接归一化后作为第二重判据（PRD §2.7 规定来源链接记在 remark 里）。
"""

from __future__ import annotations

import hashlib
import re
from urllib.parse import urlsplit


def normalize_summary(text: str) -> str:
    """可读性归一化：统一换行、压缩连续空格、去掉行首尾空白。

    保留段落结构（空行），便于人阅读与排查。
    """
    if not text:
        return ""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    normalized = re.sub(r"[ \t\u3000]+", " ", normalized)
    normalized = re.sub(r" *\n *", "\n", normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip()


def _fingerprint_payload(text: str) -> str:
    """指纹口径：忽略一切空白差异。

    同一份梗概如果只是换行、空格数量不同（比如从网页复制时多带了一个空行），
    应该算作同一个素材，因此计算指纹前把所有空白字符去掉。
    """
    return re.sub(r"\s+", "", normalize_summary(text))


def compute_fingerprint(summary: str, *, mode: str = "summary", level: str | None = None) -> str:
    """计算素材指纹。

    mode=summary       -> sha256(归一化梗概)
    mode=summary_level -> sha256(归一化梗概 + "|" + 难度)，同一梗概换难度算不同素材
    """
    payload = _fingerprint_payload(summary)
    if mode == "summary_level":
        payload = f"{payload}|{(level or '').strip()}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ------------------------------------------------------------------ 来源链接 ---
_URL_RE = re.compile(r"https?://[^\s\"'<>，。；、）】》]+", re.IGNORECASE)


def extract_source_url(text: str) -> str | None:
    """从备注文本里取出第一个 http(s) 链接。

    备注是管理员自由输入的（PRD §2.7「备注：来源链接、备注说明」），
    所以链接前面后面可能带说明文字，这里只负责把链接本身抠出来。
    """
    if not text:
        return None
    match = _URL_RE.search(text)
    if not match:
        return None
    url = match.group(0).rstrip(".,;:!?)]}'\"")
    return url or None


def normalize_url(url: str) -> str:
    """归一化链接，用于判断两条素材是不是同一个来源。

    规则：忽略协议差异（http/https 视为同一篇）、忽略 www. 前缀、
    去掉末尾斜杠与 #锚点，查询串保留（有些站点靠查询参数区分不同文章）。
    """
    if not url:
        return ""
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return url.strip().lower()

    host = (parts.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    if not host:
        return url.strip().lower()

    path = parts.path or ""
    if path.endswith("/") and path != "/":
        path = path[:-1]
    return f"{host}{path}?{parts.query}" if parts.query else f"{host}{path}"

