"""生成日志与草稿存储（PRD §2.6）。

日志落盘为 JSONL：logs/generations.jsonl，每行一条记录，字段包含
入参梗概、LLM 原始返回内容、自检结果、入库状态、生成时间。
草稿（未入库的预览）同样以 status='preview' 存在于该文件中，提交入库时按 id 回取。

刻意不写入数据库 —— DB 项目的边界是「仅 source_log / articles 两张表 + 权限控制」，
日志属于服务自身的运行痕迹。
"""

from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import Settings, get_settings


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class LogStore:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.path: Path = self.settings.log_path / "generations.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    # --- 写 ----------------------------------------------------------------
    def append(self, entry: dict[str, Any]) -> dict[str, Any]:
        record = {"id": entry.get("id") or uuid.uuid4().hex, "created_at": entry.get("created_at") or _now()}
        record.update(entry)
        record["created_at"] = record["created_at"]
        line = json.dumps(record, ensure_ascii=False)
        with self._lock:
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        return record

    def update(self, entry_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
        """更新一条记录的若干字段（用于 preview -> committed 的状态流转）。"""
        with self._lock:
            rows = self._read_all()
            target = None
            for row in rows:
                if row.get("id") == entry_id:
                    row.update(patch)
                    target = row
                    break
            if target is None:
                return None
            self._rewrite(rows)
            return target

    # --- 读 ----------------------------------------------------------------
    def _read_all(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        rows: list[dict[str, Any]] = []
        with self.path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return rows

    def get(self, entry_id: str) -> dict[str, Any] | None:
        for row in self._read_all():
            if row.get("id") == entry_id:
                return row
        return None

    def list(self, *, limit: int = 50, status: str | None = None) -> list[dict[str, Any]]:
        rows = self._read_all()
        rows.reverse()
        if status:
            rows = [r for r in rows if r.get("status") == status]
        return rows[:limit]

    def _rewrite(self, rows: list[dict[str, Any]]) -> None:
        tmp = self.path.with_suffix(".jsonl.tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        tmp.replace(self.path)


_store: LogStore | None = None
_store_lock = threading.Lock()


def get_store() -> LogStore:
    global _store
    if _store is None:
        with _store_lock:
            if _store is None:
                _store = LogStore()
    return _store
