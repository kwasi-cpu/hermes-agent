from fastapi import Depends, Header, HTTPException, status

from app.config import Settings, get_settings
from app.models import InternalAuthContext


def _extract_bearer(authorization: str | None) -> str:
    if not authorization:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing_authorization")
    prefix = "Bearer "
    if not authorization.startswith(prefix):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_authorization")
    return authorization[len(prefix) :].strip()


async def require_internal_auth(
    authorization: str | None = Header(default=None),
    x_tenant_id: str | None = Header(default=None),
    x_user_sub: str | None = Header(default=None),
    x_user_email: str | None = Header(default=None),
    x_role: str | None = Header(default=None),
    x_request_id: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> InternalAuthContext:
    token = _extract_bearer(authorization)
    expected = settings.internal_auth_token.strip()
    if not expected or token != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_internal_token")

    if not x_user_sub:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="missing_identity_headers")

    return InternalAuthContext(
        tenant_id=(x_tenant_id.strip() if x_tenant_id and x_tenant_id.strip() else None),
        user_sub=x_user_sub,
        user_email=x_user_email.lower().strip() if x_user_email else None,
        role=x_role,
        request_id=x_request_id or "",
    )
