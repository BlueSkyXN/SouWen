"""Reviewed bridge declaration for the Apify Fetch client."""

from souwen.platform.provider_spec import LegacyFetchProviderSpec, LegacyTransportDeclaration
from souwen.platform.provider_spec.models import AuthDeclaration, HttpOperation

APIFY_FETCH_PROFILE = LegacyFetchProviderSpec(
    provider_id="apify",
    adapter_id="apify-fetch",
    bridge_reason="Apify actor input and receipt parsing remain in the legacy Fetch bridge",
    transport=LegacyTransportDeclaration(
        host="api.apify.com",
        protocol="json",
        operations=(
            HttpOperation(
                method="POST",
                endpoint="/v2/acts/apify~website-content-crawler/run-sync-get-dataset-items",
            ),
        ),
    ),
    auth=AuthDeclaration(placement="query", reference="APIFY_API_TOKEN", field_name="token"),
    configuration_keys=("enabled",),
    target_contract="public_url",
)

__all__ = ["APIFY_FETCH_PROFILE"]
