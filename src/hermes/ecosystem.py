from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, Field


class ProjectContract(BaseModel):
    key: str
    capabilities: set[str] = Field(default_factory=set)
    required_endpoints: tuple[str, ...] = ("/health", "/v1/capabilities", "/v1/query")
    execute_optional: bool = True
    idempotency_required_for_execute: bool = True


CANONICAL_PROJECTS: dict[str, ProjectContract] = {
    "AI_HOLDING": ProjectContract(key="AI_HOLDING", capabilities={"portfolio_status", "governance"}),
    "SECOND_BRAIN": ProjectContract(key="SECOND_BRAIN", capabilities={"knowledge_query"}),
    "RESEARCH_AI": ProjectContract(key="RESEARCH_AI", capabilities={"research"}),
    "AGROLOG_MT": ProjectContract(key="AGROLOG_MT", capabilities={"freight_analysis"}),
    "MERCADO_FINANCEIRO": ProjectContract(key="MERCADO_FINANCEIRO", capabilities={"financial_analysis"}),
    "SPORTS_INTELLIGENCE": ProjectContract(key="SPORTS_INTELLIGENCE", capabilities={"sports_analysis"}),
    "GEOPOLITICAL_WATCH": ProjectContract(key="GEOPOLITICAL_WATCH", capabilities={"geopolitical_analysis"}),
    "WORLDWAR_MODERN": ProjectContract(key="WORLDWAR_MODERN", capabilities={"simulation"}),
    "CULINARIA": ProjectContract(key="CULINARIA", capabilities={"recipe_analysis"}),
    "CONTENT_FACTORY": ProjectContract(key="CONTENT_FACTORY", capabilities={"content_creation"}),
    "WHATSAPP_AI": ProjectContract(key="WHATSAPP_AI", capabilities={"message_processing"}),
    "PERSONAL_PERFORMANCE": ProjectContract(key="PERSONAL_PERFORMANCE", capabilities={"training_plan"}),
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
        if not isinstance(base_url, str) or not base_url.startswith(("http://", "https://")):
            errors.append("base_url must be HTTP(S)")
        capabilities = registration.get("capabilities")
        if not isinstance(capabilities, list) or not all(isinstance(item, str) for item in capabilities):
            errors.append("capabilities must be a list of strings")
        elif not contract.capabilities.issubset(set(capabilities)):
            errors.append("required canonical capabilities are missing")
        if registration.get("allow_execute") and contract.idempotency_required_for_execute:
            if not bool(registration.get("idempotency_supported")):
                errors.append("execute requires idempotency support")
        return ContractValidation(valid=not errors, errors=errors)

    def coverage(self, registrations: Mapping[str, Mapping[str, Any]]) -> dict[str, bool]:
        return {
            key: (
                key in registrations
                and self.validate_registration(contract, registrations[key]).valid
            )
            for key, contract in CANONICAL_PROJECTS.items()
        }
