from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    env: str = "dev"
    auth0_domain: str = ""
    auth0_audience: str = ""
    auth0_issuer: str = ""
    auth0_tenant_claim: str = ""
    auth0_role_claim: str = "https://hellosunday.app/role"

    hermes_url: str = ""
    hermes_internal_token: str = ""
    hermes_connect_timeout_s: float = 10.0
    hermes_read_timeout_s: float = 120.0

    database_url: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
