from uuid import UUID

import pytest

from app.config import Settings
from app.guardrails import resolve_agent_max_iterations, resolve_enabled_toolsets, validate_agent_guardrails
from app.models import InternalChatStreamRequest


def _request(message: str) -> InternalChatStreamRequest:
    return InternalChatStreamRequest(
        conversation_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        message=message,
    )


def test_enabled_toolsets_default_to_safe_when_empty():
    settings = Settings(agent_enabled_toolsets="")
    assert resolve_enabled_toolsets(settings) == ["safe"]


def test_enabled_toolsets_can_include_dev_gws_toggle():
    settings = Settings(env="dev", agent_enabled_toolsets="safe", agent_enable_gws_readonly_dev=True)
    assert resolve_enabled_toolsets(settings) == ["safe", "gws_readonly"]


def test_enabled_toolsets_reject_dev_gws_toggle_in_prod():
    settings = Settings(env="prod", agent_enabled_toolsets="safe", agent_enable_gws_readonly_dev=True)
    with pytest.raises(RuntimeError, match="gws_readonly_dev_only"):
        resolve_enabled_toolsets(settings)


def test_guardrails_allow_safe_toolset_without_confirmation():
    settings = Settings(agent_enabled_toolsets="safe")
    validate_agent_guardrails(settings=settings, req=_request("hello"), enabled_toolsets=["safe"])


def test_guardrails_allow_safe_plus_gws_without_confirmation():
    settings = Settings(agent_enabled_toolsets="safe,gws_readonly")
    validate_agent_guardrails(settings=settings, req=_request("hello"), enabled_toolsets=["safe", "gws_readonly"])


def test_guardrails_require_confirmation_for_unsafe_toolsets():
    settings = Settings(
        agent_enabled_toolsets="safe,debugging",
        agent_enforce_safe_toolset_only=True,
        agent_require_confirmation_for_unsafe_toolsets=True,
        agent_unsafe_tool_confirmation_phrase="CONFIRM_UNSAFE_TOOLS",
    )

    with pytest.raises(RuntimeError, match="unsafe_toolset_confirmation_required"):
        validate_agent_guardrails(settings=settings, req=_request("run terminal"), enabled_toolsets=["safe", "debugging"])


def test_guardrails_allow_unsafe_toolsets_with_explicit_confirmation():
    settings = Settings(
        agent_enabled_toolsets="safe,debugging",
        agent_enforce_safe_toolset_only=True,
        agent_require_confirmation_for_unsafe_toolsets=True,
        agent_unsafe_tool_confirmation_phrase="CONFIRM_UNSAFE_TOOLS",
    )
    req = _request("Please proceed. CONFIRM_UNSAFE_TOOLS")
    validate_agent_guardrails(settings=settings, req=req, enabled_toolsets=["safe", "debugging"])


def test_agent_max_iterations_respects_cap():
    settings = Settings(agent_max_iterations=50, agent_max_iterations_cap=20)
    assert resolve_agent_max_iterations(settings) == 20
