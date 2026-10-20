# Computer — LCARS AI Assistant

A voice-first, local-first desktop assistant inspired by the LCARS interface from *Star Trek: The Next Generation*.

## Project status

This repository is the starting point for the Computer 1.0.0 implementation. The items below are goals, not claims that the features are already implemented.

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
- Document what is implemented, tested, and still experimental.

## Development

See the source tree and project documentation as implementation is added. Do not treat roadmap items as implemented features.
