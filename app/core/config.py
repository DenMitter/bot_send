from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)

    bot_token: str
    api_id: int
    api_hash: str
    mysql_dsn: str

    admin_ids: str = ""
    default_locale: str = "uk"
    media_dir: str = "storage"

    mailing_batch_size: int = 30
    mailing_delay_seconds: float = 1.2

    web_auth_host: str = "127.0.0.1"
    web_auth_port: int = 8080
    web_auth_base_url: str = "http://127.0.0.1:8080"

    def admin_id_set(self) -> set[int]:
        if not self.admin_ids:
            return set()
        return {int(x.strip()) for x in self.admin_ids.split(",") if x.strip()}


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
