from pathlib import Path
from typing import Any

import httpx
import pytest

from whisper_shortcut.config import OpenAIConfig
from whisper_shortcut.transcriber import OpenAITranscriber, clean_transcript


def test_clean_transcript_joins_nonempty_segments() -> None:
    assert clean_transcript([" Hello ", "", " world.  "]) == "Hello world."


def test_clean_transcript_handles_silence() -> None:
    assert clean_transcript([" ", "\n"]) == ""


@pytest.mark.parametrize(
    ("model", "field"),
    [("gpt-transcribe", "languages[]"), ("whisper-1", "language")],
)
def test_openai_language_field_matches_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, model: str, field: str
) -> None:
    sent: dict[str, Any] = {}

    def fake_post(url: str, **kwargs: Any) -> httpx.Response:
        sent.update(kwargs["data"])
        return httpx.Response(200, json={"text": " Hello. "})

    monkeypatch.setattr(httpx, "post", fake_post)
    audio = tmp_path / "audio.wav"
    audio.write_bytes(b"")
    transcriber = OpenAITranscriber(OpenAIConfig(model=model), "de", lambda: "key")

    assert transcriber.transcribe(audio) == "Hello."
    assert sent["model"] == model
    assert sent[field] == "de"
    assert {"language", "languages[]"} & sent.keys() == {field}
