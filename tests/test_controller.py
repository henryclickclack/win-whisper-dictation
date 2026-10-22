from __future__ import annotations

import threading
from pathlib import Path

from whisper_shortcut.controller import DictationController
from whisper_shortcut.states import AppState


class FakeRecorder:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.started = False

    def start(self) -> None:
        self.started = True

    def stop(self) -> Path:
        self.started = False
        return self.path

    def cancel(self) -> None:
        self.started = False


class FakeTranscriber:
    def __init__(self, text: str) -> None:
        self.text = text

    def warm_up(self) -> None:
        pass

    def transcribe(self, _audio_path: Path) -> str:
        return self.text


class FakeInserter:
    def __init__(self, inserted: threading.Event) -> None:
        self.inserted = inserted
        self.text = ""

    def foreground_window(self) -> int:
        return 123

    def insert(self, text: str, target_window: int | None = None) -> bool:
        assert target_window == 123
        self.text = text
        self.inserted.set()
        return True

    def paste_last(self) -> bool:
        return bool(self.text)


def test_toggle_records_transcribes_and_inserts(tmp_path: Path) -> None:
    audio_path = tmp_path / "speech.wav"
    audio_path.touch()
    inserted = threading.Event()
    recorder = FakeRecorder(audio_path)
    inserter = FakeInserter(inserted)
    states: list[AppState] = []
    controller = DictationController(
        recorder,
        FakeTranscriber("A test transcript."),
        inserter,
        lambda state, _message: states.append(state),
    )

    controller.toggle_recording()
    assert recorder.started
    assert controller.state == AppState.RECORDING

    controller.toggle_recording()
    assert inserted.wait(timeout=2)
    assert inserter.text == "A test transcript."
    assert controller.state == AppState.INSERTED
    assert states == [
        AppState.RECORDING,
        AppState.TRANSCRIBING,
        AppState.INSERTED,
    ]
    assert not audio_path.exists()


def test_paste_last_reports_missing_transcript(tmp_path: Path) -> None:
    inserted = threading.Event()
    states: list[tuple[AppState, str]] = []
    controller = DictationController(
        FakeRecorder(tmp_path / "unused.wav"),
        FakeTranscriber(""),
        FakeInserter(inserted),
        lambda state, message: states.append((state, message)),
    )

    controller.paste_last()

    assert states[-1] == (AppState.ERROR, "No transcript to paste")
