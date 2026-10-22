from __future__ import annotations

from pathlib import Path

import pytest

from whisper_shortcut import config
from whisper_shortcut.config import OpenAIConfig
from whisper_shortcut.controller import DictationController
from whisper_shortcut.history import TranscriptHistory
from whisper_shortcut.states import AppState
from whisper_shortcut.transcriber import OpenAITranscriber, SwitchableTranscriber
from whisper_shortcut.windows_input import TextInserter


class FakeUser32:
    def __init__(self, held_polls: int) -> None:
        self.held_polls = held_polls

    def GetAsyncKeyState(self, _key: int) -> int:  # noqa: N802
        if self.held_polls > 0:
            self.held_polls -= 1
            return 0x8000
        return 0


def test_paste_waits_for_hotkey_modifiers_to_be_released() -> None:
    inserter = TextInserter.__new__(TextInserter)
    inserter._user32 = FakeUser32(held_polls=3)
    assert inserter._modifiers_released(timeout=1.0)
    assert inserter._user32.held_polls == 0

    inserter._user32 = FakeUser32(held_polls=10**9)
    assert not inserter._modifiers_released(timeout=0.05)


class FakeBackend:
    def __init__(self, text: str) -> None:
        self.text = text

    def warm_up(self) -> None:
        pass

    def transcribe(self, _audio_path: Path) -> str:
        return self.text


def make_switchable(key: str | None, saved: list[str]) -> SwitchableTranscriber:
    remote = OpenAITranscriber(OpenAIConfig(), None, lambda: key)
    return SwitchableTranscriber(FakeBackend("local"), remote, on_change=saved.append)


def test_toggle_switches_mode_and_persists() -> None:
    saved: list[str] = []
    transcriber = make_switchable("sk-test", saved)

    assert transcriber.toggle() == "OpenAI API"
    assert transcriber.mode == "openai"
    assert transcriber.toggle() == "Local"
    assert saved == ["openai", "local"]


def test_toggle_stays_local_without_api_key() -> None:
    saved: list[str] = []
    transcriber = make_switchable(None, saved)

    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        transcriber.toggle()
    assert transcriber.mode == "local"
    assert saved == []


def test_controller_reports_mode_toggle_failure() -> None:
    states: list[tuple[AppState, str]] = []
    controller = DictationController(
        recorder=None,  # type: ignore[arg-type]
        transcriber=FakeBackend(""),
        inserter=None,  # type: ignore[arg-type]
        on_state=lambda state, message: states.append((state, message)),
        mode_switcher=make_switchable(None, []),
    )

    controller.toggle_mode()

    assert states[-1][0] == AppState.ERROR
    assert "OPENAI_API_KEY" in states[-1][1]


def test_api_key_is_read_from_env_file(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    assert config.load_api_key() is None

    config.ensure_env_file()
    assert config.load_api_key() is None

    config.env_path().write_text('# key\nOPENAI_API_KEY="sk-file"\n', encoding="utf-8")
    assert config.load_api_key() == "sk-file"


def test_mode_round_trips_through_state_file(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert config.load_mode() == "local"
    config.save_mode("openai")
    assert config.load_mode() == "openai"


def test_history_keeps_newest_first_and_persists(tmp_path: Path) -> None:
    path = tmp_path / "history.json"
    history = TranscriptHistory(path, limit=2)
    for text in ("one", "two", "three"):
        history.add(text)

    assert [entry.text for entry in history.entries()] == ["three", "two"]
    assert TranscriptHistory(path).latest() == "three"
