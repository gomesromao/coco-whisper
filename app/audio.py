"""Microphone capture."""
from __future__ import annotations

import logging
import threading
import wave

import numpy as np
import sounddevice as sd

log = logging.getLogger(__name__)

SAMPLE_RATE = 16000
CHANNELS = 1
MIN_SECONDS = 0.35


class RecordingError(RuntimeError):
    pass


class Recorder:
    """Records mono 16 kHz audio from the selected input device."""

    def __init__(self) -> None:
        self._stream: sd.InputStream | None = None
        self._chunks: list[np.ndarray] = []
        self._lock = threading.Lock()
        self._peak = 0.0

    @property
    def is_recording(self) -> bool:
        return self._stream is not None

    def _callback(self, indata, frames, time_info, status) -> None:
        if status:
            log.debug("audio status: %s", status)
        block = indata.copy().reshape(-1)
        with self._lock:
            self._chunks.append(block)
            peak = float(np.abs(block).max()) if block.size else 0.0
            if peak > self._peak:
                self._peak = peak

    def start(self, device=None) -> None:
        if self._stream is not None:
            return
        with self._lock:
            self._chunks = []
            self._peak = 0.0
        try:
            self._stream = sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=CHANNELS,
                dtype="float32",
                blocksize=1024,
                device=device,
                callback=self._callback,
            )
            self._stream.start()
        except Exception as exc:  # sounddevice raises a variety of errors
            self._stream = None
            raise RecordingError(str(exc)) from exc

    def stop(self) -> tuple[np.ndarray, float]:
        """Stop and return (audio, peak_level). Audio is float32 mono 16 kHz."""
        stream, self._stream = self._stream, None
        if stream is not None:
            try:
                # abort, not stop: stop() asks PortAudio to drain its pending
                # buffers first, and that wait can hang on macOS. When it does,
                # it hangs the thread that was closing out the dictation, so
                # the overlay stays up, nothing is pasted, and not one line is
                # written anywhere. Push to talk has nothing to drain for: the
                # audio is already in _chunks by the time we get here.
                stream.abort()
                stream.close()
            except Exception:  # already closed or device vanished
                log.exception("failed to close input stream")
        with self._lock:
            chunks, peak = self._chunks, self._peak
            self._chunks = []
        if not chunks:
            return np.zeros(0, dtype="float32"), 0.0
        try:
            return np.concatenate(chunks).astype("float32"), peak
        except Exception:
            # Losing the take is bad. Taking the app down with it is worse.
            log.exception("the captured audio could not be assembled")
            return np.zeros(0, dtype="float32"), 0.0

    @property
    def seconds(self) -> float:
        with self._lock:
            return sum(c.size for c in self._chunks) / SAMPLE_RATE


def list_input_devices() -> list[tuple[int, str]]:
    devices = []
    try:
        for idx, dev in enumerate(sd.query_devices()):
            if dev.get("max_input_channels", 0) > 0:
                devices.append((idx, dev.get("name", f"Device {idx}")))
    except Exception:
        log.exception("could not query input devices")
    return devices


def save_wav(path, audio: np.ndarray) -> None:
    pcm = np.clip(audio, -1.0, 1.0)
    pcm = (pcm * 32767).astype("<i2")
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(CHANNELS)
        handle.setsampwidth(2)
        handle.setframerate(SAMPLE_RATE)
        handle.writeframes(pcm.tobytes())
