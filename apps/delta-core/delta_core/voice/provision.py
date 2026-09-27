"""Explicit one-time setup: python -m delta_core.voice.provision."""
from faster_whisper.utils import download_model
from delta_contracts.config import Settings

if __name__ == '__main__':
    settings = Settings()
    download_model(settings.whisper_model, cache_dir=settings.whisper_cache_dir)
    print('Whisper model is available locally.')
