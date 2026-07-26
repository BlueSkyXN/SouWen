"""Reviewed declarative ERIC REST JSON Provider v2 specification."""

from souwen.platform.provider_spec import RestJsonProviderSpec
from souwen.platform.provider_spec.models import (
    HttpOperation,
    SearchRequestMapping,
    SearchResponseMapping,
)

ERIC_REST_SPEC = RestJsonProviderSpec(
    provider_id="eric",
    adapter_id="eric-search",
    host="api.ies.ed.gov",
    base_path="/",
    operation=HttpOperation(method="GET", endpoint="/eric/"),
    request_mapping=SearchRequestMapping(
        query_field="query", limit_field="rows", fixed_fields={"start": 0}
    ),
    response_mapping=SearchResponseMapping(
        source_field="source",
        items_field="results",
        total_field="total_results",
        page_field="page",
        limit_field="per_page",
        item_source_field="source",
        identifier_path="raw.eric_id",
        identifier_pattern=r"[A-Z]{2}[0-9]+",
        identifier_scheme="eric",
        identifier_normalization="upper",
        title_path="title",
        snippet_path="abstract",
        year_path="year",
        authors_path="authors",
        author_name_path="name",
        resource_type_path="raw.publication_types",
        language_path="raw.language",
        open_access_path="raw.fulltext_authorized",
        record_url_path="source_url",
        record_host="eric.ed.gov",
        record_path_template="/",
        record_query_template="id={identifier}",
    ),
    configuration_keys=("enabled", "max_retries", "timeout_seconds"),
)

__all__ = ["ERIC_REST_SPEC"]
