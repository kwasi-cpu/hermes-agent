from collections.abc import AsyncGenerator
import httpx
from fastapi import HTTPException, status

from app.config import Settings
from app.models import AuthContext, InternalChatRequest


def _internal_bearer(settings: Settings) -> str:
    token = settings.hermes_internal_token.strip()
    if not token:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="missing_internal_token")
    return token


async def stream_hermes(
    *,
    settings: Settings,
    auth: AuthContext,
    request_id: str,
    payload: InternalChatRequest,
) -> AsyncGenerator[str, None]:
    if not settings.hermes_url:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="missing_hermes_url")

    url = f"{settings.hermes_url.rstrip('/')}/internal/chat/stream"
    headers = {
        "Authorization": f"Bearer {_internal_bearer(settings)}",
        "X-Tenant-Id": auth.tenant_id or "",
        "X-User-Sub": auth.user_sub,
        "X-User-Email": auth.user_email or "",
        "X-Role": auth.role or "",
        "X-Request-Id": request_id,
    }

    timeout = httpx.Timeout(connect=settings.hermes_connect_timeout_s, read=settings.hermes_read_timeout_s, write=30.0, pool=5.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        async with client.stream("POST", url, headers=headers, json=payload.model_dump(mode="json")) as response:
            if response.status_code >= 400:
                text = await response.aread()
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail={"upstream_status": response.status_code, "upstream_body": text.decode("utf-8", errors="ignore")[:500]},
                )
            async for line in response.aiter_lines():
                yield f"{line}\n"
