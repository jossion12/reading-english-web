"""运行日志（PRD §4.4）：搜索记录、抓取 URL、查重结果、入库操作。

落盘 JSONL：logs/crawler.jsonl
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
        self.path: Path = self.settings.log_path / "crawler.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def append(self, event: str, **payload: Any) -> dict[str, Any]:
        record = {"id": uuid.uuid4().hex, "created_at": _now(), "event": event}
        record.update(payload)
        with self._lock:
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        return record

    def list(self, *, limit: int = 100, event: str | None = None) -> list[dict[str, Any]]:
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
        rows.reverse()
        if event:
            rows = [r for r in rows if r.get("event") == event]
        return rows[:limit]


_store: LogStore | None = None
_store_lock = threading.Lock()


def get_store() -> LogStore:
    global _store
    if _store is None:
        with _store_lock:
            if _store is None:
                _store = LogStore()
    return _store
