"""API settings. Every field maps to an upper-case environment variable."""

from functools import lru_cache

from eden_core.settings import CoreSettings

_DEV_SALT = "dev-salt-not-for-production"


class ApiSettings(CoreSettings):
    # Supabase Auth: tokens are verified against the project's JWKS.
    supabase_url: str | None = None
    # Only needed when the issuer differs from SUPABASE_URL, which happens in the
    # local Docker stack: the API reaches Supabase via host.docker.internal while
    # the browser's tokens say 127.0.0.1.
    supabase_jwt_issuer: str | None = None

    ip_hash_salt: str = _DEV_SALT

    # Abuse limits, counted from the sessions table itself.
    guest_sessions_per_hour: int = 10
    guest_sessions_per_day: int = 30
    user_sessions_per_hour: int = 60
    # A refresh within this window returns the same session instead of a new one.
    session_reuse_minutes: int = 10
    # A scrape of the same URL newer than this is shared instead of fetched again.
    scrape_fresh_minutes: int = 30

    # Comma-separated sites the gates accept (e.g. "joinfleek.com"). Empty means any.
    gate_allowed_sites: str = ""
    # Resolve the target's DNS before accepting it. Off only for offline development.
    gate_resolve_dns: bool = True

    @property
    def allowed_sites(self) -> frozenset[str]:
        return frozenset(s.strip().lower() for s in self.gate_allowed_sites.split(",") if s.strip())

    def production_problems(self) -> list[str]:
        """Settings that would make production silently unsafe. Boot refuses to start on any."""
        if not self.is_production:
            return []
        problems = []
        if self.ip_hash_salt == _DEV_SALT:
            problems.append("IP_HASH_SALT is the development default")
        if not self.supabase_url:
            problems.append("SUPABASE_URL is not set, so sign-in tokens cannot be verified")
        if self.public_base_url.startswith("http://"):
            problems.append("PUBLIC_BASE_URL is not https")
        if not self.gate_resolve_dns:
            problems.append("GATE_RESOLVE_DNS is off")
        return problems


@lru_cache
def get_settings() -> ApiSettings:
    return ApiSettings()
