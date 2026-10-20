"""Local Ollama conversation orchestration."""
from __future__ import annotations

import json
import urllib.error
import urllib.request

from lcarsai.runtime import check_ollama, has_model

SYSTEM_PROMPT = (
    "You are Computer, a concise, helpful, voice-first personal assistant inspired by "
    "Star Trek: The Next Generation. Speak naturally and clearly. Your responses will be "
    "read aloud, so avoid markdown tables, excessive formatting, and long lists unless asked. "
    "Do not claim to control devices, browse the web, or remember information unless the "
    "application actually provides that capability."
)


class LocalAssistant:
    def __init__(self, model: str = "qwen3:8b") -> None:
        self.model = model
        self.history = [{"role": "system", "content": SYSTEM_PROMPT}]

    def reset(self) -> None:
        self.history = [{"role": "system", "content": SYSTEM_PROMPT}]

    def respond(self, prompt: str) -> str:
        status = check_ollama(timeout=2.0)
        if not status.available:
            raise RuntimeError(status.error or "The local Ollama runtime is unavailable.")
        if not has_model(self.model, timeout=5.0):
            raise RuntimeError(
                f"The local model {self.model} is not installed. Open LOCAL AI SETUP to download it."
            )
        messages = self.history + [{"role": "user", "content": prompt}]
        payload = json.dumps({
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": 0.65},
        }).encode("utf-8")
        request = urllib.request.Request(
            f"{status.endpoint}/api/chat", data=payload,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=300) as response:
                result = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            raise RuntimeError(f"The local model could not complete the response: {exc}") from exc
        message = result.get("message", {}) if isinstance(result, dict) else {}
        answer = message.get("content", "").strip() if isinstance(message, dict) else ""
        if not answer:
            raise RuntimeError("The local model returned an empty response.")
        self.history = messages + [{"role": "assistant", "content": answer}]
        # Keep conversational context bounded.
        if len(self.history) > 17:
            self.history = [self.history[0], *self.history[-16:]]
        return answer
