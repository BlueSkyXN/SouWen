"""Reviewed bridge declaration for the DBLP search client."""

from souwen.platform.provider_spec import LegacySearchProviderSpec, LegacyTransportDeclaration
from souwen.platform.provider_spec.models import HttpOperation

DBLP_PROVIDER_SPEC = LegacySearchProviderSpec(
    provider_id="dblp",
    adapter_id="dblp-search",
    review_status="bridge_exception",
    bridge_reason="legacy records do not guarantee one reviewed stable generic identifier",
    transport=LegacyTransportDeclaration(
        scheme="https",
        host="dblp.org",
        base_path="/search",
        protocol="json",
        operations=(HttpOperation(method="GET", endpoint="/publ/api"),),
    ),
    configuration_keys=("enabled",),
)
