from typing import Optional
from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file='.env',
        env_file_encoding='utf-8',
        case_sensitive=False,
        extra='ignore',
    )

    app_name: str = 'Real-Time-Translation-AI-Agent'
    environment: str = Field(default='development', alias='ENVIRONMENT')
    host: str = Field(default='0.0.0.0', alias='HOST')
    port: int = Field(default=3000, alias='PORT')
    public_base_url: Optional[str] = Field(default=None, alias='PUBLIC_BASE_URL')

    signalwire_space: Optional[str] = Field(default=None, alias='SIGNALWIRE_SPACE')
    signalwire_project: Optional[str] = Field(default=None, alias='SIGNALWIRE_PROJECT')
    signalwire_token: Optional[str] = Field(default=None, alias='SIGNALWIRE_TOKEN')
    signalwire_context: str = Field(default='live-translation', alias='SIGNALWIRE_CONTEXT')

    swml_basic_auth_user: str = Field(default='signalwire', alias='SWML_BASIC_AUTH_USER')
    swml_basic_auth_password: str = Field(default='dev-password-change-me', alias='SWML_BASIC_AUTH_PASSWORD')

    openai_api_key: Optional[str] = Field(default=None, alias='OPENAI_API_KEY')
    anthropic_api_key: Optional[str] = Field(default=None, alias='ANTHROPIC_API_KEY')
    llm_model: str = Field(default='gpt-4o-mini', alias='LLM_MODEL')

    default_source_language: str = Field(default='en-US', alias='DEFAULT_SOURCE_LANGUAGE')
    default_target_language: str = Field(default='es-ES', alias='DEFAULT_TARGET_LANGUAGE')
    default_source_label: str = Field(default='English', alias='DEFAULT_SOURCE_LABEL')
    default_target_label: str = Field(default='Spanish', alias='DEFAULT_TARGET_LABEL')
    default_voice: str = Field(default='alloy', alias='DEFAULT_VOICE')

    use_local_webhook: bool = Field(default=True, alias='USE_LOCAL_WEBHOOK')
    local_webhook_path: str = Field(default='/internal/translation-webhook', alias='LOCAL_WEBHOOK_PATH')
    translation_webhook_url: Optional[str] = Field(default=None, alias='TRANSLATION_WEBHOOK_URL')
    translation_webhook_auth_header: Optional[str] = Field(default=None, alias='TRANSLATION_WEBHOOK_AUTH_HEADER')

    debug: bool = Field(default=True, alias='DEBUG')
    log_level: str = Field(default='INFO', alias='LOG_LEVEL')
    log_format: str = Field(default='pretty', alias='LOG_FORMAT')


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
