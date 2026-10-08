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

    # Vercel AI Gateway (API compatível com OpenAI). Nomes de modelo só via .env.
    ai_gateway_api_key: SecretStr = SecretStr("")
    ai_gateway_base_url: str = "https://ai-gateway.vercel.sh/v1"
    model_classifier: str = ""
    model_primary: str = ""
    model_escalation: str = ""
    allowed_providers: str = ""  # separados por vírgula; vazio = sem filtro
    reasoning_effort: str = ""  # vazio = padrão do modelo

    tz: str = "America/Sao_Paulo"
    log_level: str = "INFO"


def provider_list(raw: str) -> list[str]:
    return [p.strip() for p in raw.split(",") if p.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
