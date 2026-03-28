from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AVIVI_", env_file=".env", extra="ignore")

    host: str = "0.0.0.0"
    port: int = 8000
    database_url: str = "sqlite+aiosqlite:///./avivi_master.db"
    master_secret: str = "change-me-in-production"
    admin_api_key: str = "dev-admin-key-change-me"
    ollama_base_url: str = "http://127.0.0.1:11434"
    master_telegram_bot_token: str | None = None
    master_telegram_allowed_chat_ids: str = ""
    roi_hourly_rate_ils: float = 200.0
    nightly_roi_hour_utc: int = 20

    @property
    def allowed_chat_ids(self) -> set[int]:
        if not self.master_telegram_allowed_chat_ids.strip():
            return set()
        return {int(x.strip()) for x in self.master_telegram_allowed_chat_ids.split(",") if x.strip()}


settings = Settings()
