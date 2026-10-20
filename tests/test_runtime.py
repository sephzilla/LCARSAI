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
