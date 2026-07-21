"""OpenCitations Index V2 citation-enrichment client.

OpenCitations is a directed citation-index API, not a keyword paper-search
provider.  The client exposes only its verified count, incoming-citation and
reference operations and keeps API relation data separate from article access
or redistribution claims.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any, Literal
from urllib.parse import quote, urlsplit

from souwen.core.exceptions import NotFoundError, ParseError
from souwen.core.http_client import SouWenHttpClient
from souwen.models import (
    CitationCountResponse,
    CitationEdge,
    CitationGraphResponse,
    CitationIdentifier,
)

_BASE_URL = "https://api.opencitations.net/index/v2"
_LICENSE_URL = "https://creativecommons.org/public-domain/cc0/"
_REQUEST_SCHEMES = frozenset({"doi", "pmid", "omid"})
_DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$", re.IGNORECASE)
_PMID_RE = re.compile(r"^\d+$")


class OpenCitationsClient:
    """Call the official anonymous OpenCitations Index V2 API."""

    def __init__(self) -> None:
        self._client = SouWenHttpClient(base_url=_BASE_URL, source_name="opencitations")

    async def __aenter__(self) -> OpenCitationsClient:
        await self._client.__aenter__()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        await self._client.__aexit__(exc_type, exc_val, exc_tb)

    @staticmethod
    def normalize_identifier(identifier: str | CitationIdentifier) -> CitationIdentifier:
        """Normalize a DOI URL/bare DOI or explicit DOI, PMID, OMID identifier.

        Edge responses may contain more schemes, but the public request surface
        is limited to the identifier patterns explicitly documented by the V2
        endpoint.  This avoids treating arbitrary paths as a valid provider ID.
        """
        if isinstance(identifier, CitationIdentifier):
            normalized = identifier
        elif isinstance(identifier, str):
            raw = identifier.strip()
            if not raw:
                raise ValueError("identifier 必须是非空 DOI、PMID 或 OMID")
            parsed = urlsplit(raw)
            if parsed.scheme in {"http", "https"} and parsed.netloc.lower() in {
                "doi.org",
                "dx.doi.org",
            }:
                raw = parsed.path.lstrip("/")
            if ":" in raw:
                scheme, value = raw.split(":", 1)
                normalized = CitationIdentifier(scheme=scheme, value=value)
            elif _DOI_RE.fullmatch(raw):
                normalized = CitationIdentifier(scheme="doi", value=raw)
            else:
                raise ValueError("identifier 必须是 DOI、PMID 或 OMID 的明确形式")
        else:
            raise ValueError("identifier 必须是字符串或 CitationIdentifier")

        if normalized.scheme not in _REQUEST_SCHEMES:
            raise ValueError("OpenCitations 仅支持 DOI、PMID 或 OMID identifier")
        if normalized.scheme == "doi" and not _DOI_RE.fullmatch(normalized.value):
            raise ValueError("DOI identifier 格式非法")
        if normalized.scheme == "pmid" and not _PMID_RE.fullmatch(normalized.value):
            raise ValueError("PMID identifier 必须是数字")
        if normalized.scheme == "omid" and "/" not in normalized.value:
            raise ValueError("OMID identifier 必须包含实体前缀和 '/'")
        return CitationIdentifier(
            scheme=normalized.scheme,
            value=normalized.value.lower()
            if normalized.scheme in {"doi", "pmid"}
            else normalized.value,
        )

    @staticmethod
    def _parse_edge_identifiers(raw: object) -> list[CitationIdentifier]:
        if not isinstance(raw, str):
            return []
        identifiers: list[CitationIdentifier] = []
        for item in raw.split():
            if ":" not in item:
                continue
            scheme, value = item.split(":", 1)
            try:
                identifiers.append(CitationIdentifier(scheme=scheme, value=value))
            except ValueError:
                continue
        return identifiers

    @staticmethod
    def _yes_no(value: object) -> bool | None:
        if value == "yes":
            return True
        if value == "no":
            return False
        return None

    @classmethod
    def _parse_edge(cls, payload: Mapping[str, Any]) -> CitationEdge:
        oci = payload.get("oci")
        citing = payload.get("citing")
        cited = payload.get("cited")
        if not all(isinstance(value, str) and value.strip() for value in (oci, citing, cited)):
            raise ParseError("OpenCitations citation edge 缺少 oci/citing/cited")
        return CitationEdge(
            oci=oci.strip(),
            citing=cls._parse_edge_identifiers(citing),
            cited=cls._parse_edge_identifiers(cited),
            citing_raw=citing,
            cited_raw=cited,
            creation=payload.get("creation") if isinstance(payload.get("creation"), str) else None,
            timespan=payload.get("timespan") if isinstance(payload.get("timespan"), str) else None,
            journal_self_citation=cls._yes_no(payload.get("journal_sc")),
            author_self_citation=cls._yes_no(payload.get("author_sc")),
            raw={
                key: value
                for key, value in payload.items()
                if key
                not in {"oci", "citing", "cited", "creation", "timespan", "journal_sc", "author_sc"}
            },
        )

    @staticmethod
    def _nonnegative_count(value: object) -> int:
        try:
            count = int(value)
        except (TypeError, ValueError) as exc:
            raise ParseError("OpenCitations count 不是非负整数") from exc
        if count < 0:
            raise ParseError("OpenCitations count 不能为负数")
        return count

    @staticmethod
    def _url(operation: str, identifier: CitationIdentifier) -> str:
        # Encode slash-bearing DOI/OMID values inside one upstream path segment.
        return f"/{operation}/{quote(identifier.canonical, safe=':')}"

    async def citation_count(self, identifier: str | CitationIdentifier) -> CitationCountResponse:
        normalized = self.normalize_identifier(identifier)
        path = self._url("citation-count", normalized)
        response = await self._client.get(path)
        if response.status_code == 404:
            raise NotFoundError(f"OpenCitations 未找到 identifier: {normalized.canonical}")
        payload = response.json()
        if (
            not isinstance(payload, list)
            or len(payload) != 1
            or not isinstance(payload[0], Mapping)
        ):
            raise ParseError("OpenCitations citation-count 响应格式非法")
        return CitationCountResponse(
            identifier=normalized,
            count=self._nonnegative_count(payload[0].get("count")),
            source_url=f"{_BASE_URL}{path}",
            license_url=_LICENSE_URL,
        )

    async def _graph(
        self,
        relation: Literal["citations", "references"],
        identifier: str | CitationIdentifier,
        max_edges: int = 100,
    ) -> CitationGraphResponse:
        if not 1 <= max_edges <= 1_000:
            raise ValueError("max_edges 必须在 1..1000 范围内")
        normalized = self.normalize_identifier(identifier)
        path = self._url(relation, normalized)
        response = await self._client.get(path)
        if response.status_code == 404:
            raise NotFoundError(f"OpenCitations 未找到 identifier: {normalized.canonical}")
        payload = response.json()
        if not isinstance(payload, list) or not all(isinstance(item, Mapping) for item in payload):
            raise ParseError(f"OpenCitations {relation} 响应不是 citation edge 数组")
        edges = [self._parse_edge(item) for item in payload]
        return CitationGraphResponse(
            identifier=normalized,
            relation=relation,
            total_edges=len(edges),
            returned_edges=min(len(edges), max_edges),
            truncated=len(edges) > max_edges,
            edges=edges[:max_edges],
            source_url=f"{_BASE_URL}{path}",
            license_url=_LICENSE_URL,
        )

    async def citations(
        self, identifier: str | CitationIdentifier, max_edges: int = 100
    ) -> CitationGraphResponse:
        """Return incoming citations, capped locally without claiming upstream pagination."""
        return await self._graph("citations", identifier, max_edges)

    async def references(
        self, identifier: str | CitationIdentifier, max_edges: int = 100
    ) -> CitationGraphResponse:
        """Return outgoing references, capped locally without claiming upstream pagination."""
        return await self._graph("references", identifier, max_edges)
