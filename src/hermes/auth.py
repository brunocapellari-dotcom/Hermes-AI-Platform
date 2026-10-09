from __future__ import annotations

import asyncio
import base64
import json
import os
import threading
import time
from collections.abc import Awaitable, Callable, Mapping
from contextvars import ContextVar, Token
from typing import Any, Protocol

from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2 import id_token
from pydantic import BaseModel


class ServiceIdentity(BaseModel):
    subject: str
    email: str | None = None
    issuer: str | None = None
    audience: str | None = None


class IdentityVerifier(Protocol):
    def verify(self, token: str) -> ServiceIdentity: ...


class IdentityTokenProvider(Protocol):
    def token(self, audience: str) -> str: ...


_current_identity: ContextVar[ServiceIdentity | None] = ContextVar(
    "hermes_service_identity", default=None
)


def current_identity() -> ServiceIdentity | None:
    return _current_identity.get()


def authenticated_actor(default: str | None = None) -> str | None:
    identity = current_identity()
    return identity.subject if identity is not None else default


def _set_identity(identity: ServiceIdentity) -> Token[ServiceIdentity | None]:
    return _current_identity.set(identity)


def _reset_identity(token: Token[ServiceIdentity | None]) -> None:
    _current_identity.reset(token)


def outbound_service_auth_enabled() -> bool:
    return os.getenv("HERMES_SERVICE_TO_SERVICE_AUTH", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


class GoogleOIDCVerifier:
    def __init__(
        self,
        audience: str,
        *,
        verify_func: Callable[[str, str], Mapping[str, Any]] | None = None,
    ) -> None:
        if not audience:
            raise ValueError("OIDC audience is required")
        self.audience = audience
        self._verify_func = verify_func or self._verify_google

    @staticmethod
    def _verify_google(token: str, audience: str) -> Mapping[str, Any]:
        claims = id_token.verify_oauth2_token(token, GoogleRequest(), audience=audience)
        return claims

    def verify(self, token: str) -> ServiceIdentity:
        claims = self._verify_func(token, self.audience)
        subject = claims.get("sub")
        if not isinstance(subject, str) or not subject:
            raise ValueError("OIDC token is missing a subject")
        email = claims.get("email")
        if email is not None and not isinstance(email, str):
            raise ValueError("OIDC email claim is invalid")
        if email is not None and claims.get("email_verified") is False:
            raise ValueError("OIDC email claim is not verified")
        issuer = claims.get("iss")
        audience = claims.get("aud")
        return ServiceIdentity(
            subject=subject,
            email=email,
            issuer=issuer if isinstance(issuer, str) else None,
            audience=audience if isinstance(audience, str) else self.audience,
        )


class GoogleIDTokenProvider:
    """Fetch and cache short-lived Google-signed ID tokens without service-account keys."""

    def __init__(self, *, fetch_func: Callable[[str], str] | None = None) -> None:
        self._fetch_func = fetch_func or self._fetch_google
        self._cache: dict[str, tuple[str, float]] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _fetch_google(audience: str) -> str:
        return id_token.fetch_id_token(GoogleRequest(), audience)

    @staticmethod
    def _expiry(token: str) -> float:
        try:
            payload = token.split(".")[1]
            payload += "=" * (-len(payload) % 4)
            claims = json.loads(base64.urlsafe_b64decode(payload).decode("utf-8"))
            expiry = claims.get("exp")
            return float(expiry) if isinstance(expiry, (int, float)) else time.time() + 60
        except (IndexError, ValueError, TypeError, json.JSONDecodeError):
            return time.time() + 60

    def token(self, audience: str) -> str:
        if not audience:
            raise ValueError("token audience is required")
        now = time.time()
        with self._lock:
            cached = self._cache.get(audience)
            if cached is not None and cached[1] - now > 60:
                return cached[0]
            token = self._fetch_func(audience)
            self._cache[audience] = (token, self._expiry(token))
            return token

    def headers(self, audience: str, *, header: str = "Authorization") -> dict[str, str]:
        return {header: f"Bearer {self.token(audience)}"}


_default_token_provider = GoogleIDTokenProvider()


def service_identity_headers(
    audience: str, *, header: str = "Authorization"
) -> dict[str, str]:
    if not audience.startswith("https://"):
        raise ValueError("service-to-service identity tokens require an HTTPS audience")
    return _default_token_provider.headers(audience, header=header)


def serverless_identity_headers(audience: str) -> dict[str, str]:
    """Cloud Run IAM header that leaves Authorization available for app-layer auth."""
    return service_identity_headers(audience, header="X-Serverless-Authorization")


class ServiceAuthMiddleware:
    """ASGI boundary that authenticates service identity before Hermes handles a request."""

    def __init__(
        self,
        app: Callable[[dict[str, Any], Callable[[], Awaitable[dict[str, Any]]], Callable[[dict[str, Any]], Awaitable[None]]], Awaitable[None]],
        *,
        verifier: IdentityVerifier | None,
        required: bool,
        public_paths: frozenset[str] = frozenset({"/health"}),
    ) -> None:
        if required and verifier is None:
            raise ValueError("identity verifier is required when service authentication is enabled")
        self.app = app
        self.verifier = verifier
        self.required = required
        self.public_paths = public_paths

    @staticmethod
    async def _unauthorized(send: Callable[[dict[str, Any]], Awaitable[None]]) -> None:
        body = b'{"detail":"unauthorized"}'
        await send(
            {
                "type": "http.response.start",
                "status": 401,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode("ascii")),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Callable[[], Awaitable[dict[str, Any]]],
        send: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        if scope.get("type") != "http" or not self.required or scope.get("path") in self.public_paths:
            await self.app(scope, receive, send)
            return
        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        raw = headers.get(b"authorization", b"").decode("utf-8", errors="ignore")
        if not raw.startswith("Bearer ") or self.verifier is None:
            await self._unauthorized(send)
            return
        token = raw.removeprefix("Bearer ").strip()
        if not token:
            await self._unauthorized(send)
            return
        try:
            identity = await asyncio.to_thread(self.verifier.verify, token)
        except Exception:  # verification details must not leak to callers
            await self._unauthorized(send)
            return
        context_token = _set_identity(identity)
        try:
            await self.app(scope, receive, send)
        finally:
            _reset_identity(context_token)
