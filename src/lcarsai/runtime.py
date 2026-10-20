"""Local inference endpoint discovery.

This module checks an already-running Ollama service; it does not download or
install any runtime. That avoids brittle assumptions about release asset names
and platform/GPU compatibility. Runtime installation will be a separate,
explicit setup step.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"


@dataclass(frozen=True)
class RuntimeStatus:
    available: bool
    endpoint: str
    version: str | None = None
    error: str | None = None


def ollama_endpoint() -> str:
    """Return the configured Ollama base URL, defaulting to localhost."""
    return os.environ.get("LCARSAI_OLLAMA_URL", DEFAULT_OLLAMA_URL).rstrip("/")


def check_ollama(timeout: float = 1.5) -> RuntimeStatus:
    """Check whether Ollama responds locally; never contacts a remote host by default."""
    endpoint = ollama_endpoint()
    if not endpoint.startswith(("http://127.0.0.1", "http://localhost", "http://[::1]")):
        return RuntimeStatus(
            available=False,
            endpoint=endpoint,
            error="Non-local Ollama endpoint blocked by default. Explicit remote access is not enabled.",
        )

    request = urllib.request.Request(f"{endpoint}/api/version", method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload: Any = json.loads(response.read().decode("utf-8"))
        version = payload.get("version") if isinstance(payload, dict) else None
        return RuntimeStatus(available=True, endpoint=endpoint, version=version)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        return RuntimeStatus(
            available=False,
            endpoint=endpoint,
            error=f"Ollama is not responding locally ({type(exc).__name__}).",
        )
