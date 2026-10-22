from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from .states import AppState

LOGGER = logging.getLogger(__name__)


class Recorder(Protocol):
    def start(self) -> None: ...

    def stop(self) -> Path: ...

    def cancel(self) -> None: ...


class Transcriber(Protocol):
    def warm_up(self) -> None: ...

    def transcribe(self, audio_path: Path) -> str: ...


class Inserter(Protocol):
    def foreground_window(self) -> int: ...

    def insert(self, text: str, target_window: int | None = None) -> bool: ...

    def paste_last(self) -> bool: ...


class ModeSwitcher(Protocol):
    def toggle(self) -> str: ...


StateCallback = Callable[[AppState, str], None]

RESTING_STATES = {AppState.IDLE, AppState.INSERTED, AppState.ERROR, AppState.NOTICE}


class DictationController:
    def __init__(
        self,
        recorder: Recorder,
        transcriber: Transcriber,
        inserter: Inserter,
        on_state: StateCallback,
        on_transcript: Callable[[str], None] | None = None,
        mode_switcher: ModeSwitcher | None = None,
    ) -> None:
        self._recorder = recorder
        self._transcriber = transcriber
        self._inserter = inserter
        self._on_state = on_state
        self._on_transcript = on_transcript
        self._mode_switcher = mode_switcher
        self._state = AppState.IDLE
        self._target_window: int | None = None
        self._lock = threading.RLock()
        self._closed = False

    @property
    def state(self) -> AppState:
        with self._lock:
            return self._state

    def _set_state(self, state: AppState, message: str = "") -> None:
        with self._lock:
            self._state = state
        self._on_state(state, message)

    def warm_up(self) -> None:
        def load() -> None:
            try:
                self._transcriber.warm_up()
            except Exception:
                LOGGER.exception("Unable to preload transcription model")

        threading.Thread(target=load, name="model-warmup", daemon=True).start()

    def toggle_recording(self) -> None:
        with self._lock:
            if self._closed:
                return
            state = self._state

        if state == AppState.RECORDING:
            self._stop_and_transcribe()
        elif state in RESTING_STATES:
            self._start_recording()

    def _start_recording(self) -> None:
        try:
            self._target_window = self._inserter.foreground_window()
            self._recorder.start()
            self._set_state(AppState.RECORDING, "Recording")
        except Exception as exc:
            LOGGER.exception("Unable to start recording")
            self._set_state(AppState.ERROR, f"Microphone error: {exc}")

    def _stop_and_transcribe(self) -> None:
        try:
            audio_path = self._recorder.stop()
        except Exception as exc:
            LOGGER.exception("Unable to stop recording")
            self._set_state(AppState.ERROR, f"Recording error: {exc}")
            return

        self._set_state(AppState.TRANSCRIBING, "Transcribing")
        threading.Thread(
            target=self._process_audio,
            args=(audio_path, self._target_window),
            name="transcription",
            daemon=True,
        ).start()

    def _process_audio(self, audio_path: Path, target_window: int | None) -> None:
        try:
            transcript = self._transcriber.transcribe(audio_path)
            audio_path.unlink(missing_ok=True)
            if not transcript:
                self._set_state(AppState.ERROR, "No speech detected")
                return

            if self._on_transcript is not None:
                self._on_transcript(transcript)
            inserted = self._inserter.insert(transcript, target_window)
            if inserted:
                self._set_state(AppState.INSERTED, "Inserted")
            else:
                self._set_state(
                    AppState.ERROR,
                    "Copied; use the paste-last hotkey",
                )
        except Exception as exc:
            LOGGER.exception("Transcription failed")
            self._set_state(AppState.ERROR, f"Transcription error: {exc}")
        finally:
            audio_path.unlink(missing_ok=True)

    def paste_last(self) -> None:
        if self._inserter.paste_last():
            self._set_state(AppState.INSERTED, "Pasted last transcript")
        else:
            self._set_state(AppState.ERROR, "No transcript to paste")

    def notify(self, message: str) -> None:
        """Shows a short message unless a recording or transcription is active."""
        if self.state in RESTING_STATES:
            self._set_state(AppState.NOTICE, message)

    def toggle_mode(self) -> None:
        if self._mode_switcher is None or self.state not in RESTING_STATES:
            return
        try:
            label = self._mode_switcher.toggle()
        except Exception as exc:
            self._set_state(AppState.ERROR, str(exc))
            return
        self._set_state(AppState.NOTICE, f"Mode: {label}")
        self.warm_up()

    def reset_indicator(self) -> None:
        with self._lock:
            if self._state in RESTING_STATES:
                self._set_state(AppState.IDLE)

    def shutdown(self) -> None:
        with self._lock:
            self._closed = True
        try:
            self._recorder.cancel()
        except Exception:
            LOGGER.exception("Unable to stop the audio recorder cleanly")
