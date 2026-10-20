# Computer — LCARS AI Assistant

A voice-first, local-first desktop assistant inspired by the LCARS interface from *Star Trek: The Next Generation*.

## Project status

**Early development scaffold.** The desktop shell, basic configuration helpers, local Ollama availability check, and starter tests are in the repository. Voice interaction, encrypted storage, model management, and installers are not implemented yet.

## Current development baseline

- Python 3.11+
- PySide6 desktop shell
- Checks for an already-running Ollama service at `http://127.0.0.1:11434`
- Does not download or install inference runtimes automatically
- Basic configuration for a local per-user data directory
- GitHub Actions test workflow for Windows and Ubuntu, Python 3.11 and 3.12

### Run from a development checkout

Create and activate a virtual environment, then run:

```bash
python -m pip install -e ".[dev]"
python -m pytest -q
python -m lcarsai.main
```

On Linux, install your distribution's required Qt system libraries if PySide6 reports missing shared libraries. These commands have not yet been verified on a user's machine; CI is configured but must complete successfully before the baseline can be considered validated.

## Planned features

- Wake phrase: **“Computer”**
- Voice-first interaction; text input is out of scope for the initial version
- Local speech recognition, language model, and speech synthesis
- LCARS-inspired animated interface with listening, processing, and speaking states
- Optional web lookup only when explicitly requested
- Encrypted personal data vault with a separate recovery mechanism
- Windows and Linux builds with shared user data and OS-specific runtimes
- Secondary-monitor display preference, with platform-aware fallbacks
- Setup flow for model and data locations
- Automated tests and separate Windows/Linux packaging workflows

## Intended technical direction

The implementation will evaluate a Qt/PySide desktop UI, a local inference runtime, local speech-to-text and text-to-speech, and a wake-word detector. GPU acceleration must be detected and validated on each platform; AMD support must not be assumed from the presence of a compatible-looking runtime.

## Safety and privacy principles

- No cloud transcription by default.
- Voice matching is an auxiliary signal, not the encryption key.
- Do not persist raw enrollment audio by default.
- Never write to the shared data vault when the filesystem is unavailable or unsafe.
- Keep Windows and Linux runtime files separate from shared user data.
- Do not treat a local data directory as encrypted storage; vault encryption remains future work.
- Document what is implemented, tested, and still experimental.
