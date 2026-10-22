from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class HistoryEntry:
    text: str
    timestamp: float


class TranscriptHistory:
    """Keeps the most recent transcripts, newest first, and persists them."""

    def __init__(self, path: Path | None = None, limit: int = 50) -> None:
        self._path = path
        self._limit = limit
        self._lock = threading.Lock()
        self._entries: list[HistoryEntry] = self._load()

    def _load(self) -> list[HistoryEntry]:
        if self._path is None or not self._path.exists():
            return []
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            entries = [
                HistoryEntry(str(item["text"]), float(item["timestamp"]))
                for item in raw
            ]
        except Exception:
            LOGGER.warning("Ignoring unreadable transcript history", exc_info=True)
            return []
        return entries[: self._limit]

    def _save(self) -> None:
        if self._path is None:
            return
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(
                json.dumps([asdict(entry) for entry in self._entries], indent=1),
                encoding="utf-8",
            )
        except OSError:
            LOGGER.warning("Unable to save transcript history", exc_info=True)

    def add(self, text: str) -> None:
        with self._lock:
            self._entries.insert(0, HistoryEntry(text, time.time()))
            del self._entries[self._limit :]
            self._save()

    def entries(self) -> list[HistoryEntry]:
        with self._lock:
            return list(self._entries)

    def latest(self) -> str:
        with self._lock:
            return self._entries[0].text if self._entries else ""
