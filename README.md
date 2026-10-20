# Computer — LCARS AI Assistant

A voice-first, local-first desktop assistant inspired by the LCARS interface from *Star Trek: The Next Generation*.

## Current application

Computer now opens into a voice-first LCARS desktop panel rather than stopping at the model status screen. The panel supports microphone capture, local speech recognition, local Ollama conversation, system speech output, an optional explicit web-search command, an encrypted notes vault, tray controls, a draggable panel, and a remembered monitor preference.

### Voice interaction

1. Install/start Ollama and download a model in **LOCAL AI SETUP**.
2. Once the local model is ready, say **“Computer”** followed by your request. The app continuously checks short microphone windows using local Whisper tiny.en; after the wake word, it records the request and ends on silence.
3. Alternatively, press **LISTEN** and then **STOP LISTENING** to use manual recording.
4. Computer transcribes locally with faster-whisper, sends the transcript to the local Ollama model, and reads the answer aloud using the operating system speech engine.
4. Say “search the web for …” or “look up online …” to explicitly request web lookup. Ordinary requests do not trigger web lookup.

The Whisper `base` model is downloaded from Hugging Face on first use unless `LCARSAI_WHISPER_MODEL` is set. That first download needs internet; later transcription is local. The Ollama model must already be installed. Speech synthesis uses system voices; on Linux, `espeak-ng` may need to be installed separately.

### Local runtime and models

- Runtime files: per-user Computer data directory, configurable with `LCARSAI_DATA_DIR`.
- Model files: configurable with `LCARSAI_MODELS_DIR`.
- Ollama endpoint: `http://127.0.0.1:11434`; non-local endpoints are blocked by default.
- Available model presets: Qwen3 4B, 8B, and 14B.
- The app starts a managed Ollama runtime when one is installed but not running. It does not install a system service or use administrator privileges.
- Runtime downloads use official Ollama download endpoints with TLS certificate verification enabled.

### Encrypted personal vault

The optional vault encrypts note contents using Fernet with a randomly generated data key. That key is wrapped independently by a passphrase and a recovery key using scrypt-derived keys. The recovery key is shown once at creation; store it outside this computer. Losing both the passphrase and recovery key means the vault cannot be recovered. The vault is local and does not sync across machines automatically.

### Panel behavior

- Borderless LCARS panel with segmented LCARS-style side rail, status bands, and amber/purple interface palette.
- Monitor preference and manually moved panel position are remembered.
- Tray menu can restore or hide the panel and quit the application.
- The panel hides seven seconds after speech output completes; restore it from the system tray.

## Platform notes

- Supported packaging targets: Windows x86-64 and Linux x86-64.
- First-time Whisper and Ollama/model downloads require internet.
- Microphone capture requires an available input device and OS microphone permission.
- Linux audio dependencies can vary by distribution. Install PortAudio and espeak-ng if the system reports missing audio backends.
- This project is not a system daemon. The app-managed Ollama process is stopped when Computer exits; an Ollama instance that was already running is not terminated.

## Development

Python 3.11+, with dependencies from `pyproject.toml`.

```bash
python -m pip install -e ".[dev]"
python -m pytest -q
python -m lcarsai.main
```

## Planned / not yet complete

- Voice enrollment and speaker recognition.
- Animated audio-reactive LCARS visualization and richer per-screen positioning controls.
- Secure cross-device vault synchronization and a separate recovery workflow UI.
- Automatic background startup at OS login.

No cloud transcription is enabled. Web lookup occurs only when the user explicitly requests it. The vault is encrypted at rest, but the application has not undergone an independent security audit.
