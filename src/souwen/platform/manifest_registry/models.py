"""Strict, static Provider v2 manifest declarations.

This module validates package metadata only.  It deliberately has no provider
imports, resolver calls, or executable loading hooks.
"""

from __future__ import annotations

import re
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictStr,
    StringConstraints,
    model_validator,
)


_ID = re.compile(r"^[a-z][a-z0-9_-]{0,127}$")
_SCHEMA_ID = re.compile(r"^[a-z][a-z0-9-]{0,127}$")
_SECRET_REFERENCE = re.compile(r"^[A-Z][A-Z0-9_]{0,127}$")
_HOST = re.compile(r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)(?:\.[a-z0-9-]+)+$")
_VERSION = re.compile(r"^\d+\.\d+\.\d+(?:(?:a|b|rc)\d+|[-+][0-9A-Za-z.-]+)?$")

StableId = Annotated[StrictStr, StringConstraints(pattern=_ID.pattern)]
SchemaId = Annotated[StrictStr, StringConstraints(pattern=_SCHEMA_ID.pattern)]
SecretReference = Annotated[StrictStr, StringConstraints(pattern=_SECRET_REFERENCE.pattern)]
Host = Annotated[StrictStr, StringConstraints(pattern=_HOST.pattern)]
Version = Annotated[StrictStr, StringConstraints(pattern=_VERSION.pattern)]
CapabilityName = Literal["search", "llm_search", "fetch"]


class _StrictManifestModel(BaseModel):
    """Base model that rejects unreviewed manifest topology and metadata."""

    # JSON arrays must remain valid manifest input; scalar fields are strict by
    # annotation while `extra="forbid"` keeps declaration topology closed.
    model_config = ConfigDict(extra="forbid", frozen=True)


class AdapterDeclaration(_StrictManifestModel):
    """One exported adapter and exactly one target SPI capability."""

    id: StableId
    capability: CapabilityName
    export: Annotated[StrictStr, StringConstraints(pattern=r"^[A-Z][A-Za-z0-9_]{0,127}$")]
    availability: Literal["always", "configured"]


class ConfigurationDeclaration(_StrictManifestModel):
    """Non-secret configuration shape declared by a provider package."""

    schema_reference: SchemaId
    unknown_key_policy: Literal["reject"]
    non_secret_keys: tuple[StableId, ...] = ()

    @model_validator(mode="after")
    def _no_duplicate_or_secret_like_keys(self) -> "ConfigurationDeclaration":
        if len(set(self.non_secret_keys)) != len(self.non_secret_keys):
            raise ValueError("duplicate non-secret configuration key")
        secret_words = {"auth", "cookie", "credential", "key", "password", "secret", "token"}
        if any(secret_words.intersection(re.split(r"[-_]", key)) for key in self.non_secret_keys):
            raise ValueError("secret-like configuration key")
        return self


class SecretsDeclaration(_StrictManifestModel):
    """Reference names only; this type intentionally has no value field."""

    references: tuple[SecretReference, ...] = ()
    optional_references: tuple[SecretReference, ...] = ()

    @model_validator(mode="after")
    def _no_duplicate_references(self) -> "SecretsDeclaration":
        if (
            len(set(self.references)) != len(self.references)
            or len(set(self.optional_references)) != len(self.optional_references)
            or set(self.references).intersection(self.optional_references)
        ):
            raise ValueError("duplicate secret reference")
        return self

    @property
    def all_references(self) -> tuple[SecretReference, ...]:
        return self.references + self.optional_references


class NetworkDeclaration(_StrictManifestModel):
    """Reviewed network metadata, never a credential-bearing URL."""

    egress_hosts: tuple[Host, ...] = ()
    proxy_supported: StrictBool
    browser_required: StrictBool

    @model_validator(mode="after")
    def _no_duplicate_hosts(self) -> "NetworkDeclaration":
        if len(set(self.egress_hosts)) != len(self.egress_hosts):
            raise ValueError("duplicate egress host")
        return self


class RiskDeclaration(_StrictManifestModel):
    authenticated: StrictBool
    costed: StrictBool


class ObservabilityDeclaration(_StrictManifestModel):
    dimensions: tuple[StableId, ...]

    @model_validator(mode="after")
    def _dimensions_are_unique_and_bounded(self) -> "ObservabilityDeclaration":
        if not self.dimensions or len(set(self.dimensions)) != len(self.dimensions):
            raise ValueError("invalid observability dimensions")
        return self


class CompatibilityDeclaration(_StrictManifestModel):
    contract_versions: tuple[Literal["provider-v2"], ...]
    config_schema_versions: tuple[SchemaId, ...]

    @model_validator(mode="after")
    def _ranges_are_nonempty_and_unique(self) -> "CompatibilityDeclaration":
        if not self.contract_versions or not self.config_schema_versions:
            raise ValueError("empty compatibility declaration")
        if len(set(self.contract_versions)) != len(self.contract_versions):
            raise ValueError("duplicate contract compatibility")
        if len(set(self.config_schema_versions)) != len(self.config_schema_versions):
            raise ValueError("duplicate config schema compatibility")
        return self


class ProviderManifest(_StrictManifestModel):
    """Validated, non-executable Provider Extension v2 declaration."""

    schema_version: Literal[2]
    id: StableId
    version: Version
    contract_version: Literal["provider-v2"]
    capabilities: tuple[CapabilityName, ...] = Field(min_length=1)
    adapters: tuple[AdapterDeclaration, ...] = Field(min_length=1)
    configuration: ConfigurationDeclaration
    secrets: SecretsDeclaration
    network: NetworkDeclaration
    risk: RiskDeclaration
    observability: ObservabilityDeclaration
    compatibility: CompatibilityDeclaration

    @model_validator(mode="after")
    def _validate_topology_and_compatibility(self) -> "ProviderManifest":
        if len(set(self.capabilities)) != len(self.capabilities):
            raise ValueError("duplicate capability")
        adapter_ids = tuple(adapter.id for adapter in self.adapters)
        if len(set(adapter_ids)) != len(adapter_ids):
            raise ValueError("duplicate adapter")
        adapter_capabilities = tuple(adapter.capability for adapter in self.adapters)
        if len(set(adapter_capabilities)) != len(adapter_capabilities):
            raise ValueError("duplicate adapter capability")
        if set(adapter_capabilities) != set(self.capabilities):
            raise ValueError("capability and adapter parity mismatch")
        if self.contract_version not in self.compatibility.contract_versions:
            raise ValueError("incompatible contract version")
        if self.configuration.schema_reference not in self.compatibility.config_schema_versions:
            raise ValueError("incompatible configuration schema")
        return self
