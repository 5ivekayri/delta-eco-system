from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    delta_token: str = Field(min_length=16)
    database_url: str
    service_name: str = "delta-core"
    tasks_url: str = "http://127.0.0.1:8001"
    service_configs: list[dict] | None = None
    heartbeat_timeout: int = Field(default=30, ge=5)
    command_timeout: int = Field(default=15, ge=1)
    llm_provider: str = "mock"
    openrouter_api_key: str = ""
    openrouter_model: str = ""
    delta_router_model: str = ""
    delta_assistant_model: str = ""
    delta_router_max_tokens: int = Field(default=512, ge=128, le=4096)
    delta_local_intent_threshold: float = Field(default=.9, gt=0, le=1)
    stt_provider: str = "whisper"
    whisper_model: str = "small"
    whisper_cache_dir: str = ".runtime/whisper"
    whisper_language: str | None = "ru"
    voice_max_bytes: int = Field(default=10 * 1024 * 1024, ge=1024, le=25 * 1024 * 1024)
    voice_max_seconds: int = Field(default=60, ge=1, le=120)
    mock_stt_transcript: str = "покажи устройства"
    tts_provider: str = "piper"
    piper_model: str = ".runtime/piper/ru_RU-irina-medium.onnx"
    tts_max_chars: int = Field(default=1500, ge=100, le=5000)
    tts_max_seconds: int = Field(default=60, ge=1, le=120)
    tts_timeout_seconds: float = Field(default=10, ge=.1, le=60)
