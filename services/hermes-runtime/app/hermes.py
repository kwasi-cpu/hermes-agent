import asyncio
import json
import logging
from collections.abc import AsyncGenerator

from openai import OpenAI
from google import genai
from google.genai.types import GenerateContentConfig

from app.config import Settings, get_settings
from app.guardrails import parse_toolsets, resolve_agent_max_iterations, resolve_enabled_toolsets, validate_agent_guardrails

from app.models import InternalAuthContext, InternalChatStreamRequest


logger = logging.getLogger(__name__)

try:
    from run_agent import AIAgent as RuntimeAIAgent
    _AIAGENT_IMPORT_ERROR: Exception | None = None
except Exception as exc:
    RuntimeAIAgent = None
    _AIAGENT_IMPORT_ERROR = exc


def _sse(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, separators=(',', ':'))}\n\n"


def _build_client(settings: Settings) -> OpenAI:
    if settings.openai_api_key:
        return OpenAI(api_key=settings.openai_api_key, base_url=settings.openai_base_url or None)
    if settings.openrouter_api_key:
        base_url = settings.openai_base_url or "https://openrouter.ai/api/v1"
        return OpenAI(api_key=settings.openrouter_api_key, base_url=base_url)
    raise RuntimeError("missing_model_credentials")


def _generate_response_agent(
    *,
    settings: Settings,
    auth: InternalAuthContext,
    req: InternalChatStreamRequest,
) -> str:
    if RuntimeAIAgent is None:
        raise RuntimeError("agent_runtime_unavailable") from _AIAGENT_IMPORT_ERROR

    api_key = (
        settings.agent_api_key.strip()
        or settings.openrouter_api_key.strip()
        or settings.openai_api_key.strip()
        or None
    )
    base_url = settings.agent_base_url.strip() or settings.openai_base_url.strip() or None
    provider = settings.agent_provider.strip() or None
    enabled_toolsets = resolve_enabled_toolsets(settings)
    validate_agent_guardrails(settings=settings, req=req, enabled_toolsets=enabled_toolsets)

    agent = RuntimeAIAgent(
        model=settings.agent_model,
        api_key=api_key,
        base_url=base_url,
        provider=provider,
        max_iterations=resolve_agent_max_iterations(settings),
        enabled_toolsets=enabled_toolsets,
        disabled_toolsets=parse_toolsets(settings.agent_disabled_toolsets),
        quiet_mode=True,
        platform="api",
        session_id=f"{auth.user_sub}:{req.conversation_id}",
        skip_context_files=settings.agent_skip_context_files,
        skip_memory=settings.agent_skip_memory,
    )
    return (agent.chat(req.message) or "").strip()


def _generate_response_vertex(*, settings: Settings, user_message: str) -> str:
    if not settings.gcp_project_id:
        raise RuntimeError("missing_gcp_project_id")
    client = genai.Client(vertexai=True, project=settings.gcp_project_id, location=settings.vertex_location)
    resp = client.models.generate_content(
        model=settings.model_name,
        contents=user_message,
        config=GenerateContentConfig(
            system_instruction=settings.system_prompt,
            temperature=settings.temperature,
            max_output_tokens=settings.max_output_tokens,
        ),
    )
    return (resp.text or "").strip()


def _generate_response(*, settings: Settings, user_message: str) -> str:
    if settings.openai_api_key or settings.openrouter_api_key:
        client = _build_client(settings)
        resp = client.chat.completions.create(
            model=settings.model_name,
            messages=[
                {"role": "system", "content": settings.system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=settings.temperature,
            max_tokens=settings.max_output_tokens,
        )
        content = resp.choices[0].message.content
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    parts.append(item.get("text", ""))
            return "".join(parts).strip()
        return ""

    return _generate_response_vertex(settings=settings, user_message=user_message)


def _chunk_text(text: str, size: int = 220) -> list[str]:
    if not text:
        return []
    return [text[i : i + size] for i in range(0, len(text), size)]


async def stream_chat(*, auth: InternalAuthContext, req: InternalChatStreamRequest) -> AsyncGenerator[str, None]:
    settings = get_settings()
    yield _sse("message_start", {"conversation_id": str(req.conversation_id), "request_id": auth.request_id})

    try:
        mode = (settings.runtime_mode or "agent").strip().lower()
        if mode == "agent":
            try:
                text = await asyncio.to_thread(_generate_response_agent, settings=settings, auth=auth, req=req)
            except Exception:
                if settings.agent_fallback_to_completion:
                    logger.warning("agent mode failed; falling back to completion mode")
                    text = await asyncio.to_thread(_generate_response, settings=settings, user_message=req.message)
                else:
                    raise
        elif mode == "completion":
            text = await asyncio.to_thread(_generate_response, settings=settings, user_message=req.message)
        else:
            raise RuntimeError("invalid_runtime_mode")

        if not text:
            yield _sse("error", {"code": "empty_model_response", "request_id": auth.request_id})
            yield _sse("message_end", {"status": "error"})
            return

        for chunk in _chunk_text(text):
            yield _sse("delta", {"text": chunk})

        yield _sse("message_end", {"status": "ok"})
    except Exception as exc:
        error_code = str(exc) if isinstance(exc, RuntimeError) else "runtime_error"
        logger.exception("runtime generation failed: %s", exc.__class__.__name__)
        yield _sse("error", {"code": error_code, "request_id": auth.request_id})
        yield _sse("message_end", {"status": "error"})
