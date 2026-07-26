"""Reviewed generic REST JSON declaration for HuggingFace Papers."""

from souwen.platform.provider_spec import RestJsonProviderSpec
from souwen.platform.provider_spec.models import (
    HttpOperation,
    SearchRequestMapping,
    SearchResponseMapping,
)

HUGGINGFACE_REST_SPEC = RestJsonProviderSpec(
    provider_id="huggingface",
    adapter_id="huggingface-search",
    host="huggingface.co",
    operation=HttpOperation(method="GET", endpoint="/api/papers/search"),
    request_mapping=SearchRequestMapping(query_field="query", limit_field="top_n"),
    response_mapping=SearchResponseMapping(
        source_field="source",
        items_field="results",
        total_field="total_results",
        page_field="page",
        limit_field="per_page",
        item_source_field="source",
        identifier_path="raw.arxiv_id",
        identifier_pattern=r"[A-Za-z0-9._-]+",
        identifier_scheme="arxiv",
        title_path="title",
        snippet_path="abstract",
        year_path="year",
        authors_path="authors",
        author_name_path="name",
        record_url_path="source_url",
        record_host="huggingface.co",
        record_path_template="/papers/{identifier}",
    ),
    configuration_keys=("enabled",),
)
