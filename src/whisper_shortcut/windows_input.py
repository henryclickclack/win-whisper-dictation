from __future__ import annotations

import ctypes
import time
from collections.abc import Callable

import pyperclip
from pynput import keyboard

from .config import HotkeyConfig

# VK_SHIFT, VK_CONTROL, VK_MENU (Alt), VK_LWIN, VK_RWIN
MODIFIER_KEYS = (0x10, 0x11, 0x12, 0x5B, 0x5C)


class TextInserter:
    """Copies text and sends Ctrl+V to a target Windows foreground window."""

    def __init__(self) -> None:
        self._keyboard = keyboard.Controller()
        self._last_transcript = ""
        self._user32 = ctypes.windll.user32

    @property
    def last_transcript(self) -> str:
        return self._last_transcript

    def foreground_window(self) -> int:
        return int(self._user32.GetForegroundWindow())

    def remember(self, text: str) -> None:
        self._last_transcript = text

    def copy_transcript(self, text: str) -> None:
        self._last_transcript = text
        pyperclip.copy(text)

    def insert(self, text: str, target_window: int | None = None) -> bool:
        self.copy_transcript(text)
        if target_window:
            self._user32.SetForegroundWindow(target_window)
            time.sleep(0.08)
        return self._send_paste()

    def paste_last(self) -> bool:
        if not self._last_transcript:
            return False
        # Re-copy in case another application replaced the clipboard.
        pyperclip.copy(self._last_transcript)
        return self._send_paste()

    def _modifiers_released(self, timeout: float = 2.0) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if not any(
                self._user32.GetAsyncKeyState(key) & 0x8000 for key in MODIFIER_KEYS
            ):
                return True
            time.sleep(0.01)
        return False

    def _send_paste(self) -> bool:
        # The hotkey's own modifiers are usually still held when we get here.
        # Sending Ctrl+V on top of a held Alt reaches the target as Ctrl+Alt+V,
        # which pastes nothing, so wait for the user to let go first.
        if not self._modifiers_released():
            return False
        try:
            with self._keyboard.pressed(keyboard.Key.ctrl):
                self._keyboard.press("v")
                self._keyboard.release("v")
            return True
        except Exception:
            # The transcript remains on the clipboard for manual paste.
            return False


class HotkeyListener:
    def __init__(
        self,
        config: HotkeyConfig,
        on_toggle: Callable[[], None],
        on_paste_last: Callable[[], None],
        on_history: Callable[[], None],
        on_toggle_mode: Callable[[], None],
        on_quit: Callable[[], None],
    ) -> None:
        self._listener = keyboard.GlobalHotKeys(
            {
                config.toggle_recording: on_toggle,
                config.paste_last: on_paste_last,
                config.history: on_history,
                config.toggle_mode: on_toggle_mode,
                config.quit: on_quit,
            }
        )

    def start(self) -> None:
        self._listener.start()

    def stop(self) -> None:
        self._listener.stop()
