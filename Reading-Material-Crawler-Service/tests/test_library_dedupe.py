"""素材入库查重的单元测试（不触网、不连库）。

覆盖 PRD §2.6 的两重判据：
1. 梗概指纹（sha256）——同一份梗概重复入库；
2. 来源链接 ——同一篇报道被二次抓取时，两次 LLM 梗概文字不同、指纹不同，
   但链接相同，靠这一重兜住。
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import Settings
from app.library import LibraryError, SourceLibrary
from app.pipeline.dedupe import extract_source_url, normalize_url

URL = "https://www.chinanews.com.cn/gn/2026/11-10/10729476.shtml"


class FakeDb:
    """只实现 SourceLibrary 用到的数据库方法。"""

    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        self.rows = rows or []
        self.inserted: list[dict[str, Any]] = []

    async def find_source_by_fingerprint(self, fingerprint: str) -> dict[str, Any] | None:
        for row in self.rows:
            if row["source_fingerprint"] == fingerprint:
                return row
        return None

    async def find_source_by_url(self, url: str) -> dict[str, Any] | None:
        target = normalize_url(url)
        for row in self.rows:
            other = extract_source_url(row.get("remark") or "")
            if other and normalize_url(other) == target:
                return row
        return None

    async def insert_source(self, row: dict[str, Any]) -> dict[str, Any]:
        self.inserted.append(row)
        return {**row, "id": "new-source-id"}


def make_library(rows: list[dict[str, Any]] | None = None) -> tuple[SourceLibrary, FakeDb]:
    db = FakeDb(rows)
    return SourceLibrary(db=db, settings=Settings()), db


@pytest.mark.asyncio
async def test_same_fingerprint_is_rejected() -> None:
    library, _ = make_library([{"id": "old-1", "source_fingerprint": "fp-1", "remark": None}])
    with pytest.raises(LibraryError) as exc:
        await library.create(summary_text="梗概正文", fingerprint="fp-1")
    assert "已存在" in str(exc.value)


@pytest.mark.asyncio
async def test_same_url_with_different_fingerprint_is_rejected() -> None:
    """同一篇报道二次抓取：梗概文字有微差 → 指纹不同，但链接相同 → 仍然拦下。"""
    library, _ = make_library(
        [{"id": "old-1", "source_fingerprint": "fp-1", "remark": f"探针素材 · {URL}"}]
    )
    with pytest.raises(LibraryError) as exc:
        await library.create(
            summary_text="梗概正文（措辞略有不同）", fingerprint="fp-2", source_url=URL
        )
    assert "来源链接重复" in str(exc.value)
    assert "old-1" in str(exc.value)


@pytest.mark.asyncio
async def test_remark_gets_url_appended_when_missing() -> None:
    library, db = make_library()
    await library.create(summary_text="梗概正文", remark="新华社报道", source_url=URL)
    assert db.inserted[0]["remark"] == f"新华社报道 · {URL}"


@pytest.mark.asyncio
async def test_remark_keeps_existing_text_when_url_already_present() -> None:
    library, db = make_library()
    await library.create(summary_text="梗概正文", remark=f"来源：{URL}", source_url=URL)
    assert db.inserted[0]["remark"] == f"来源：{URL}"


@pytest.mark.asyncio
async def test_new_material_is_inserted() -> None:
    library, db = make_library()
    row = await library.create(summary_text="梗概正文", fingerprint="fp-new", source_url=URL)
    assert row["id"] == "new-source-id"
    assert len(db.inserted) == 1
