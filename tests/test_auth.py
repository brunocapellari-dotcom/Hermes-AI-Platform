import base64
import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from hermes.api import create_app
from hermes.auth import (
    GoogleIDTokenProvider,
    GoogleOIDCVerifier,
    ServiceAuthMiddleware,
    ServiceIdentity,
)
from hermes.config import Settings
from hermes.persistence import AuditRow


class FakeVerifier:
    def verify(self, token: str) -> ServiceIdentity:
        if token != "valid-token":
            raise ValueError("bad token")
        return ServiceIdentity(subject="service:caller", email="caller@example.com")


def _client(tmp_path: Path) -> tuple[TestClient, object]:
    settings = Settings(
        environment="test",
        database_url=f"sqlite:///{tmp_path / 'auth.db'}",
        auto_create_schema=True,
    )
    inner = create_app(settings)
    wrapped = ServiceAuthMiddleware(inner, verifier=FakeVerifier(), required=True)
    return TestClient(wrapped), inner


def test_service_auth_requires_token_but_keeps_health_public(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    with client as c:
        assert c.get("/health").status_code == 200
        assert c.get("/ready").status_code == 401
        assert c.post("/v1/missions", json={"request": "x"}).status_code == 401
        assert (
            c.post(
                "/v1/missions",
                headers={"Authorization": "Bearer wrong"},
                json={"request": "x"},
            ).status_code
            == 401
        )


def test_authenticated_identity_overrides_spoofed_actor(tmp_path: Path) -> None:
    client, inner = _client(tmp_path)
    with client as c:
        response = c.post(
            "/v1/missions",
            headers={"Authorization": "Bearer valid-token"},
            json={"request": "Como está a Holding?", "actor": "spoofed-owner"},
        )
        assert response.status_code == 200
    db = inner.state.container.db
    with db.sessions() as session:
        actor = session.scalar(select(AuditRow.actor).order_by(AuditRow.event_id.desc()).limit(1))
    assert actor == "service:caller"


def _fake_jwt(expiry: int) -> str:
    def enc(value: dict[str, object]) -> str:
        raw = json.dumps(value).encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

    return f"{enc({'alg': 'none'})}.{enc({'exp': expiry})}.sig"


def test_id_token_provider_caches_valid_token() -> None:
    calls: list[str] = []
    token = _fake_jwt(int(time.time()) + 3600)

    def fetch(audience: str) -> str:
        calls.append(audience)
        return token

    provider = GoogleIDTokenProvider(fetch_func=fetch)
    assert provider.token("https://project.internal") == token
    assert provider.token("https://project.internal") == token
    assert calls == ["https://project.internal"]
    assert provider.headers("https://project.internal")["Authorization"].startswith("Bearer ")
    assert provider.headers(
        "https://project.internal", header="X-Serverless-Authorization"
    )["X-Serverless-Authorization"].startswith("Bearer ")


def test_google_oidc_verifier_validates_claim_contract() -> None:
    verifier = GoogleOIDCVerifier(
        "https://hermes.internal",
        verify_func=lambda token, audience: {
            "sub": "service:caller",
            "email": "caller@example.com",
            "email_verified": True,
            "iss": "https://accounts.google.com",
            "aud": audience,
        },
    )
    identity = verifier.verify("token")
    assert identity.subject == "service:caller"
    assert identity.audience == "https://hermes.internal"

    bad = GoogleOIDCVerifier(
        "https://hermes.internal",
        verify_func=lambda token, audience: {"email": "x@example.com"},
    )
    with pytest.raises(ValueError, match="subject"):
        bad.verify("token")
