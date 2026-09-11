"""Speech to text engine (faster-whisper, fully local)."""
from __future__ import annotations

import logging
import os
import threading

import numpy as np

from .config import models_dir
from .platform_support import IS_MAC, IS_WINDOWS

log = logging.getLogger(__name__)

# label, model id, approximate download size
MODEL_CATALOG = [
    ("Tiny (fastest, least accurate)", "tiny", "75 MB"),
    ("Base (fast)", "base", "145 MB"),
    ("Small (recommended)", "small", "480 MB"),
    ("Medium (accurate, slower)", "medium", "1.5 GB"),
    ("Turbo (most accurate)", "large-v3-turbo", "1.6 GB"),
]

LANGUAGES = [
    ("Auto detect", "auto"),
    ("English", "en"),
    ("Portuguese", "pt"),
    ("Tagalog", "tl"),
    ("Taglish (Tagalog + English)", "taglish"),
]

# Whisper invents these on silence or noise. Drop them when they are the
# entire result.
HALLUCINATIONS = {
    "thank you.", "thanks for watching!", "thank you for watching.",
    "you", "bye.", "okay.", ".", "...",
    "legendas pela comunidade amara.org", "amara.org",
    "legendado pela comunidade amara.org",
    "subtitles by the amara.org community",
    "obrigado.", "tchau.",
}

TAGLISH_PROMPT = (
    "Ito ay isang mixed Tagalog and English conversation. Sinasabi ng speaker, "
    "okay so I will send the report later, pero kailangan ko muna i-check "
    "yung client feedback."
)


CUDA_LIBS = ("cublas64_12.dll", "cudnn_ops64_9.dll")


def _cuda_libs_present() -> bool:
    """A GPU is useless to us without the CUDA runtime libraries."""
    if not IS_WINDOWS:
        return True  # only Windows ships these as separate DLLs to look up
    import ctypes

    for name in CUDA_LIBS:
        try:
            ctypes.WinDLL(name)
        except OSError:
            log.info("cuda library %s not found, staying on cpu", name)
            return False
    return True


def cuda_available() -> bool:
    if IS_MAC:
        return False  # no CUDA on Apple hardware
    try:
        import ctranslate2

        if ctranslate2.get_cuda_device_count() <= 0:
            return False
    except Exception:
        return False
    return _cuda_libs_present()


def auto_model() -> str:
    if cuda_available():
        return "large-v3-turbo"
    cores = os.cpu_count() or 4
    if cores >= 12:
        return "large-v3-turbo"
    if cores >= 6:
        return "small"
    return "base"


def auto_device() -> str:
    return "cuda" if cuda_available() else "cpu"


class Engine:
    """Loads a Whisper model and transcribes audio buffers."""

    def __init__(self) -> None:
        self._model = None
        self._key: tuple | None = None
        self._lock = threading.Lock()
        self._forced_cpu = False

    @property
    def loaded_key(self) -> tuple | None:
        return self._key

    def resolve(self, model: str, device: str) -> tuple[str, str, str]:
        model_id = auto_model() if model == "auto" else model
        dev = auto_device() if device == "auto" else device
        if dev == "cuda" and self._forced_cpu:
            dev = "cpu"
        if dev == "cuda" and not cuda_available():
            log.warning("cuda requested but unavailable, using cpu")
            dev = "cpu"
        compute = "float16" if dev == "cuda" else "int8"
        return model_id, dev, compute

    def load(self, model: str, device: str, progress=None):
        """Load the model, downloading it on first use. Returns the model."""
        model_id, dev, compute = self.resolve(model, device)
        key = (model_id, dev, compute)
        with self._lock:
            if self._model is not None and self._key == key:
                return self._model
            if progress:
                progress(f"Loading {model_id} on {dev.upper()}...")
            from faster_whisper import WhisperModel

            threads = max(4, min(8, (os.cpu_count() or 4)))
            model_obj = WhisperModel(
                model_id,
                device=dev,
                compute_type=compute,
                cpu_threads=threads,
                download_root=str(models_dir()),
            )
            if dev == "cuda" and not self._gpu_works(model_obj):
                log.warning("gpu path failed its smoke test, reloading on cpu")
                self._forced_cpu = True
                dev, compute = "cpu", "int8"
                key = (model_id, dev, compute)
                model_obj = WhisperModel(
                    model_id,
                    device=dev,
                    compute_type=compute,
                    cpu_threads=threads,
                    download_root=str(models_dir()),
                )
            self._model = model_obj
            self._key = key
            log.info("model loaded: %s device=%s compute=%s", model_id, dev, compute)
            return self._model

    @staticmethod
    def _gpu_works(model_obj) -> bool:
        """Some machines report a GPU but lack the CUDA runtime libraries."""
        try:
            silence = np.zeros(16000, dtype="float32")
            segments, _ = model_obj.transcribe(silence, language="en", vad_filter=False)
            list(segments)
            return True
        except Exception as exc:
            log.warning("gpu smoke test failed: %s", exc)
            return False

    def unload(self) -> None:
        with self._lock:
            self._model = None
            self._key = None

    def transcribe(self, audio: np.ndarray, language: str, model: str, device: str) -> dict:
        model_obj = self.load(model, device)
        lang, prompt = self._language_args(language)
        _, dev, _ = self.resolve(model, device)
        segments, info = model_obj.transcribe(
            audio,
            language=lang,
            initial_prompt=prompt,
            beam_size=5 if dev == "cuda" else 1,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 400},
            condition_on_previous_text=False,
            temperature=[0.0, 0.2, 0.4],
        )
        parts = [seg.text.strip() for seg in segments]
        text = " ".join(p for p in parts if p).strip()
        if text.lower().strip() in HALLUCINATIONS:
            log.info("dropped likely hallucination: %r", text)
            text = ""
        return {
            "text": text,
            "language": getattr(info, "language", lang or "?"),
            "probability": getattr(info, "language_probability", 0.0),
        }

    @staticmethod
    def _language_args(language: str) -> tuple[str | None, str | None]:
        if language == "auto":
            return None, None
        if language == "taglish":
            return "tl", TAGLISH_PROMPT
        return language, None
