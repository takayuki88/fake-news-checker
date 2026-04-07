from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    fetch_timeout_seconds: float = 12.0
    max_fetch_chars: int = 7000
    min_text_chars: int = 10
    min_auto_extract_chars: int = 80
    app_timezone: str = "Asia/Tokyo"
    app_host: str = "127.0.0.1"
    app_port: int = 8000
    robots_user_agent: str = "WebPageTrustChecker"
    request_user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/136.0.0.0 Safari/537.36"
    )

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
