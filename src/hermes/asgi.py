from hermes.api import app as hermes_app
from hermes.auth import GoogleOIDCVerifier, ServiceAuthMiddleware
from hermes.config import get_settings

settings = get_settings()
verifier = (
    GoogleOIDCVerifier(settings.service_auth_audience)
    if settings.service_auth_required and settings.service_auth_audience
    else None
)
if settings.service_auth_required and verifier is None:
    raise RuntimeError("HERMES_SERVICE_AUTH_AUDIENCE is required when service auth is enabled")

app = ServiceAuthMiddleware(
    hermes_app,
    verifier=verifier,
    required=settings.service_auth_required,
)
