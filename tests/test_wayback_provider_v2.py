from souwen.platform.provider_spec import validate_spec_manifest
from souwen.providers.fetch_sources.wayback import (
    WAYBACK_FETCH_PROVIDER_SPEC,
    WAYBACK_PROVIDER_MANIFEST,
)


def test_wayback_manifest_spec():
    assert (
        validate_spec_manifest(WAYBACK_FETCH_PROVIDER_SPEC, WAYBACK_PROVIDER_MANIFEST)
        is WAYBACK_FETCH_PROVIDER_SPEC
    )
    assert WAYBACK_FETCH_PROVIDER_SPEC.hosts == ("archive.org", "web.archive.org")
    assert set(WAYBACK_PROVIDER_MANIFEST.network.egress_hosts) == {
        "archive.org",
        "web.archive.org",
    }
    assert WAYBACK_FETCH_PROVIDER_SPEC.transport.operations[0].endpoint == "/wayback/available"
    assert (
        WAYBACK_FETCH_PROVIDER_SPEC.additional_transports[0].operations[0].endpoint
        == "/web/:snapshot/:target"
    )
