import json
from collections.abc import AsyncGenerator
import httpx

from app.config import Settings
from app.models import AuthContext, InternalChatRequest


def _sse(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, separators=(',', ':'))}\n\n"


async def stream_hermes(
    *,
    settings: Settings,
    auth: AuthContext,
    request_id: str,
    payload: InternalChatRequest,
) -> AsyncGenerator[str, None]:
    if not settings.hermes_url:
        yield _sse("error", {"code": "missing_hermes_url", "request_id": request_id})
        yield _sse("message_end", {"status": "error"})
        return

    token = settings.hermes_internal_token.strip()
    if not token:
        yield _sse("error", {"code": "missing_internal_token", "request_id": request_id})
        yield _sse("message_end", {"status": "error"})
        return

    url = f"{settings.hermes_url.rstrip('/')}/internal/chat/stream"
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Tenant-Id": auth.tenant_id or "",
        "X-User-Sub": auth.user_sub,
        "X-User-Email": auth.user_email or "",
        "X-Role": auth.role or "",
        "X-Request-Id": request_id,
    }

    timeout = httpx.Timeout(connect=settings.hermes_connect_timeout_s, read=settings.hermes_read_timeout_s, write=30.0, pool=5.0)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream("POST", url, headers=headers, json=payload.model_dump(mode="json")) as response:
                if response.status_code >= 400:
                    yield _sse(
                        "error",
                        {
                            "code": "upstream_error",
                            "upstream_status": response.status_code,
                            "request_id": request_id,
                        },
                    )
                    yield _sse("message_end", {"status": "error"})
                    return
                async for line in response.aiter_lines():
                    yield f"{line}\n"
    except httpx.HTTPError:
        yield _sse("error", {"code": "upstream_unreachable", "request_id": request_id})
        yield _sse("message_end", {"status": "error"})
