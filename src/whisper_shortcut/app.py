from __future__ import annotations

import logging
import signal
import sys
import threading
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

from .audio import AudioRecorder
from .config import (
    config_directory,
    ensure_env_file,
    load_api_key,
    load_config,
    load_mode,
    save_mode,
)
from .controller import DictationController
from .history import TranscriptHistory
from .history_window import HistoryWindow
from .indicator import FloatingIndicator, IndicatorBridge
from .transcriber import LocalTranscriber, OpenAITranscriber, SwitchableTranscriber
from .windows_input import HotkeyListener, TextInserter


def configure_logging() -> Path:
    directory = config_directory()
    directory.mkdir(parents=True, exist_ok=True)
    log_path = directory / "whisper-shortcut.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_path, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )
    return log_path


def in_background(action: Callable[[], None]) -> Callable[[], None]:
    # Hotkey callbacks run on the keyboard hook thread, which must not block.
    return lambda: threading.Thread(target=action, daemon=True).start()


def main() -> int:
    application = QApplication(sys.argv)
    application.setApplicationName("Whisper Shortcut")
    application.setQuitOnLastWindowClosed(False)
    configure_logging()

    try:
        config = load_config()
        ensure_env_file()
    except Exception as exc:
        logging.exception("Invalid configuration")
        QMessageBox.critical(
            None,
            "Whisper Shortcut",
            f"Could not load the configuration:\n\n{exc}",
        )
        return 2

    bridge = IndicatorBridge()
    recorder = AudioRecorder(config.audio)
    transcriber = SwitchableTranscriber(
        local=LocalTranscriber(config.transcription),
        remote=OpenAITranscriber(
            config.openai,
            config.transcription.language,
            load_api_key,
        ),
        mode=load_mode(),
        on_change=save_mode,
    )
    history = TranscriptHistory(config_directory() / "history.json")
    inserter = TextInserter()
    inserter.remember(history.latest())
    controller = DictationController(
        recorder=recorder,
        transcriber=transcriber,
        inserter=inserter,
        on_state=bridge.publish,
        on_transcript=history.add,
        mode_switcher=transcriber,
    )
    indicator = FloatingIndicator(
        config.indicator,
        on_timeout=controller.reset_indicator,
        level_source=lambda: recorder.level,
        mode_source=lambda: transcriber.short_label,
    )

    def copy_from_history(text: str) -> None:
        inserter.copy_transcript(text)
        controller.notify("Copied to clipboard")

    history_window = HistoryWindow(history, on_copy=copy_from_history)
    bridge.state_changed.connect(indicator.set_state)
    bridge.history_requested.connect(history_window.toggle)
    bridge.quit_requested.connect(application.quit)

    try:
        listener = HotkeyListener(
            config.hotkeys,
            on_toggle=controller.toggle_recording,
            on_paste_last=in_background(controller.paste_last),
            on_history=bridge.request_history,
            on_toggle_mode=in_background(controller.toggle_mode),
            on_quit=bridge.request_quit,
        )
        listener.start()
    except Exception as exc:
        logging.exception("Unable to register global hotkeys")
        QMessageBox.critical(
            None,
            "Whisper Shortcut",
            f"Could not register the global hotkeys:\n\n{exc}",
        )
        return 3

    shutting_down = False

    def shutdown() -> None:
        nonlocal shutting_down
        if shutting_down:
            return
        shutting_down = True
        listener.stop()
        controller.shutdown()

    application.aboutToQuit.connect(shutdown)
    signal.signal(signal.SIGINT, lambda *_args: bridge.request_quit())

    # Give Python a regular chance to process Ctrl+C when run from a console.
    keepalive = QTimer()
    keepalive.timeout.connect(lambda: None)
    keepalive.start(500)

    controller.warm_up()
    logging.info("Whisper Shortcut started in %s mode", transcriber.mode)
    return application.exec()
