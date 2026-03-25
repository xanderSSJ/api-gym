from __future__ import annotations

from functools import lru_cache
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Gym API"
    app_env: str = "development"
    app_debug: bool = True
    api_v1_prefix: str = "/v1"

    secret_key: str = Field(..., alias="SECRET_KEY")
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 30

    database_url: str = Field(..., alias="DATABASE_URL")
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")
    allow_inmemory_rate_limit_fallback: bool = Field(
        default=True,
        alias="ALLOW_INMEMORY_RATE_LIMIT_FALLBACK",
    )

    cors_origins: str = Field(default="http://localhost:3000,http://localhost:5173", alias="CORS_ORIGINS")

    enable_email_verification: bool = Field(default=True, alias="ENABLE_EMAIL_VERIFICATION")
    max_login_attempts_per_15_min: int = Field(default=10, alias="MAX_LOGIN_ATTEMPTS_PER_15_MIN")
    max_register_attempts_per_hour: int = Field(default=10, alias="MAX_REGISTER_ATTEMPTS_PER_HOUR")
    max_plan_generations_per_min: int = Field(default=20, alias="MAX_PLAN_GENERATIONS_PER_MIN")
    free_cooldown_days: int = Field(default=15, alias="FREE_COOLDOWN_DAYS")
    enable_sql_import_endpoint: bool = Field(default=False, alias="ENABLE_SQL_IMPORT_ENDPOINT")
    admin_import_key: str = Field(default="", alias="ADMIN_IMPORT_KEY")

    storage_provider: str = "local"
    local_storage_path: str = "./storage"
    public_media_base_url: str = "http://localhost:8000/media"

    payment_provider: str = "stripe"
    payment_webhook_secret: str = ""

    celery_broker_url: str = Field(default="redis://localhost:6379/1", alias="CELERY_BROKER_URL")
    celery_result_backend: str = Field(default="redis://localhost:6379/2", alias="CELERY_RESULT_BACKEND")

    @property
    def cors_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
