"""Local microphone capture, speech recognition, and speech synthesis."""
from __future__ import annotations

import os
import tempfile
import threading
import wave
from pathlib import Path

SAMPLE_RATE = 16_000


def record_until_stopped(stop_event: threading.Event, max_seconds: int = 45):
    """Capture microphone audio until stopped; returns float32 mono audio."""
    try:
        import numpy as np
        import sounddevice as sd
    except ImportError as exc:
        raise RuntimeError("Voice input dependencies are missing. Reinstall the latest Computer build.") from exc

    chunks = []
    done = threading.Event()
    failure = []

    def callback(indata, frames, time_info, status):
        if status:
            # Audio under/overruns are recoverable; keep the recording.
            pass
        chunks.append(indata.copy())
        if len(chunks) * frames >= SAMPLE_RATE * max_seconds:
            done.set()
            raise sd.CallbackStop()

    try:
        with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32", callback=callback):
            while not stop_event.is_set() and not done.wait(0.1):
                pass
    except Exception as exc:
        raise RuntimeError(f"Could not record from the microphone: {exc}") from exc
    if not chunks:
        raise RuntimeError("No microphone audio was captured. Check the selected input device and permissions.")
    return np.concatenate(chunks, axis=0).reshape(-1)


def transcribe_local(audio) -> str:
    """Transcribe speech locally with faster-whisper; the model downloads on first use."""
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError("Local speech recognition is not installed in this build.") from exc
    model_name = os.environ.get("LCARSAI_WHISPER_MODEL", "base")
    try:
        model = WhisperModel(model_name, device="auto", compute_type="int8")
        segments, _ = model.transcribe(audio, vad_filter=True, beam_size=3)
        text = " ".join(segment.text.strip() for segment in segments).strip()
    except Exception as exc:
        raise RuntimeError(f"Local speech recognition failed: {exc}") from exc
    if not text:
        raise RuntimeError("I didn't catch any speech. Press LISTEN and try again.")
    return text


def speak_local(text: str) -> None:
    """Speak a response using the operating system's installed speech engine."""
    try:
        import pyttsx3
        engine = pyttsx3.init()
        engine.setProperty("rate", 178)
        engine.say(text)
        engine.runAndWait()
        engine.stop()
    except Exception as exc:
        raise RuntimeError(
            "Speech output is unavailable. On Linux, install espeak-ng; on Windows, "
            f"check that a system speech voice is available. Details: {exc}"
        ) from exc
