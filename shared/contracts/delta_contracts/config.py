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
    stt_provider: str = "whisper"
    whisper_model: str = "small"
    tts_provider: str = "piper"
    piper_model: str = ""
