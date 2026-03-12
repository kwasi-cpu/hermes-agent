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


def _normalize_mode(mode: str) -> str:
    value = (mode or "").strip().lower()
    return value if value else "shared_token"


def _split_csv(value: str) -> set[str]:
    return {item.strip().lower() for item in (value or "").split(",") if item.strip()}


def _verify_oauth2_id_token(token: str, audience: str) -> dict:
    from google.auth.transport.requests import Request
    from google.oauth2.id_token import verify_oauth2_token

    return verify_oauth2_token(token, Request(), audience)


def _validate_internal_token(token: str, settings: Settings) -> None:
    mode = _normalize_mode(settings.internal_auth_mode)

    if mode == "shared_token":
        expected = settings.internal_auth_token.strip()
        if not expected or token != expected:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_internal_token")
        return

    if mode == "iam":
        audience = settings.internal_auth_iam_audience.strip()
        if not audience:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="missing_internal_auth_iam_audience")

        try:
            claims = _verify_oauth2_id_token(token, audience)
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_internal_iam_token") from exc

        allowed_service_accounts = _split_csv(settings.internal_auth_allowed_service_accounts)
        if not allowed_service_accounts:
            return

        caller = str(claims.get("email") or "").lower().strip()
        if caller not in allowed_service_accounts:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_invoker_identity")
        return

    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="invalid_internal_auth_mode")


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
    _validate_internal_token(token, settings)

    if not x_user_sub:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="missing_identity_headers")

    return InternalAuthContext(
        tenant_id=(x_tenant_id.strip() if x_tenant_id and x_tenant_id.strip() else None),
        user_sub=x_user_sub,
        user_email=x_user_email.lower().strip() if x_user_email else None,
        role=x_role,
        request_id=x_request_id or "",
    )
