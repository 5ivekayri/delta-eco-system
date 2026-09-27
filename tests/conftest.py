import pytest


@pytest.fixture(autouse=True)
def offline_providers(monkeypatch):
    """Never use a developer's live LLM credentials in isolated backend tests."""
    monkeypatch.setenv('LLM_PROVIDER', 'mock')
    monkeypatch.setenv('STT_PROVIDER', 'mock')
    monkeypatch.setenv('TTS_PROVIDER', 'disabled')
