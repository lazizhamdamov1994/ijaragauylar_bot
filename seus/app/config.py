"""Sozlamalar: hammasi .env faylidan o'qiladi. Token va parol SecretStr — logga chiqmaydi."""
from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    bot_token: SecretStr = SecretStr("")
    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "seus"
    db_user: str = "seus"
    db_password: SecretStr = SecretStr("")
    # To'liq URL berilsa (masalan serverda), yuqoridagi DB_* o'rniga shu ishlatiladi
    database_url: SecretStr | None = None
    log_level: str = "INFO"

    @property
    def db_url(self) -> str:
        if self.database_url and self.database_url.get_secret_value():
            return self.database_url.get_secret_value()
        return URL.create(
            "postgresql+asyncpg",
            username=self.db_user,
            password=self.db_password.get_secret_value(),
            host=self.db_host,
            port=self.db_port,
            database=self.db_name,
        ).render_as_string(hide_password=False)


@lru_cache
def get_settings() -> Settings:
    return Settings()
