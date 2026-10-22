from __future__ import annotations

import tempfile
import threading
import wave
from pathlib import Path
from typing import Any

import numpy as np
import sounddevice as sd

from .config import AudioConfig


class AudioRecorder:
    """Records mono 16-bit PCM audio until stop() is called."""

    def __init__(self, config: AudioConfig) -> None:
        self._config = config
        self._stream: sd.InputStream | None = None
        self._chunks: list[np.ndarray[Any, Any]] = []
        self._lock = threading.Lock()
        self._level = 0.0

    @property
    def is_recording(self) -> bool:
        return self._stream is not None

    @property
    def level(self) -> float:
        """Loudness of the most recent audio block, scaled to 0..1 for display."""
        if self._stream is None:
            return 0.0
        return self._level

    def start(self) -> None:
        if self._stream is not None:
            raise RuntimeError("Recording is already active")

        with self._lock:
            self._chunks.clear()
        self._level = 0.0

        self._stream = sd.InputStream(
            samplerate=self._config.sample_rate,
            channels=1,
            dtype="int16",
            device=self._config.device,
            callback=self._on_audio,
        )
        try:
            self._stream.start()
        except Exception:
            self._stream.close()
            self._stream = None
            raise

    def _on_audio(
        self,
        indata: np.ndarray[Any, Any],
        _frames: int,
        _time: Any,
        status: sd.CallbackFlags,
    ) -> None:
        if status.input_overflow:
            # Keep recording; a small dropped interval is preferable to aborting.
            pass
        rms = float(np.sqrt(np.mean(np.square(indata.astype(np.float32))))) / 32768
        # Quiet speech sits around 0.01-0.05 RMS; compress so it stays visible.
        self._level = min(1.0, (rms * 8) ** 0.6)
        with self._lock:
            self._chunks.append(indata.copy())

    def stop(self) -> Path:
        stream = self._stream
        if stream is None:
            raise RuntimeError("Recording is not active")

        self._stream = None
        stream.stop()
        stream.close()

        with self._lock:
            chunks = self._chunks
            self._chunks = []

        if not chunks:
            raise RuntimeError("No microphone audio was captured")

        samples = np.concatenate(chunks, axis=0)
        with tempfile.NamedTemporaryFile(
            prefix="whisper-shortcut-",
            suffix=".wav",
            delete=False,
        ) as handle:
            path = Path(handle.name)

        with wave.open(str(path), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(self._config.sample_rate)
            wav.writeframes(samples.tobytes())
        return path

    def cancel(self) -> None:
        stream = self._stream
        self._stream = None
        if stream is not None:
            stream.stop()
            stream.close()
        with self._lock:
            self._chunks.clear()
