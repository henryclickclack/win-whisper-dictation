from pathlib import Path

import pytest

from whisper_shortcut.config import DEFAULT_CONFIG, load_config


def test_default_config_loads(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"

    config = load_config(path)

    assert path.read_text(encoding="utf-8") == DEFAULT_CONFIG
    assert config.hotkeys.toggle_recording == "<ctrl>+<alt>+<space>"
    assert config.audio.sample_rate == 16_000
    assert config.indicator.anchor == "top-center"


def test_config_accepts_position_and_device(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        """
[audio]
device = 2
sample_rate = 48000

[indicator]
anchor = "top-right"
x_offset = -10
y_offset = 30
""",
        encoding="utf-8",
    )

    config = load_config(path)

    assert config.audio.device == 2
    assert config.audio.sample_rate == 48_000
    assert config.indicator.anchor == "top-right"
    assert config.indicator.x_offset == -10
    assert config.indicator.y_offset == 30


def test_invalid_anchor_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text('[indicator]\nanchor = "middle"\n', encoding="utf-8")

    with pytest.raises(ValueError, match="indicator.anchor"):
        load_config(path)


def test_legacy_space_hotkey_is_normalized(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        '[hotkeys]\ntoggle_recording = "<ctrl>+<alt>+space"\n',
        encoding="utf-8",
    )

    config = load_config(path)

    assert config.hotkeys.toggle_recording == "<ctrl>+<alt>+<space>"
