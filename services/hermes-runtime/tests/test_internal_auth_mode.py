import pytest
from fastapi import HTTPException

from app.auth import _validate_internal_token
from app.config import Settings


def test_shared_token_mode_accepts_matching_token():
    settings = Settings(internal_auth_mode="shared_token", internal_auth_token="secret-token")
    _validate_internal_token("secret-token", settings)


def test_shared_token_mode_rejects_invalid_token():
    settings = Settings(internal_auth_mode="shared_token", internal_auth_token="secret-token")

    with pytest.raises(HTTPException, match="invalid_internal_token"):
        _validate_internal_token("wrong-token", settings)


def test_iam_mode_requires_audience():
    settings = Settings(internal_auth_mode="iam", internal_auth_iam_audience="")

    with pytest.raises(HTTPException, match="missing_internal_auth_iam_audience"):
        _validate_internal_token("any", settings)


def test_iam_mode_validates_allowed_service_account(monkeypatch):
    monkeypatch.setattr("app.auth._verify_oauth2_id_token", lambda *_: {"email": "chat-api-sa@sunday-475619.iam.gserviceaccount.com"})
    settings = Settings(
        internal_auth_mode="iam",
        internal_auth_iam_audience="https://hermes-runtime.example",
        internal_auth_allowed_service_accounts="chat-api-sa@sunday-475619.iam.gserviceaccount.com",
    )

    _validate_internal_token("token", settings)


def test_iam_mode_rejects_unapproved_service_account(monkeypatch):
    monkeypatch.setattr("app.auth._verify_oauth2_id_token", lambda *_: {"email": "other-sa@sunday-475619.iam.gserviceaccount.com"})
    settings = Settings(
        internal_auth_mode="iam",
        internal_auth_iam_audience="https://hermes-runtime.example",
        internal_auth_allowed_service_accounts="chat-api-sa@sunday-475619.iam.gserviceaccount.com",
    )

    with pytest.raises(HTTPException, match="invalid_invoker_identity"):
        _validate_internal_token("token", settings)
