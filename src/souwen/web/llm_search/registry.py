"""Internal scheme/source registry projected into the public SourceAdapter catalog."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import replace

from souwen.registry.adapter import MethodSpec, SourceAdapter

from .base import (
    ConcreteSearchSourceSpec,
    SearchSchemeSpec,
    gateway_credential_fields,
)


class SearchSchemeRegistry:
    """Own scheme/model identity without creating a second public source catalog."""

    def __init__(self) -> None:
        self._schemes: dict[str, SearchSchemeSpec] = {}
        self._sources: dict[str, ConcreteSearchSourceSpec] = {}
        self._identities: dict[tuple[str, str], str] = {}

    def register_scheme(self, scheme: SearchSchemeSpec) -> SearchSchemeSpec:
        if scheme.scheme_id in self._schemes:
            raise ValueError(f"duplicate LLM-search scheme: {scheme.scheme_id!r}")
        self._schemes[scheme.scheme_id] = scheme
        return scheme

    def register_source(self, source: ConcreteSearchSourceSpec) -> ConcreteSearchSourceSpec:
        if source.source_id in self._sources:
            raise ValueError(f"duplicate LLM-search source ID: {source.source_id!r}")
        scheme = self._schemes.get(source.scheme_id)
        if scheme is None:
            raise ValueError(
                f"source {source.source_id!r} references unknown scheme {source.scheme_id!r}"
            )
        if not scheme.executable:
            raise ValueError(f"scheme {scheme.scheme_id!r} is not source-grade and executable")
        identity = (source.scheme_id, source.model_id)
        existing = self._identities.get(identity)
        if existing is not None:
            raise ValueError(
                f"LLM-search identity {identity!r} already belongs to source {existing!r}"
            )
        self._sources[source.source_id] = source
        self._identities[identity] = source.source_id
        return source

    def get_scheme(self, scheme_id: str) -> SearchSchemeSpec | None:
        return self._schemes.get(scheme_id)

    def get_source(self, source_id: str) -> ConcreteSearchSourceSpec | None:
        return self._sources.get(source_id)

    def source_id_for(self, scheme_id: str, model_id: str) -> str | None:
        return self._identities.get((scheme_id, model_id))

    def project_source_adapter(
        self,
        source_id: str,
        *,
        description: str,
        client_loader: Callable[[], type],
        methods: Mapping[str, MethodSpec] | None = None,
        usage_note: str | None = None,
    ) -> SourceAdapter:
        """Project one internal source identity into the canonical public registry type."""
        source = self._sources.get(source_id)
        if source is None:
            raise KeyError(f"unknown LLM-search source: {source_id!r}")
        scheme = self._schemes[source.scheme_id]
        credential_fields = gateway_credential_fields(scheme.gateway_id)
        effective_timeout = source.timeout_seconds or scheme.default_timeout_seconds
        if methods is None:
            method_specs: Mapping[str, MethodSpec] = {
                "search": MethodSpec("search", timeout_seconds=effective_timeout)
            }
        else:
            search_method = methods.get("search")
            if search_method is None:
                raise ValueError("LLM-search source projection requires a search MethodSpec")
            if search_method.timeout_seconds is not None and float(
                search_method.timeout_seconds
            ) != float(effective_timeout):
                raise ValueError(
                    "search MethodSpec timeout conflicts with the scheme/source timeout"
                )
            method_specs = dict(methods)
            method_specs["search"] = replace(
                search_method,
                timeout_seconds=effective_timeout,
            )
        return SourceAdapter(
            name=source.source_id,
            domain="web",
            integration="official_api",
            description=description,
            config_field=credential_fields[0],
            client_loader=client_loader,
            methods=method_specs,
            default_enabled=source.default_enabled,
            runtime_default_enabled=source.default_enabled,
            default_for=frozenset(),
            tags=frozenset({"llm_search"}),
            needs_config=True,
            auth_requirement="required",
            credential_fields=credential_fields,
            risk_level="medium",
            risk_reasons=frozenset({"quota_cost"}),
            stability=source.stability,
            category="web_professional",
            usage_note=usage_note,
        )


_SEARCH_SCHEMES = SearchSchemeRegistry()
