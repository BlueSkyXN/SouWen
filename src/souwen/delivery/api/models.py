"""Delivery-owned response DTOs not represented by a business Module."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from souwen.platform.provider_spi import CanonicalModel, Capability, Provenance, RequestContext

from .rollout import RolloutMode


class ProviderCatalogItem(CanonicalModel):
    """Safe Provider v2 availability without config or secret values."""

    provider: str = Field(min_length=1, max_length=128)
    capabilities: tuple[Capability, ...] = Field(min_length=1)
    availability: Literal["available", "unavailable"]
    provenance: tuple[Provenance, ...] = Field(min_length=1)
    reason: Literal["available", "disabled", "missing_configuration", "not_eligible"]
    missing_fields: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _status_matches_reason(self) -> ProviderCatalogItem:
        if (self.availability == "available") != (self.reason == "available"):
            raise ValueError("provider catalog status and reason do not match")
        if self.missing_fields and self.reason != "missing_configuration":
            raise ValueError("missing fields require missing_configuration")
        return self


class ProviderCatalog(CanonicalModel):
    """Migrated Provider v2 catalog without legacy source or config readback fields."""

    items: tuple[ProviderCatalogItem, ...]
    context: RequestContext


class ProbeResponse(CanonicalModel):
    """Superset payload shared by canonical probes and their 2.x aliases."""

    status: Literal["ok", "ready", "not_ready"]
    ready: bool
    version: str = Field(min_length=1, max_length=64)
    source_sha: str | None = Field(default=None, min_length=40, max_length=40)
    wrapper_sha: str | None = Field(default=None, min_length=40, max_length=40)
    worker_source_sha: str | None = Field(default=None, min_length=40, max_length=40)
    rollout_mode: RolloutMode
    config_revision: str | None = Field(default=None, min_length=1, max_length=128)
    components: dict[
        str,
        Literal["ready", "not_ready", "optional_unavailable", "disabled"],
    ] = Field(default_factory=dict)
    error: str | None = Field(default=None, min_length=1, max_length=256)
    context: RequestContext

    @model_validator(mode="after")
    def _status_matches_readiness(self) -> ProbeResponse:
        if self.status == "not_ready" and self.ready:
            raise ValueError("not_ready status cannot be ready")
        if self.status in {"ok", "ready"} and not self.ready:
            raise ValueError("successful probe status must be ready")
        if self.ready and self.error is not None:
            raise ValueError("ready probe cannot include an error")
        return self


__all__ = ["ProbeResponse", "ProviderCatalog", "ProviderCatalogItem"]
