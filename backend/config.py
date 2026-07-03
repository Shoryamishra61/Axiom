from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")
    database_url: str = "postgresql+asyncpg://scheduler:scheduler@localhost:5432/scheduler"
    secret_key: str = "change-me-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24  # 24h
    worker_lease_seconds: int = 30
    worker_poll_interval: float = 1.0
    worker_concurrency: int = 5
    reaper_interval_seconds: int = 15
    materializer_interval_seconds: int = 10
    cors_origins: str = "http://localhost,http://localhost:3000"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

settings = Settings()
