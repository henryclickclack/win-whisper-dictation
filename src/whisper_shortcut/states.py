from __future__ import annotations

from enum import StrEnum


class AppState(StrEnum):
    IDLE = "idle"
    RECORDING = "recording"
    TRANSCRIBING = "transcribing"
    INSERTED = "inserted"
    ERROR = "error"
    NOTICE = "notice"
