from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    env: str = "dev"
    internal_auth_mode: str = "shared_token"
    internal_auth_token: str = ""
    internal_auth_iam_audience: str = ""
    internal_auth_allowed_service_accounts: str = ""
    model_name: str = "gemini-2.5-flash"
    runtime_mode: str = "agent"

    agent_model: str = "google/gemini-2.5-flash"
    agent_base_url: str = "https://openrouter.ai/api/v1"
    agent_api_key: str = ""
    agent_provider: str = "openrouter"
    agent_enabled_toolsets: str = "safe"
    agent_disabled_toolsets: str = ""
    agent_enable_gws_readonly_dev: bool = False
    agent_max_iterations: int = 20
    agent_max_iterations_cap: int = 20
    agent_enforce_safe_toolset_only: bool = True
    agent_require_confirmation_for_unsafe_toolsets: bool = True
    agent_unsafe_tool_confirmation_phrase: str = "CONFIRM_UNSAFE_TOOLS"
    agent_skip_context_files: bool = True
    agent_skip_memory: bool = True
    agent_fallback_to_completion: bool = True

    openai_api_key: str = ""
    openai_base_url: str = ""
    openrouter_api_key: str = ""
    system_prompt: str = "You are Hermes, a helpful clinical assistant. Be concise and safe."
    temperature: float = 0.2
    max_output_tokens: int = 800
    gcp_project_id: str = ""
    vertex_location: str = "us-central1"


@lru_cache
def get_settings() -> Settings:
    return Settings()
