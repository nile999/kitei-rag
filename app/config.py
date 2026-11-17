from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """環境変数と .env から読む設定。変数名は大文字でも小文字でもよい。"""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "kitei-rag"
    environment: str = "local"


settings = Settings()
