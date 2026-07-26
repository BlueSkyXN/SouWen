"""Read-only administration response models."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, RootModel


class AdminConfigResponse(RootModel[dict[str, Any]]):
    """Current configuration with every credential value redacted."""


class DoctorProviderResponse(BaseModel):
    provider: str
    capabilities: list[Literal["search", "llm_search", "fetch"]]
    availability: Literal["available", "unavailable"]
    reason: Literal["available", "disabled", "missing_configuration", "not_eligible"]
    missing_fields: list[str] = Field(default_factory=list)


class DoctorResponse(BaseModel):
    total: int
    available: int
    unavailable: int
    providers: list[DoctorProviderResponse]


class AdminPingResponse(BaseModel):
    status: Literal["ok"]


__all__ = ["AdminConfigResponse", "AdminPingResponse", "DoctorResponse"]
