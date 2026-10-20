"""Local microphone capture, speech recognition, and speech synthesis."""
from __future__ import annotations

import os
import threading

SAMPLE_RATE = 16_000


def list_input_devices() -> list[dict]:
    """Return available PortAudio input devices for diagnostics and UI selection."""
    try:
        import sounddevice as sd
        devices = sd.query_devices()
        return [
            {
                "index": index,
                "name": str(device["name"]),
                "channels": int(device["max_input_channels"]),
                "default_samplerate": int(device["default_samplerate"]),
                "hostapi": str(sd.query_hostapis(int(device["hostapi"]))["name"]),
            }
            for index, device in enumerate(devices)
            if int(device["max_input_channels"]) > 0
        ]
    except Exception as exc:
        raise RuntimeError(f"Unable to enumerate audio input devices: {exc}") from exc


def _resample_mono(audio, source_rate: int, target_rate: int):
    """Convert mono samples to Whisper's 16 kHz rate without an extra audio dependency."""
    import numpy as np
    if source_rate == target_rate:
        return np.asarray(audio, dtype=np.float32).reshape(-1)
    samples = np.asarray(audio, dtype=np.float32).reshape(-1)
    if not samples.size:
        return samples
    target_length = max(1, round(len(samples) * target_rate / source_rate))
    old_positions = np.arange(len(samples), dtype=np.float64)
    new_positions = np.arange(target_length, dtype=np.float64) * source_rate / target_rate
    return np.interp(new_positions, old_positions, samples).astype(np.float32)


def record_until_stopped(
    stop_event: threading.Event, max_seconds: int = 45, auto_stop: bool = False,
    silence_seconds: float = 1.15,
):
    """Capture audio from the default input or a working alternative until stopped."""
    try:
        import numpy as np
        import sounddevice as sd
    except ImportError as exc:
        raise RuntimeError(
            "Voice input dependencies are missing. Reinstall the latest Computer build."
        ) from exc

    try:
        devices = sd.query_devices()
    except Exception as exc:
        raise RuntimeError(
            f"Computer could not enumerate audio devices: {exc}. On Linux, check that "
            "PipeWire/PulseAudio is running and that PortAudio is installed."
        ) from exc

    try:
        default_input = int(sd.default.device[0])
    except Exception:
        default_input = -1

    candidates = []
    if 0 <= default_input < len(devices) and int(devices[default_input]["max_input_channels"]) > 0:
        candidates.append(default_input)
    candidates.extend(
        i for i, device in enumerate(devices)
        if int(device["max_input_channels"]) > 0 and i not in candidates
    )
    if not candidates:
        raise RuntimeError(
            "No microphone/input device is available to Computer. Check the system audio "
            "settings and microphone permissions, then restart Computer."
        )

    errors = []
    for device_index in candidates:
        device = devices[device_index]
        channels = min(1, int(device["max_input_channels"]))
        default_rate = int(float(device["default_samplerate"])) or 48_000
        rates = []
        for rate in (default_rate, 48_000, 44_100, 32_000, 16_000):
            if rate not in rates:
                rates.append(rate)
        for rate in rates:
            chunks = []
            done = threading.Event()
            frame_count = [0]
            speech_state = {"started": False, "silence_frames": 0}

            def callback(indata, frames, time_info, status):
                chunks.append(indata.copy())
                frame_count[0] += frames
                if auto_stop:
                    level = float(np.sqrt(np.mean(np.square(indata))))
                    if level >= 0.012:
                        speech_state["started"] = True
                        speech_state["silence_frames"] = 0
                    elif speech_state["started"]:
                        speech_state["silence_frames"] += frames
                    if speech_state["started"] and speech_state["silence_frames"] >= rate * silence_seconds:
                        done.set()
                        raise sd.CallbackStop()
                if frame_count[0] >= rate * max_seconds:
                    done.set()
                    raise sd.CallbackStop()

            try:
                with sd.InputStream(
                    device=device_index,
                    samplerate=rate,
                    channels=channels,
                    dtype="float32",
                    callback=callback,
                ):
                    while not stop_event.is_set() and not done.wait(0.1):
                        pass
                if not chunks:
                    errors.append(f"{device['name']} at {rate} Hz: no audio captured")
                    continue
                audio = np.concatenate(chunks, axis=0)
                if audio.ndim > 1:
                    audio = audio.mean(axis=1)
                return _resample_mono(audio, rate, SAMPLE_RATE)
            except Exception as exc:
                errors.append(f"{device['name']} at {rate} Hz: {exc}")
                # A failed stream open is safe to retry with another supported rate/device.
                continue

    details = " | ".join(errors[:6])
    raise RuntimeError(
        "Computer could not open any microphone input stream. Check your selected input "
        "in KDE System Settings → Audio and confirm PipeWire is running. "
        f"Device errors: {details or 'no compatible input stream'}"
    )


_whisper_model = None


def transcribe_local(audio) -> str:
    """Transcribe speech locally with faster-whisper; the model downloads on first use."""
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError("Local speech recognition is not installed in this build.") from exc
    model_name = os.environ.get("LCARSAI_WHISPER_MODEL", "base")
    global _whisper_model
    try:
        if _whisper_model is None:
            _whisper_model = WhisperModel(model_name, device="auto", compute_type="int8")
        segments, _ = _whisper_model.transcribe(audio, vad_filter=True, beam_size=3)
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


def wait_for_wake_word(stop_event: threading.Event, wake_word: str = "computer") -> None:
    """Listen continuously and return when local Whisper hears the configured wake word.

    This is fully offline after the tiny.en model has been cached. It deliberately uses
    short overlapping windows so the wake word can straddle a chunk boundary.
    """
    import queue
    import time
    import numpy as np
    import sounddevice as sd
    from faster_whisper import WhisperModel

    try:
        devices = sd.query_devices()
    except Exception as exc:
        raise RuntimeError(f"Cannot enumerate microphone devices for wake-word listening: {exc}") from exc

    try:
        default_input = int(sd.default.device[0])
    except Exception:
        default_input = -1
    candidates = []
    if 0 <= default_input < len(devices) and int(devices[default_input]["max_input_channels"]) > 0:
        candidates.append(default_input)
    candidates.extend(i for i, d in enumerate(devices)
                      if int(d["max_input_channels"]) > 0 and i not in candidates)
    if not candidates:
        raise RuntimeError("No microphone is available for wake-word listening.")

    model = WhisperModel(
        os.environ.get("LCARSAI_WAKE_MODEL", "tiny.en"),
        device="auto",
        compute_type="int8",
    )
    errors = []
    for device_index in candidates:
        device = devices[device_index]
        source_rate = int(float(device["default_samplerate"])) or 48_000
        rates = list(dict.fromkeys((source_rate, 48_000, 44_100, 32_000, 16_000)))
        for rate in rates:
            audio_queue = queue.Queue()
            def callback(indata, frames, time_info, status):
                audio_queue.put(indata.copy())
            try:
                with sd.InputStream(device=device_index, samplerate=rate, channels=1,
                                    dtype="float32", callback=callback, blocksize=0):
                    buffer = np.empty(0, dtype=np.float32)
                    last_check = 0.0
                    while not stop_event.is_set():
                        try:
                            chunk = audio_queue.get(timeout=0.2).reshape(-1)
                        except queue.Empty:
                            continue
                        buffer = np.concatenate((buffer, chunk))
                        # Decode a 2.4-second window roughly once per second, with overlap.
                        if len(buffer) < int(rate * 2.4):
                            continue
                        if time.monotonic() - last_check < 0.85:
                            continue
                        last_check = time.monotonic()
                        window = buffer[-int(rate * 3.2):]
                        samples = _resample_mono(window, rate, SAMPLE_RATE)
                        try:
                            segments, _ = model.transcribe(
                                samples, language="en", beam_size=1, best_of=1,
                                vad_filter=False, condition_on_previous_text=False,
                            )
                            heard = " ".join(segment.text for segment in segments).lower()
                        except Exception:
                            heard = ""
                        if wake_word.lower() in heard.split():
                            return
                        # Keep a 1.2-second overlap to avoid chopping the keyword.
                        buffer = buffer[-int(rate * 1.2):]
                if stop_event.is_set():
                    return
            except Exception as exc:
                errors.append(f"{device['name']} at {rate} Hz: {exc}")
                continue
    if not stop_event.is_set():
        raise RuntimeError("Wake-word microphone failed: " + " | ".join(errors[:4]))
