from __future__ import annotations

import json
import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_CONFIG = """# Whisper Shortcut configuration

[hotkeys]
toggle_recording = "<ctrl>+<alt>+<space>"
paste_last = "<ctrl>+<alt>+v"
history = "<ctrl>+<alt>+c"
toggle_mode = "<ctrl>+<alt>+m"
quit = "<ctrl>+<alt>+q"

[audio]
device = ""
sample_rate = 16000

[transcription]
model = "small"
language = ""
device = "auto"
compute_type = "auto"
beam_size = 5

[openai]
model = "gpt-transcribe"
base_url = "https://api.openai.com/v1"
timeout = 120

[indicator]
anchor = "top-center"
x_offset = 0
y_offset = 8
width = 210
height = 42
"""


@dataclass(frozen=True)
class HotkeyConfig:
    toggle_recording: str = "<ctrl>+<alt>+<space>"
    paste_last: str = "<ctrl>+<alt>+v"
    history: str = "<ctrl>+<alt>+c"
    toggle_mode: str = "<ctrl>+<alt>+m"
    quit: str = "<ctrl>+<alt>+q"


@dataclass(frozen=True)
class AudioConfig:
    device: str | int | None = None
    sample_rate: int = 16_000


@dataclass(frozen=True)
class TranscriptionConfig:
    model: str = "small"
    language: str | None = None
    device: str = "auto"
    compute_type: str = "auto"
    beam_size: int = 5


@dataclass(frozen=True)
class OpenAIConfig:
    model: str = "gpt-transcribe"
    base_url: str = "https://api.openai.com/v1"
    timeout: float = 120.0


@dataclass(frozen=True)
class IndicatorConfig:
    anchor: str = "top-center"
    x_offset: int = 0
    y_offset: int = 8
    width: int = 210
    height: int = 42


@dataclass(frozen=True)
class AppConfig:
    hotkeys: HotkeyConfig = field(default_factory=HotkeyConfig)
    audio: AudioConfig = field(default_factory=AudioConfig)
    transcription: TranscriptionConfig = field(default_factory=TranscriptionConfig)
    openai: OpenAIConfig = field(default_factory=OpenAIConfig)
    indicator: IndicatorConfig = field(default_factory=IndicatorConfig)


def config_directory() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    if not base:
        base = str(Path.home() / "AppData" / "Local")
    return Path(base) / "WhisperShortcut"


def config_path() -> Path:
    return config_directory() / "config.toml"


def ensure_config_file(path: Path | None = None) -> Path:
    destination = path or config_path()
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists():
        destination.write_text(DEFAULT_CONFIG, encoding="utf-8")
    return destination


ENV_TEMPLATE = """# Used when Whisper Shortcut is switched to OpenAI API mode.
OPENAI_API_KEY=
"""


def env_path() -> Path:
    return config_directory() / ".env"


def ensure_env_file() -> Path:
    destination = env_path()
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists():
        destination.write_text(ENV_TEMPLATE, encoding="utf-8")
    return destination


def _read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except OSError:
        return values
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.removeprefix("export ").partition("=")
        values[name.strip()] = value.strip().strip("\"'")
    return values


def load_api_key() -> str | None:
    """Finds the OpenAI key in the environment or a .env file."""
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if key:
        return key
    for path in (env_path(), Path.cwd() / ".env"):
        key = _read_env_file(path).get("OPENAI_API_KEY", "")
        if key:
            return key
    return None


def state_path() -> Path:
    return config_directory() / "state.json"


def load_mode() -> str:
    """Returns the transcription mode chosen with the toggle-mode hotkey."""
    try:
        mode = json.loads(state_path().read_text(encoding="utf-8")).get("mode")
    except (OSError, ValueError, AttributeError):
        return "local"
    return mode if mode in {"local", "openai"} else "local"


def save_mode(mode: str) -> None:
    path = state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"mode": mode}), encoding="utf-8")


def _section(data: dict[str, Any], name: str) -> dict[str, Any]:
    value = data.get(name, {})
    if not isinstance(value, dict):
        raise ValueError(f"[{name}] must be a TOML table")
    return value


def _optional_string(value: Any) -> str | None:
    if value is None or value == "":
        return None
    return str(value)


def _normalize_hotkey(value: Any) -> str:
    # pynput requires named keys such as space to use angle brackets. Accept
    # the more natural spelling too, including configs created by v0.1.0.
    parts = str(value).split("+")
    return "+".join("<space>" if part.lower() == "space" else part for part in parts)


def load_config(path: Path | None = None) -> AppConfig:
    source = ensure_config_file(path)
    with source.open("rb") as handle:
        data = tomllib.load(handle)

    hotkeys = _section(data, "hotkeys")
    audio = _section(data, "audio")
    transcription = _section(data, "transcription")
    openai = _section(data, "openai")
    indicator = _section(data, "indicator")

    device_value = audio.get("device")
    if device_value == "":
        device_value = None

    anchor = str(indicator.get("anchor", "top-center"))
    if anchor not in {"top-left", "top-center", "top-right"}:
        raise ValueError("indicator.anchor must be top-left, top-center, or top-right")

    sample_rate = int(audio.get("sample_rate", 16_000))
    if sample_rate <= 0:
        raise ValueError("audio.sample_rate must be positive")

    return AppConfig(
        hotkeys=HotkeyConfig(
            toggle_recording=_normalize_hotkey(
                hotkeys.get("toggle_recording", "<ctrl>+<alt>+<space>")
            ),
            paste_last=_normalize_hotkey(
                hotkeys.get("paste_last", "<ctrl>+<alt>+v")
            ),
            history=_normalize_hotkey(hotkeys.get("history", "<ctrl>+<alt>+c")),
            toggle_mode=_normalize_hotkey(
                hotkeys.get("toggle_mode", "<ctrl>+<alt>+m")
            ),
            quit=_normalize_hotkey(hotkeys.get("quit", "<ctrl>+<alt>+q")),
        ),
        audio=AudioConfig(device=device_value, sample_rate=sample_rate),
        transcription=TranscriptionConfig(
            model=str(transcription.get("model", "small")),
            language=_optional_string(transcription.get("language")),
            device=str(transcription.get("device", "auto")),
            compute_type=str(transcription.get("compute_type", "auto")),
            beam_size=int(transcription.get("beam_size", 5)),
        ),
        openai=OpenAIConfig(
            model=str(openai.get("model", "gpt-transcribe")),
            base_url=str(
                openai.get("base_url", "https://api.openai.com/v1")
            ).rstrip("/"),
            timeout=float(openai.get("timeout", 120)),
        ),
        indicator=IndicatorConfig(
            anchor=anchor,
            x_offset=int(indicator.get("x_offset", 0)),
            y_offset=int(indicator.get("y_offset", 8)),
            width=max(120, int(indicator.get("width", 210))),
            height=max(28, int(indicator.get("height", 42))),
        ),
    )
