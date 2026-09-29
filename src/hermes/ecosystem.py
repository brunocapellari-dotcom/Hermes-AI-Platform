from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, Field


DOMAIN_READ_ENDPOINTS = (
    "/health",
    "/v1/status",
    "/v1/capabilities",
    "/v1/query",
    "/v1/search",
    "/v1/alerts",
)


class ProjectContract(BaseModel):
    key: str
    capabilities: set[str] = Field(default_factory=set)
    required_endpoints: tuple[str, ...] = DOMAIN_READ_ENDPOINTS
    execute_optional: bool = True
    idempotency_required_for_execute: bool = True


CANONICAL_PROJECTS: dict[str, ProjectContract] = {
    "AI_HOLDING": ProjectContract(
        key="AI_HOLDING",
        capabilities={"portfolio_status", "governance"},
        required_endpoints=("/health", "/api/v1/status", "/api/v1/projects", "/api/v1/alerts"),
        execute_optional=True,
    ),
    "SECOND_BRAIN": ProjectContract(
        key="SECOND_BRAIN",
        capabilities={"knowledge_query"},
        required_endpoints=("/health", "/v1/status", "/v1/capabilities", "/v1/search"),
        execute_optional=True,
    ),
    "RESEARCH_AI": ProjectContract(
        key="RESEARCH_AI",
        capabilities={"research"},
        required_endpoints=("/health", "/v1/status", "/v1/capabilities", "/v1/research"),
        execute_optional=True,
    ),
    "AGROLOG_MT": ProjectContract(
        key="AGROLOG_MT",
        capabilities={"freight_analysis", "crop_analysis", "weather_analysis", "maritime_analysis"},
    ),
    "MERCADO_FINANCEIRO": ProjectContract(
        key="MERCADO_FINANCEIRO", capabilities={"financial_analysis"}
    ),
    "SPORTS_INTELLIGENCE": ProjectContract(
        key="SPORTS_INTELLIGENCE", capabilities={"sports_analysis"}
    ),
    "GEOPOLITICAL_WATCH": ProjectContract(
        key="GEOPOLITICAL_WATCH", capabilities={"geopolitical_analysis"}
    ),
    "WORLDWAR_MODERN": ProjectContract(key="WORLDWAR_MODERN", capabilities={"simulation"}),
    "CULINARIA": ProjectContract(key="CULINARIA", capabilities={"recipe_analysis"}),
    "CONTENT_FACTORY": ProjectContract(
        key="CONTENT_FACTORY", capabilities={"content_creation"}
    ),
    "WHATSAPP_AI": ProjectContract(
        key="WHATSAPP_AI", capabilities={"message_processing"}
    ),
    "PERSONAL_PERFORMANCE": ProjectContract(
        key="PERSONAL_PERFORMANCE", capabilities={"training_plan"}
    ),
    "CATEQUESE_INFANTIL": ProjectContract(
        key="CATEQUESE_INFANTIL", capabilities={"catechesis_content"}
    ),
    "RACING_TEAM_MANAGER": ProjectContract(
        key="RACING_TEAM_MANAGER", capabilities={"racing_management_simulation"}
    ),
    "FOOTBALL_MANAGER": ProjectContract(
        key="FOOTBALL_MANAGER", capabilities={"football_management_simulation"}
    ),
}


class ContractValidation(BaseModel):
    valid: bool
    errors: list[str] = Field(default_factory=list)


class ProjectContractValidator:
    def validate_registration(
        self, contract: ProjectContract, registration: Mapping[str, Any]
    ) -> ContractValidation:
        errors: list[str] = []
        base_url = registration.get("base_url")
        if not isinstance(base_url, str) or not base_url.startswith("https://"):
            errors.append("base_url must use HTTPS")

        capabilities = registration.get("capabilities")
        if not isinstance(capabilities, list) or not all(
            isinstance(item, str) for item in capabilities
        ):
            errors.append("capabilities must be a list of strings")
        elif not contract.capabilities.issubset(set(capabilities)):
            errors.append("required canonical capabilities are missing")

        endpoints = registration.get("endpoints")
        if not isinstance(endpoints, list) or not all(isinstance(item, str) for item in endpoints):
            errors.append("endpoints must be a list of strings")
        else:
            missing = sorted(set(contract.required_endpoints) - set(endpoints))
            if missing:
                errors.append(f"required endpoints are missing: {','.join(missing)}")

        if registration.get("allow_execute"):
            if contract.execute_optional and isinstance(endpoints, list):
                if "/v1/execute" not in endpoints:
                    errors.append("authorized execute requires /v1/execute endpoint")
            if contract.idempotency_required_for_execute and not bool(
                registration.get("idempotency_supported")
            ):
                errors.append("execute requires idempotency support")

        audience = registration.get("audience")
        if audience is not None and (
            not isinstance(audience, str) or not audience.startswith("https://")
        ):
            errors.append("audience must use HTTPS")

        return ContractValidation(valid=not errors, errors=errors)

    def coverage(self, registrations: Mapping[str, Mapping[str, Any]]) -> dict[str, bool]:
        return {
            key: (
                key in registrations
                and self.validate_registration(contract, registrations[key]).valid
            )
            for key, contract in CANONICAL_PROJECTS.items()
        }
