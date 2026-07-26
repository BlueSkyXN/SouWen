"""Constrained canonical Search projection for reviewed generic REST JSON specs."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlsplit

from souwen.platform.provider_spec.models import RestJsonProviderSpec, SearchResponseMapping
from souwen.platform.provider_spi import (
    PageInfo,
    Provenance,
    RequestContext,
    SearchAttributes,
    SearchIdentifier,
    SearchItem,
    SearchMeta,
    SearchPage,
)


def project_search_page(
    spec: RestJsonProviderSpec, response: Any, limit: int, context: RequestContext
) -> SearchPage:
    mapping = spec.response_mapping
    assert mapping is not None
    items = _path(response, mapping.items_field)
    total = _path(response, mapping.total_field)
    if (
        mapping.source_field is not None
        and _path(response, mapping.source_field) != spec.provider_id
    ):
        raise ValueError("invalid response source")
    if not isinstance(items, (list, tuple)) or (total is not None and not _number(total)):
        raise ValueError("invalid response page")
    if mapping.page_field is not None and _path(response, mapping.page_field) != 1:
        raise ValueError("response page mismatch")
    if mapping.limit_field is not None and _path(response, mapping.limit_field) != limit:
        raise ValueError("response page mismatch")
    if len(items) > limit or (total is not None and total < len(items)):
        raise ValueError("response page mismatch")
    return SearchPage(
        items=tuple(_item(spec, mapping, item, rank) for rank, item in enumerate(items, 1)),
        page=PageInfo(limit=limit, next_cursor=None, total=total),
        meta=SearchMeta(requested=(spec.provider_id,), succeeded=(spec.provider_id,)),
        context=context,
    )


def _item(
    spec: RestJsonProviderSpec, mapping: SearchResponseMapping, item: Any, rank: int
) -> SearchItem:
    if (
        mapping.item_source_field is not None
        and _path(item, mapping.item_source_field) != spec.provider_id
    ):
        raise ValueError("invalid item source")
    identifier = _text(_path(item, mapping.identifier_path))
    if len(identifier) > 512:
        raise ValueError("identifier is too long")
    if mapping.identifier_normalization == "upper":
        identifier = identifier.upper()
    elif mapping.identifier_normalization == "lower":
        identifier = identifier.lower()
    if re.fullmatch(mapping.identifier_pattern, identifier) is None:
        raise ValueError("invalid identifier")
    access = _path(item, mapping.open_access_path)
    if access is not None and not isinstance(access, bool):
        raise ValueError("invalid access")
    return SearchItem(
        id=f"{spec.provider_id}:{identifier}",
        title=_text(_path(item, mapping.title_path)),
        url=_url(_path(item, mapping.record_url_path), mapping, identifier),
        snippet=_optional_text(_path(item, mapping.snippet_path)),
        rank=rank,
        provenance=(Provenance(provider=spec.provider_id, attempt=1, outcome="success"),),
        attributes=SearchAttributes(
            year=_year(_path(item, mapping.year_path)),
            authors=_authors(_path(item, mapping.authors_path), mapping.author_name_path),
            identifiers=(SearchIdentifier(scheme=mapping.identifier_scheme, value=identifier),),
            resource_type=_first(_path(item, mapping.resource_type_path)),
            language=_first(_path(item, mapping.language_path)),
            open_access=access,
        ),
    )


def _path(value: Any, path: str | None) -> Any:
    if path is None:
        return None
    for part in path.split("."):
        value = value.get(part) if isinstance(value, dict) else getattr(value, part, None)
    return value


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError("invalid text")
    return value.strip()


def _text(value: Any) -> str:
    result = _optional_text(value)
    if result is None:
        raise ValueError("missing text")
    return result


def _number(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _year(value: Any) -> int | None:
    if value is None:
        return None
    if not _number(value) or value > 9999:
        raise ValueError("invalid year")
    return value


def _authors(value: Any, name_path: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)):
        raise ValueError("invalid authors")
    result = tuple(_text(_path(item, name_path)) for item in value)
    if len(result) != len(set(result)):
        raise ValueError("duplicate authors")
    return result


def _first(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return _optional_text(value)
    if not isinstance(value, (list, tuple)):
        raise ValueError("invalid text sequence")
    values = tuple(_text(item) for item in value)
    if len(values) != len(set(values)):
        raise ValueError("duplicate text")
    return values[0] if values else None


def _url(value: Any, mapping: SearchResponseMapping, identifier: str) -> str | None:
    if mapping.record_url_path is None:
        return None
    if mapping.record_host is None or mapping.record_path_template is None:
        raise ValueError("record URL mapping is incomplete")
    parsed = urlsplit(_text(value))
    path = mapping.record_path_template.format(identifier=identifier)
    query = (
        mapping.record_query_template.format(identifier=identifier)
        if mapping.record_query_template
        else ""
    )
    if (
        parsed.scheme,
        parsed.hostname,
        parsed.username,
        parsed.password,
        parsed.port,
        parsed.path,
        parsed.query,
        parsed.fragment,
    ) != ("https", mapping.record_host, None, None, None, path, query, ""):
        raise ValueError("invalid url")
    return f"https://{mapping.record_host}{path}" + (f"?{query}" if query else "")
