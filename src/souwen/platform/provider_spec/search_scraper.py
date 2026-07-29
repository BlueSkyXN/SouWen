"""Strict Provider v2 projection for existing scraper search clients."""

from __future__ import annotations

from collections.abc import Sequence
from hashlib import sha256
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from souwen.platform.provider_spi import (
    PageInfo,
    Provenance,
    RequestContext,
    SearchAttributes,
    SearchIdentifier,
    SearchItem,
    SearchMeta,
    SearchPage,
    SearchRequest,
)

from .factory import ClientSearchProvider, ClientSearchSpec
from .models import (
    AuthDeclaration,
    HttpOperation,
    ClientSearchProviderSpec,
    ClientTransportDeclaration,
)
from souwen.platform.manifest_registry import ProviderManifest


def canonical_public_url(value: Any) -> str:
    """Return a public http(s) URL suitable for a canonical Search item."""

    if not isinstance(value, str) or not value.strip():
        raise ValueError("missing record URL")
    parsed = urlsplit(value.strip())
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise ValueError("invalid record URL")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("invalid record URL") from exc
    host = parsed.hostname.lower()
    netloc = host if port is None else f"{host}:{port}"
    return urlunsplit((parsed.scheme.lower(), netloc, parsed.path or "/", parsed.query, ""))


class ScraperSearchProvider(ClientSearchProvider):
    """Search bridge for first-page existing scraper responses.

    The existing client still owns request sequencing, anti-bot handling and HTML or
    JSON parsing; this class only admits well-formed public result metadata.
    """

    def __init__(self, client: Any, *, provider_id: str, domain: str, enabled: bool = True) -> None:
        self.provider_id = provider_id
        super().__init__(client, _spec(provider_id, domain), enabled=enabled)


async def _invoke(client: Any, request: SearchRequest, limit: int) -> Any:
    return await client.search(request.query, max_results=limit)


def _spec(provider_id: str, domain: str) -> ClientSearchSpec:
    return ClientSearchSpec(provider_id, domain, _invoke, _project(provider_id))


def _project(provider_id: str):
    def project(response: Any, limit: int, context: RequestContext) -> SearchPage:
        results = getattr(response, "results", None)
        total = getattr(response, "total_results", None)
        if (
            getattr(response, "source", None) != provider_id
            or getattr(response, "page", None) not in (None, 1)
            or not isinstance(results, Sequence)
            or isinstance(results, (str, bytes))
            or not isinstance(total, int)
            or isinstance(total, bool)
            or total < len(results)
            or len(results) > limit
        ):
            raise ValueError("invalid existing scraper search response")
        return SearchPage(
            items=tuple(_item(provider_id, value, rank) for rank, value in enumerate(results, 1)),
            page=PageInfo(limit=limit, total=total),
            meta=SearchMeta(requested=(provider_id,), succeeded=(provider_id,)),
            context=context,
        )

    return project


def _item(provider_id: str, value: Any, rank: int) -> SearchItem:
    if (
        getattr(value, "source", None) != provider_id
        or not isinstance(getattr(value, "title", None), str)
        or not value.title.strip()
    ):
        raise ValueError("invalid existing scraper search item")
    url = canonical_public_url(getattr(value, "url", None))
    key = sha256(url.encode("utf-8")).hexdigest()
    snippet = getattr(value, "snippet", None)
    if snippet is not None and not isinstance(snippet, str):
        raise ValueError("invalid existing scraper snippet")
    return SearchItem(
        id=f"{provider_id}:{key}",
        title=value.title.strip(),
        url=url,
        snippet=snippet.strip() or None if isinstance(snippet, str) else None,
        rank=rank,
        provenance=(Provenance(provider=provider_id, attempt=1, outcome="success"),),
        attributes=SearchAttributes(identifiers=(SearchIdentifier(scheme=provider_id, value=key),)),
    )


__all__ = ["ScraperSearchProvider", "canonical_public_url"]


def client_scraper_spec(
    provider_id: str,
    domain: str,
    host: str,
    protocol: str,
    operations: tuple[HttpOperation, ...],
    *,
    auth: AuthDeclaration | None = None,
    additional_transports: tuple[ClientTransportDeclaration, ...] = (),
) -> ClientSearchProviderSpec:
    return ClientSearchProviderSpec(
        provider_id=provider_id,
        adapter_id=f"{provider_id}-search",
        domain=domain,  # type: ignore[arg-type]
        adapter_reason="existing scraper parsing and anti-bot transport remain behind a strict Search bridge",
        transport=ClientTransportDeclaration(host=host, protocol=protocol, operations=operations),  # type: ignore[arg-type]
        additional_transports=additional_transports,
        auth=auth or AuthDeclaration(),
        configuration_keys=("enabled",),
    )


def scraper_search_manifest(
    provider_id: str,
    export: str,
    hosts: list[str],
    *,
    proxy_supported: bool = True,
    optional_secrets: list[str] | None = None,
) -> ProviderManifest:
    schema = f"{provider_id.replace('_', '-')}-scraper-provider-config-v1"
    return ProviderManifest.model_validate(
        {
            "schema_version": 2,
            "id": provider_id,
            "version": "2.0.0rc4",
            "contract_version": "provider-v2",
            "capabilities": ["search"],
            "adapters": [
                {
                    "id": f"{provider_id}-search",
                    "capability": "search",
                    "export": export,
                    "availability": "configured",
                }
            ],
            "configuration": {
                "schema_reference": schema,
                "unknown_key_policy": "reject",
                "non_secret_keys": ["enabled"],
            },
            "secrets": {"references": [], "optional_references": optional_secrets or []},
            "network": {
                "egress_hosts": hosts,
                "proxy_supported": proxy_supported,
                "browser_required": False,
            },
            "risk": {"authenticated": False, "costed": False},
            "observability": {"dimensions": ["provider", "adapter", "capability", "outcome"]},
            "compatibility": {
                "contract_versions": ["provider-v2"],
                "config_schema_versions": [schema],
            },
        }
    )


__all__ += ["client_scraper_spec", "scraper_search_manifest"]
