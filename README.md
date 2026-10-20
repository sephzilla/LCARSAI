# Computer — LCARS AI Assistant

A voice-first, local-first desktop assistant inspired by the LCARS interface from *Star Trek: The Next Generation*.

## Project status

**Early development scaffold.** The LCARS desktop shell now includes a first-run local AI setup dialog. It can download official Ollama runtime binaries into a per-user Computer data directory on supported Windows/Linux x86-64 systems, start the local service, and pull a selected model through Ollama's local API. Voice interaction, encrypted storage, wake-word detection, and speech recognition/synthesis are still not implemented.

## First-run setup

1. Launch Computer and choose **LOCAL AI SETUP**.
2. Choose **Install / Start Runtime**. Computer downloads the official Ollama bundle into its own per-user runtime folder and starts it locally. It does not use sudo, install system packages, or register a system service.
3. Select a model and choose **Download Model**. The default is `qwen3:8b`; smaller `qwen3:4b` and larger `qwen3:14b` options are available.
4. Model files default to the Computer data directory, configurable with `LCARSAI_MODELS_DIR`. The app data root can be changed with `LCARSAI_DATA_DIR`.

Runtime downloads come from the official Ollama download endpoints and model weights are fetched by Ollama from its model registry. Downloads require internet access and may be several gigabytes. No cloud inference or cloud transcription is enabled by this setup flow. On Linux, this currently downloads the standard AMD64 runtime bundle; GPU acceleration depends on the host drivers and Ollama runtime compatibility and is not guaranteed. The app starts the runtime as a child process for the current session; it does not install a background system service.

If Ollama is already running on localhost, Computer can use it. In that case, its existing service may control the model storage path, rather than Computer's managed model folder.

## Development

- Python 3.11+
- PySide6 desktop UI
- Ollama local runtime setup for Windows and Linux x86-64
- Tests run in GitHub Actions on Windows and Ubuntu, Python 3.11 and 3.12

Create and activate a virtual environment, then run:

```bash
python -m pip install -e ".[dev]"
python -m pytest -q
python -m lcarsai.main
```

On Linux, install your distribution's required Qt system libraries if PySide6 reports missing shared libraries.

## Planned features

- Wake phrase: **“Computer”**
- Voice-first interaction; text input is out of scope for the initial version
- Local speech recognition and synthesis
- LCARS-inspired animated interface with listening, processing, and speaking states
- Optional web lookup only when explicitly requested
- Encrypted personal data vault with a separate recovery mechanism
- Shared user data with OS-specific runtimes
- Secondary-monitor display preference, with platform-aware fallbacks
- Setup flow for model and data locations
- Automated tests and separate Windows/Linux packaging workflows

## Safety and privacy principles

- No cloud transcription by default.
- Voice matching is an auxiliary signal, not the encryption key.
- Do not persist raw enrollment audio by default.
- Never write to a shared data vault when the filesystem is unavailable or unsafe.
- Keep Windows and Linux runtime files separate from shared user data.
- Do not treat a local data directory as encrypted storage; vault encryption remains future work.
- Document what is implemented, tested, and still experimental.
