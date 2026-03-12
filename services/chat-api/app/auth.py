import time
from typing import Any, Dict

import httpx
from fastapi import Depends, Header, HTTPException, status
from jose import JWTError, jwt

from app.config import Settings, get_settings
from app.models import AuthContext


_JWKS_CACHE: Dict[str, Any] = {"expires_at": 0.0, "keys": []}


async def _fetch_jwks(settings: Settings) -> list[dict[str, Any]]:
    now = time.time()
    if _JWKS_CACHE["keys"] and now < _JWKS_CACHE["expires_at"]:
        return _JWKS_CACHE["keys"]

    if not settings.auth0_domain:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="auth0_not_configured")

    jwks_url = f"https://{settings.auth0_domain}/.well-known/jwks.json"
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get(jwks_url)
        resp.raise_for_status()
        keys = resp.json().get("keys", [])

    _JWKS_CACHE["keys"] = keys
    _JWKS_CACHE["expires_at"] = now + 300
    return keys


def _extract_bearer(authorization: str | None) -> str:
    if not authorization:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing_authorization")
    prefix = "Bearer "
    if not authorization.startswith(prefix):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_authorization")
    return authorization[len(prefix) :].strip()


async def require_auth(
    authorization: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> AuthContext:
    token = _extract_bearer(authorization)
    keys = await _fetch_jwks(settings)

    try:
        unverified = jwt.get_unverified_header(token)
    except JWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_jwt_header") from exc

    kid = unverified.get("kid")
    key = next((k for k in keys if k.get("kid") == kid), None)
    if not key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="unknown_kid")

    issuer = settings.auth0_issuer or f"https://{settings.auth0_domain}/"
    try:
        claims = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            audience=settings.auth0_audience,
            issuer=issuer,
        )
    except JWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_token") from exc

    sub = claims.get("sub")
    tenant_id = claims.get(settings.auth0_tenant_claim) if settings.auth0_tenant_claim else None
    role = claims.get(settings.auth0_role_claim)
    email = claims.get("email")

    if not sub:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing_sub")

    return AuthContext(
        tenant_id=(str(tenant_id) if tenant_id else None),
        user_sub=str(sub),
        user_email=(str(email).lower().strip() if isinstance(email, str) else None),
        role=(str(role) if role else None),
    )
