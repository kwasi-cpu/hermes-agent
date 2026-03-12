import asyncio

import pytest

from app.config import Settings
from app.hermes_client import _resolve_authorization_header


def test_shared_token_mode_builds_bearer_header():
    settings = Settings(
        hermes_service_auth_mode="shared_token",
        hermes_internal_token="dev-token",
        hermes_url="https://runtime.example",
    )

    header = asyncio.run(_resolve_authorization_header(settings))
    assert header == "Bearer dev-token"


def test_shared_token_mode_requires_internal_token():
    settings = Settings(
        hermes_service_auth_mode="shared_token",
        hermes_internal_token="",
        hermes_url="https://runtime.example",
    )

    with pytest.raises(RuntimeError, match="missing_internal_token"):
        asyncio.run(_resolve_authorization_header(settings))


def test_iam_mode_mints_id_token(monkeypatch):
    captured = {}

    def _fake_fetch(audience: str) -> str:
        captured["audience"] = audience
        return "iam-token"

    monkeypatch.setattr("app.hermes_client._fetch_google_id_token", _fake_fetch)
    settings = Settings(
        hermes_service_auth_mode="iam",
        hermes_iam_audience="https://runtime-aud.example",
        hermes_url="https://runtime.example",
    )

    header = asyncio.run(_resolve_authorization_header(settings))
    assert header == "Bearer iam-token"
    assert captured["audience"] == "https://runtime-aud.example"


def test_iam_mode_requires_audience():
    settings = Settings(
        hermes_service_auth_mode="iam",
        hermes_iam_audience="",
        hermes_url="",
    )

    with pytest.raises(RuntimeError, match="missing_iam_audience"):
        asyncio.run(_resolve_authorization_header(settings))
