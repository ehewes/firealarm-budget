"""Settings, read from the environment (and `apps/api/.env` locally). Names match env.example."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

_DEV_SALT = "dev-salt-not-for-production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: str = "development"

    # Supabase. The service role key bypasses RLS; it never leaves this service.
    supabase_url: str = "http://127.0.0.1:54321"
    supabase_service_role_key: str = ""
    # Only for projects still signing tokens with the legacy HS256 secret. Projects on
    # asymmetric signing keys (the default now, locally too) are verified via JWKS.
    supabase_jwt_secret: str | None = None
    # Only when tokens name a different issuer than SUPABASE_URL (e.g. Docker networking).
    supabase_jwt_issuer: str | None = None

    # Bright Data Web Unlocker.
    brightdata_api_key: str | None = None
    brightdata_unlocker_zone: str | None = None

    # Jev (typesafe/jev-1.13) through OpenRouter. JEV_API_KEY is accepted as the same key.
    openrouter_api_key: str | None = None
    jev_api_key: str | None = None

    # Grok API (xAI): turning plain-language rules into a rules object. Optional.
    grok_api_key: str | None = None
    grok_model: str = "grok-4-fast-non-reasoning"
    # Where "Continue to Grok" sends the shopper; the prompt goes in `?q=`.
    grok_bot_url: str = "https://grok.com/"

    # Stores allowed to be scraped (comma-separated; subdomains included; * allows all stores).
    allowed_domains: str = "*"
    # The web app's public origin; also the public API base unless PUBLIC_API_URL is set.
    web_origin: str = "http://localhost:3000"
    public_api_url: str | None = None

    session_ttl_hours: int = 24
    scrape_concurrency: int = 8
    # A scrape of the same URL newer than this is shared instead of fetched again.
    scrape_fresh_minutes: int = 30
    # page_cache entries newer than this are reused; older ones are pruned.
    page_cache_minutes: int = 360
    # Product pages fetched per scrape to enrich the listing (0 disables).
    max_product_pages: int = 10

    # Monthly caps, tracked in usage_counters.
    scrape_monthly_max: int = 5000
    jev_monthly_budget_usd: float = 5.0

    # Rate limits on POST /v1/sessions.
    ip_hash_salt: str = _DEV_SALT
    sessions_per_hour_per_ip: int = 20
    sessions_per_hour_per_user: int = 30

    # Offline development: serve pages from saved HTML instead of Bright Data.
    fixtures_dir: str | None = None
    # Local development without a Bright Data key: fetch pages from this machine.
    direct_fetch: bool = False

    @property
    def jev_key(self) -> str | None:
        return self.openrouter_api_key or self.jev_api_key

    @property
    def api_base(self) -> str:
        return (self.public_api_url or f"{self.web_origin.rstrip('/')}/v1").rstrip("/")

    @property
    def domains(self) -> frozenset[str]:
        return frozenset(d.strip().lower() for d in self.allowed_domains.split(",") if d.strip())

    def production_problems(self) -> list[str]:
        """Settings that would make production unsafe. The API refuses to start on any of them."""
        if self.environment != "production":
            return []
        problems = []
        if self.ip_hash_salt == _DEV_SALT:
            problems.append("IP_HASH_SALT is the development default")
        if not self.supabase_service_role_key:
            problems.append("SUPABASE_SERVICE_ROLE_KEY is not set")
        if self.fixtures_dir:
            problems.append("FIXTURES_DIR is set, so nothing would really be scraped")
        if self.direct_fetch:
            problems.append("DIRECT_FETCH is set; production fetches only through Bright Data")
        if not self.web_origin.startswith("https://"):
            problems.append("WEB_ORIGIN is not https")
        return problems


@lru_cache
def get_settings() -> Settings:
    return Settings()
