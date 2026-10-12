import pytest
from pydantic import ValidationError

from hermes.network_policy import is_secure_service_url
from hermes.project_registry import ProjectHealth, ProjectRegistration


@pytest.mark.parametrize(
    "url",
    [
        "https://service.example.com",
        "https://service.example.com/api",
        "http://localhost:8080",
        "http://127.0.0.1:9000",
        "http://[::1]:7000",
    ],
)
def test_secure_service_url_allows_https_and_loopback(url: str) -> None:
    assert is_secure_service_url(url) is True


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com",
        "http://192.168.1.10:8080",
        "http://10.0.0.5",
        "https://192.168.1.10:8443",
        "https://10.0.0.5",
        "https://169.254.169.254/latest/meta-data",
        "https://[fe80::1]/metadata",
        "https://metadata.google.internal/computeMetadata/v1/",
        "ftp://localhost/resource",
        "https://user:password@example.com",
        "https://example.com/path#fragment",
        "not-a-url",
    ],
)
def test_secure_service_url_rejects_non_loopback_plaintext_and_embedded_credentials(
    url: str,
) -> None:
    assert is_secure_service_url(url) is False


def test_project_registration_accepts_zero_cost_loopback_endpoint() -> None:
    registration = ProjectRegistration(
        key="AGROLOG_MT",
        base_url="http://127.0.0.1:8010",
        capabilities=["freight_analysis"],
        endpoints=[
            "/health",
            "/v1/status",
            "/v1/capabilities",
            "/v1/query",
            "/v1/search",
            "/v1/alerts",
        ],
        health=ProjectHealth.ACTIVE,
    )
    assert registration.base_url == "http://127.0.0.1:8010"


def test_project_registration_rejects_plaintext_lan_endpoint() -> None:
    with pytest.raises(ValidationError, match="HTTPS or HTTP loopback"):
        ProjectRegistration(
            key="AGROLOG_MT",
            base_url="http://192.168.1.10:8010",
        )


def test_project_registration_rejects_https_metadata_endpoint() -> None:
    with pytest.raises(ValidationError, match="HTTPS or HTTP loopback"):
        ProjectRegistration(
            key="AGROLOG_MT",
            base_url="https://169.254.169.254/latest",
        )


def test_project_registration_accepts_https_public_endpoint() -> None:
    registration = ProjectRegistration(
        key="AGROLOG_MT",
        base_url="https://agrolog.example.com",
    )
    assert registration.base_url == "https://agrolog.example.com"
