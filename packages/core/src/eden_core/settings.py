"""Settings every backend service shares, read from the environment.

Each service subclasses `CoreSettings` with its own fields. In production compose
sets every value; locally they also come from the repo-root `.env`. A real
environment variable always wins over the file.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class CoreSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: str = "development"
    public_base_url: str = "http://localhost:3000"

    # Local Supabase's default. Production uses the Supavisor session pooler string.
    supabase_db_url: str = "postgresql://postgres:postgres@127.0.0.1:54322/postgres"
    db_pool_max: int = 5

    # Monthly caps. Scrapes are Bright Data page fetches; Jev is OpenRouter's reported cost.
    jev_monthly_budget_usd: float = 5.0
    scrape_monthly_max: int = 5000

    @property
    def is_production(self) -> bool:
        return self.environment == "production"
