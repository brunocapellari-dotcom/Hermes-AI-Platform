from typing import cast

from starlette.types import ASGIApp

from hermes.api import app as hermes_app
from hermes.auth import GoogleOIDCVerifier, ServiceAuthMiddleware
from hermes.authorization import build_policy_engine
from hermes.config import get_settings
from hermes.control_auth import ControlPlaneAuthorizationMiddleware

settings = get_settings()
verifier = (
    GoogleOIDCVerifier(settings.service_auth_audience)
    if settings.service_auth_required and settings.service_auth_audience
    else None
)
if settings.service_auth_required and verifier is None:
    raise RuntimeError("HERMES_SERVICE_AUTH_AUDIENCE is required when service auth is enabled")

policy = build_policy_engine(
    allow_external_actions=settings.allow_external_actions,
    opa_url=settings.opa_url,
    opa_policy_path=settings.opa_policy_path,
    openfga_url=settings.openfga_url,
    openfga_store_id=settings.openfga_store_id,
    openfga_model_id=settings.openfga_model_id,
    external_required=settings.external_authorization_required,
    timeout=settings.authorization_timeout_seconds,
)
control_plane = ControlPlaneAuthorizationMiddleware(hermes_app, policy=policy)
app = ServiceAuthMiddleware(
    cast(ASGIApp, control_plane),
    verifier=verifier,
    required=settings.service_auth_required,
)
