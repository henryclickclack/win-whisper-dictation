from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

from .config import OpenAIConfig, TranscriptionConfig

LOGGER = logging.getLogger(__name__)


def clean_transcript(parts: list[str]) -> str:
    return " ".join(part.strip() for part in parts if part.strip()).strip()


class LocalTranscriber:
    """Lazily loads one faster-whisper model and reuses it between recordings."""

    def __init__(self, config: TranscriptionConfig) -> None:
        self._config = config
        self._model: Any = None
        self._active_device: str | None = None
        self._lock = threading.Lock()

    @property
    def active_device(self) -> str | None:
        return self._active_device

    def warm_up(self) -> None:
        with self._lock:
            self._ensure_model()

    def _load_model(self, device: str) -> Any:
        from faster_whisper import WhisperModel

        compute_type = self._config.compute_type
        if compute_type == "auto":
            compute_type = "float16" if device == "cuda" else "int8"
        return WhisperModel(
            self._config.model,
            device=device,
            compute_type=compute_type,
        )

    def _ensure_model(self) -> None:
        if self._model is not None:
            return

        requested = self._config.device
        if requested != "auto":
            self._model = self._load_model(requested)
            self._active_device = requested
            return

        try:
            self._model = self._load_model("cuda")
            self._active_device = "cuda"
            LOGGER.info("Using CUDA for transcription")
        except Exception:
            LOGGER.warning(
                "CUDA initialization failed; using CPU transcription",
                exc_info=True,
            )
            self._model = self._load_model("cpu")
            self._active_device = "cpu"

    def _use_cpu_fallback(self) -> None:
        self._model = self._load_model("cpu")
        self._active_device = "cpu"

    def transcribe(self, audio_path: Path) -> str:
        with self._lock:
            self._ensure_model()
            try:
                return self._transcribe_loaded(audio_path)
            except Exception:
                if (
                    self._config.device == "auto"
                    and self._active_device == "cuda"
                ):
                    LOGGER.warning(
                        "CUDA transcription failed; retrying once on CPU",
                        exc_info=True,
                    )
                    self._use_cpu_fallback()
                    return self._transcribe_loaded(audio_path)
                raise

    def _transcribe_loaded(self, audio_path: Path) -> str:
        segments, _info = self._model.transcribe(
            str(audio_path),
            language=self._config.language,
            beam_size=self._config.beam_size,
            vad_filter=True,
        )
        return clean_transcript([segment.text for segment in segments])


class OpenAITranscriber:
    """Sends recordings to the OpenAI audio transcription endpoint."""

    def __init__(
        self,
        config: OpenAIConfig,
        language: str | None,
        key_source: Callable[[], str | None],
    ) -> None:
        self._config = config
        self._language = language
        self._key_source = key_source

    def require_key(self) -> str:
        key = self._key_source()
        if not key:
            raise RuntimeError("No OpenAI key: set OPENAI_API_KEY in .env")
        return key

    def warm_up(self) -> None:
        pass

    def transcribe(self, audio_path: Path) -> str:
        import httpx

        key = self.require_key()
        data = {"model": self._config.model, "response_format": "json"}
        if self._language:
            # gpt-transcribe replaces the singular language field with a list.
            field = (
                "languages[]"
                if self._config.model.startswith("gpt-transcribe")
                else "language"
            )
            data[field] = self._language
        with audio_path.open("rb") as audio:
            response = httpx.post(
                f"{self._config.base_url}/audio/transcriptions",
                headers={"Authorization": f"Bearer {key}"},
                data=data,
                files={"file": (audio_path.name, audio, "audio/wav")},
                timeout=self._config.timeout,
            )
        if response.is_error:
            try:
                detail = response.json()["error"]["message"]
            except Exception:
                detail = response.text[:200]
            raise RuntimeError(f"OpenAI API {response.status_code}: {detail}")
        return clean_transcript([str(response.json().get("text", ""))])


class _Backend(Protocol):
    def warm_up(self) -> None: ...

    def transcribe(self, audio_path: Path) -> str: ...


class SwitchableTranscriber:
    """Routes transcription to the local model or the OpenAI API."""

    LABELS = {"local": "Local", "openai": "OpenAI API"}
    SHORT_LABELS = {"local": "LOCAL", "openai": "API"}

    def __init__(
        self,
        local: _Backend,
        remote: OpenAITranscriber,
        mode: str = "local",
        on_change: Callable[[str], None] | None = None,
    ) -> None:
        self._backends: dict[str, _Backend] = {"local": local, "openai": remote}
        self._remote = remote
        self._mode = mode if mode in self._backends else "local"
        self._on_change = on_change

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def short_label(self) -> str:
        return self.SHORT_LABELS[self._mode]

    def toggle(self) -> str:
        """Switches mode and returns its display name."""
        mode = "local" if self._mode == "openai" else "openai"
        if mode == "openai":
            self._remote.require_key()
        self._mode = mode
        if self._on_change is not None:
            self._on_change(mode)
        return self.LABELS[mode]

    def warm_up(self) -> None:
        self._backends[self._mode].warm_up()

    def transcribe(self, audio_path: Path) -> str:
        return self._backends[self._mode].transcribe(audio_path)
