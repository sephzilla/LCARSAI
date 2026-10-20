from lcarsai.runtime import check_ollama, ollama_endpoint


def test_default_endpoint_is_local(monkeypatch) -> None:
    monkeypatch.delenv("LCARSAI_OLLAMA_URL", raising=False)
    assert ollama_endpoint() == "http://127.0.0.1:11434"


def test_non_local_endpoint_is_rejected_without_network(monkeypatch) -> None:
    monkeypatch.setenv("LCARSAI_OLLAMA_URL", "https://example.com")
    result = check_ollama()
    assert not result.available
    assert "blocked by default" in (result.error or "")


def test_unreachable_local_service_returns_status(monkeypatch) -> None:
    monkeypatch.setenv("LCARSAI_OLLAMA_URL", "http://127.0.0.1:1")
    result = check_ollama(timeout=0.1)
    assert not result.available
    assert result.endpoint == "http://127.0.0.1:1"
    assert result.error



def test_list_models_reads_installed_names(monkeypatch) -> None:
    import json
    from lcarsai import runtime

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps({
                "models": [
                    {"name": "qwen3:8b", "model": "qwen3:8b"},
                    {"name": "llama3:latest"},
                ]
            }).encode()

    monkeypatch.setattr(
        runtime, "check_ollama",
        lambda timeout=1.5: runtime.RuntimeStatus(True, "http://127.0.0.1:11434", "0.1"),
    )
    monkeypatch.setattr(runtime.urllib.request, "urlopen", lambda *args, **kwargs: Response())
    assert runtime.list_models() == {"qwen3:8b", "llama3:latest"}


def test_has_model_accepts_exact_name(monkeypatch) -> None:
    from lcarsai import runtime

    monkeypatch.setattr(runtime, "list_models", lambda timeout=5.0: {"qwen3:8b"})
    assert runtime.has_model("qwen3:8b")


def test_has_model_accepts_implicit_latest_tag(monkeypatch) -> None:
    from lcarsai import runtime

    monkeypatch.setattr(runtime, "list_models", lambda timeout=5.0: {"llama3:latest"})
    assert runtime.has_model("llama3")
