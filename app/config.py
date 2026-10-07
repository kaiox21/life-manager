from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    owner_phone: str
    webhook_secret: SecretStr

    evolution_api_url: str = "http://evolution-api:8080"
    evolution_api_key: SecretStr
    evolution_instance: str = "assistente"
    app_webhook_url: str = "http://app:8000/webhook/evolution"
    # Provisório: bot conectado ao próprio número do dono, que fala na conversa consigo mesmo.
    self_chat_mode: bool = False

    database_url: str

    tz: str = "America/Sao_Paulo"
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
