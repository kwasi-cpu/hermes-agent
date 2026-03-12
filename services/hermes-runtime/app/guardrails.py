from app.config import Settings
from app.models import InternalChatStreamRequest


def parse_toolsets(value: str) -> list[str] | None:
    items = [v.strip() for v in (value or "").split(",") if v.strip()]
    return items or None


def resolve_enabled_toolsets(settings: Settings) -> list[str]:
    parsed = parse_toolsets(settings.agent_enabled_toolsets)
    return parsed or ["safe"]


def has_explicit_confirmation(*, message: str, phrase: str) -> bool:
    normalized_phrase = (phrase or "").strip()
    if not normalized_phrase:
        return False
    return normalized_phrase in (message or "")


def validate_agent_guardrails(*, settings: Settings, req: InternalChatStreamRequest, enabled_toolsets: list[str]) -> None:
    unsafe_toolsets_enabled = set(enabled_toolsets) != {"safe"}
    if not unsafe_toolsets_enabled:
        return

    if settings.agent_enforce_safe_toolset_only:
        if not settings.agent_require_confirmation_for_unsafe_toolsets:
            raise RuntimeError("unsafe_toolsets_disabled")
        if not has_explicit_confirmation(message=req.message, phrase=settings.agent_unsafe_tool_confirmation_phrase):
            raise RuntimeError("unsafe_toolset_confirmation_required")


def resolve_agent_max_iterations(settings: Settings) -> int:
    requested = max(1, int(settings.agent_max_iterations))
    cap = max(1, int(settings.agent_max_iterations_cap))
    return min(requested, cap)
