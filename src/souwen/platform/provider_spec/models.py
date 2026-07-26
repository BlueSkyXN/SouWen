"""Static REST JSON Provider specifications.

Specifications describe reviewed public endpoint and configuration shape.  They
never carry a credential value, a credential-bearing URL, or arbitrary hosts.
"""

from __future__ import annotations

import re
from ipaddress import ip_address
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator, model_validator


_SECRET_WORD = re.compile(r"(?:api[_-]?key|token|secret|password|cookie|authorization)", re.I)
_HOST = re.compile(r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)(?:\.[a-z0-9-]+)+$")


class _SpecModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)


class HttpOperation(_SpecModel):
    method: Literal["GET", "POST"]
    endpoint: str = Field(pattern=r"^/[A-Za-z0-9._~!$&'()*+,;=:@/%-]*$")


class LegacyTransportDeclaration(_SpecModel):
    """Reviewed legacy transport shape without pretending it is generic JSON."""

    scheme: Literal["https"] = "https"
    host: str = Field(min_length=1, max_length=253)
    base_path: str = Field(default="/", pattern=r"^/[A-Za-z0-9._~!$&'()*+,;=:@/%-]*$")
    protocol: Literal[
        "atom_xml",
        "html",
        "json",
        "multi_step_xml",
        "multi_transport",
        "xml",
    ]
    operations: tuple[HttpOperation, ...] = Field(min_length=1)

    @field_validator("host")
    @classmethod
    def _host_is_public_name(cls, value: str) -> str:
        return _reviewed_host(value)

    @model_validator(mode="after")
    def _operations_are_unique(self) -> "LegacyTransportDeclaration":
        identities = tuple((item.method, item.endpoint) for item in self.operations)
        if len(identities) != len(set(identities)):
            raise ValueError("duplicate legacy transport operation")
        return self


CredentialPlacement = Literal["header", "query", "bearer", "oauth_body", "path"]


class CredentialBinding(_SpecModel):
    """One named secret binding used by a reviewed provider transport."""

    placement: CredentialPlacement
    reference: str = Field(pattern=r"^[A-Z][A-Z0-9_]{0,127}$")
    field_name: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_-]{0,127}$")
    required: StrictBool = True


class AuthDeclaration(_SpecModel):
    placement: Literal["none", "header", "query", "bearer", "oauth_body", "path"] = "none"
    reference: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]{0,127}$")
    field_name: str | None = Field(default=None, pattern=r"^[A-Za-z][A-Za-z0-9_-]{0,127}$")
    required: StrictBool = True
    additional_bindings: tuple[CredentialBinding, ...] = ()

    @model_validator(mode="after")
    def _shape_matches_placement(self) -> "AuthDeclaration":
        if self.placement == "none" and (
            self.reference is not None or self.field_name is not None or self.additional_bindings
        ):
            raise ValueError("anonymous auth cannot declare a reference or field")
        if self.placement == "none" and not self.required:
            raise ValueError("anonymous auth cannot be optional")
        if self.placement != "none" and (self.reference is None or self.field_name is None):
            raise ValueError("configured auth requires reference and field name")
        references = tuple(
            reference
            for reference in (
                self.reference,
                *(binding.reference for binding in self.additional_bindings),
            )
            if reference is not None
        )
        if len(references) != len(set(references)):
            raise ValueError("credential references must be unique")
        return self

    @property
    def reference_requirements(self) -> tuple[tuple[str, bool], ...]:
        """Return every declared secret reference and whether it is required."""

        primary = () if self.reference is None else ((self.reference, self.required),)
        return primary + tuple(
            (binding.reference, binding.required) for binding in self.additional_bindings
        )


class SearchRequestMapping(_SpecModel):
    query_field: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_]{0,127}$")
    limit_field: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_]{0,127}$")
    fixed_fields: dict[str, int | str | bool] = Field(default_factory=dict)

    @field_validator("fixed_fields")
    @classmethod
    def _fixed_fields_are_value_free(
        cls, values: dict[str, int | str | bool]
    ) -> dict[str, int | str | bool]:
        if any(_SECRET_WORD.search(name) for name in values):
            raise ValueError("fixed request fields cannot name credentials")
        for value in values.values():
            if isinstance(value, str):
                parsed = urlsplit(value)
                if parsed.username is not None or parsed.password is not None:
                    raise ValueError("fixed request fields cannot carry URL credentials")
        return values


class SearchResponseMapping(_SpecModel):
    source_field: str | None = Field(default=None, pattern=r"^[A-Za-z][A-Za-z0-9_.]{0,127}$")
    items_field: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_.]{0,127}$")
    total_field: str | None = Field(default=None, pattern=r"^[A-Za-z][A-Za-z0-9_.]{0,127}$")
    page_field: str | None = Field(default=None, pattern=r"^[A-Za-z][A-Za-z0-9_.]{0,127}$")
    limit_field: str | None = Field(default=None, pattern=r"^[A-Za-z][A-Za-z0-9_.]{0,127}$")
    item_source_field: str | None = None
    identifier_path: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_.]{0,127}$")
    identifier_pattern: str = Field(min_length=1, max_length=512)
    identifier_scheme: str = Field(pattern=r"^[a-z][a-z0-9_.-]{0,31}$")
    identifier_normalization: Literal["preserve", "upper", "lower"] = "preserve"
    title_path: str = "title"
    snippet_path: str | None = "abstract"
    year_path: str | None = "year"
    authors_path: str | None = "authors"
    author_name_path: str = "name"
    resource_type_path: str | None = None
    language_path: str | None = None
    open_access_path: str | None = None
    record_url_path: str | None = "source_url"
    record_host: str | None = None
    record_path_template: str | None = None
    record_query_template: str | None = None


class RestJsonProviderSpec(_SpecModel):
    """Reviewed declaration for one fixed-host REST JSON provider."""

    provider_id: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,127}$")
    adapter_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
    capability: Literal["search"] = "search"
    domain: Literal[
        "paper",
        "book",
        "research_output",
        "patent",
        "web",
        "news",
        "images",
        "videos",
    ] = "paper"
    adapter_kind: Literal["generic_rest_json", "legacy_bridge"] = "generic_rest_json"
    review_status: Literal["reviewed", "bridge_exception"] = "reviewed"
    bridge_reason: str | None = Field(default=None, min_length=1, max_length=512)
    scheme: Literal["https"] = "https"
    host: str = Field(min_length=1, max_length=253)
    base_path: str = Field(default="/", pattern=r"^/[A-Za-z0-9._~!$&'()*+,;=:@/%-]*$")
    operation: HttpOperation = Field(
        default_factory=lambda: HttpOperation(method="GET", endpoint="/")
    )
    auth: AuthDeclaration = Field(default_factory=AuthDeclaration)
    request_mapping: SearchRequestMapping = Field(
        default_factory=lambda: SearchRequestMapping(query_field="query", limit_field="limit")
    )
    response_mapping: SearchResponseMapping | None = None
    configuration_keys: tuple[str, ...] = ()

    @field_validator("host")
    @classmethod
    def _host_is_public_name(cls, value: str) -> str:
        return _reviewed_host(value)

    @field_validator("configuration_keys")
    @classmethod
    def _configuration_is_non_secret(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(values) != len(set(values)) or any(_SECRET_WORD.search(value) for value in values):
            raise ValueError("configuration keys must be unique and non-secret")
        return values

    @model_validator(mode="after")
    def _literal_secret_cannot_appear(self) -> "RestJsonProviderSpec":
        serialized = self.model_dump(mode="json", exclude_none=True)
        if any("@" in str(value) for value in serialized.values()):
            raise ValueError("credential-bearing values are forbidden in a provider spec")
        if self.adapter_kind == "generic_rest_json" and self.response_mapping is None:
            raise ValueError("generic REST JSON providers require a response mapping")
        if self.adapter_kind == "legacy_bridge" and self.review_status != "bridge_exception":
            raise ValueError("legacy bridges must be explicitly marked as exceptions")
        if self.adapter_kind == "legacy_bridge" and self.bridge_reason is None:
            raise ValueError("legacy bridges require a bounded exception reason")
        if self.adapter_kind == "generic_rest_json" and self.bridge_reason is not None:
            raise ValueError("generic REST JSON providers cannot carry a bridge reason")
        return self

    @property
    def auth_reference(self) -> str | None:
        return self.auth.reference

    @property
    def auth_reference_requirements(self) -> tuple[tuple[str, bool], ...]:
        return self.auth.reference_requirements

    @property
    def base_url(self) -> str:
        return f"{self.scheme}://{self.host}{self.base_path.rstrip('/')}"


class _LegacyProviderSpec(_SpecModel):
    """Static declaration for a reviewed bridge around a non-generic client."""

    provider_id: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,127}$")
    adapter_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
    adapter_kind: Literal["legacy_bridge"] = "legacy_bridge"
    review_status: Literal["bridge_exception"] = "bridge_exception"
    bridge_reason: str = Field(min_length=1, max_length=512)
    transport: LegacyTransportDeclaration
    auth: AuthDeclaration = Field(default_factory=AuthDeclaration)
    configuration_keys: tuple[str, ...] = ()

    @field_validator("configuration_keys")
    @classmethod
    def _configuration_is_non_secret(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(values) != len(set(values)) or any(_SECRET_WORD.search(value) for value in values):
            raise ValueError("configuration keys must be unique and non-secret")
        return values

    @model_validator(mode="after")
    def _literal_secret_cannot_appear(self) -> "_LegacyProviderSpec":
        serialized = self.model_dump(mode="json", exclude_none=True)
        if "@" in str(serialized):
            raise ValueError("credential-bearing values are forbidden in a provider spec")
        return self

    @property
    def auth_reference(self) -> str | None:
        return self.auth.reference

    @property
    def auth_reference_requirements(self) -> tuple[tuple[str, bool], ...]:
        return self.auth.reference_requirements

    @property
    def host(self) -> str:
        return self.transport.host

    @property
    def base_url(self) -> str:
        return (
            f"{self.transport.scheme}://{self.transport.host}{self.transport.base_path.rstrip('/')}"
        )


class LegacySearchProviderSpec(_LegacyProviderSpec):
    """Reviewed Search bridge declaration for XML, HTML, or complex JSON clients."""

    capability: Literal["search"] = "search"
    domain: Literal[
        "paper",
        "book",
        "research_output",
        "patent",
        "web",
        "news",
        "images",
        "videos",
    ] = "paper"


class LegacyFetchProviderSpec(_LegacyProviderSpec):
    """Reviewed Fetch bridge declaration with a bounded canonical target contract."""

    capability: Literal["fetch"] = "fetch"
    target_contract: Literal["arxiv_publication_url", "public_url"]


ProviderSpec = RestJsonProviderSpec | LegacySearchProviderSpec | LegacyFetchProviderSpec


def _reviewed_host(value: str) -> str:
    normalized = value.strip().lower().rstrip(".")
    try:
        ip_address(normalized)
    except ValueError:
        is_ip = False
    else:
        is_ip = True
    if is_ip or not _HOST.fullmatch(normalized) or "@" in normalized:
        raise ValueError("host must be a reviewed DNS name")
    return normalized
