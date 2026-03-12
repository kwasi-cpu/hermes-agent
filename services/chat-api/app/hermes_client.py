import asyncio
import json
import logging
import urllib.parse
import urllib.request
from collections.abc import AsyncGenerator

import httpx

from app.config import Settings
from app.models import AuthContext, InternalChatRequest


logger = logging.getLogger(__name__)


def _sse(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, separators=(',', ':'))}\n\n"


def _normalize_mode(mode: str) -> str:
    value = (mode or "").strip().lower()
    return value if value else "shared_token"


def _resolve_iam_audience(settings: Settings) -> str:
    audience = settings.hermes_iam_audience.strip() or settings.hermes_url.strip()
    if not audience:
        raise RuntimeError("missing_iam_audience")
    return audience


def _fetch_google_id_token(audience: str) -> str:
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.id_token import fetch_id_token

        token = fetch_id_token(Request(), audience)
        if token:
            return token
    except Exception:
        pass

    encoded_aud = urllib.parse.quote(audience, safe="")
    metadata_url = (
        "http://metadata.google.internal/computeMetadata/v1/instance/"
        f"service-accounts/default/identity?audience={encoded_aud}&format=full"
    )
    req = urllib.request.Request(metadata_url, headers={"Metadata-Flavor": "Google"})
    with urllib.request.urlopen(req, timeout=5) as resp:
        token = resp.read().decode("utf-8").strip()
    if not token:
        raise RuntimeError("iam_token_mint_failed")
    return token


async def _resolve_authorization_header(settings: Settings) -> str:
    mode = _normalize_mode(settings.hermes_service_auth_mode)
    if mode == "shared_token":
        token = settings.hermes_internal_token.strip()
        if not token:
            raise RuntimeError("missing_internal_token")
        return f"Bearer {token}"
    if mode == "iam":
        audience = _resolve_iam_audience(settings)
        try:
            token = await asyncio.to_thread(_fetch_google_id_token, audience)
        except Exception as exc:
            raise RuntimeError("iam_token_mint_failed") from exc
        if not token:
            raise RuntimeError("iam_token_mint_failed")
        return f"Bearer {token}"
    raise RuntimeError("invalid_service_auth_mode")


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

    try:
        authorization_header = await _resolve_authorization_header(settings)
    except RuntimeError as exc:
        logger.exception("internal auth header resolution failed: %s", exc)
        yield _sse("error", {"code": str(exc), "request_id": request_id})
        yield _sse("message_end", {"status": "error"})
        return

    url = f"{settings.hermes_url.rstrip('/')}/internal/chat/stream"
    headers = {
        "Authorization": authorization_header,
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
