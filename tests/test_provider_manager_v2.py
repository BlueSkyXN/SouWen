"""Deterministic lifecycle conformance for the Provider v2 manager."""

from __future__ import annotations

import asyncio
import copy
import json
from pathlib import Path

import pytest

from souwen.platform.provider_manager.manager import ProviderManager, ProviderManagerError
from souwen.platform.provider_spi import (
    ContentMetadata,
    ExecutionContext,
    FetchResult,
    FetchTargetRequest,
    PageInfo,
    ProviderError,
    ProviderErrorCode,
    ProviderProbe,
    Provenance,
    RequestContext,
    SearchItem,
    SearchMeta,
    SearchPage,
    SearchRequest,
)


_FIXTURE = Path(__file__).parent / "contracts" / "fixtures" / "target_provider_manifest_v2.json"


def _manifest(
    *,
    package_id: str = "fixture-provider-package",
    adapter_id: str = "fixture-search",
    export: str = "FixtureSearchProvider",
):
    declaration = copy.deepcopy(json.loads(_FIXTURE.read_text(encoding="utf-8"))["manifest"])
    declaration["id"] = package_id
    declaration["adapters"][0]["id"] = adapter_id
    declaration["adapters"][0]["export"] = export
    return declaration


class FixtureSearchProvider:
    capability = "search"

    def __init__(self, configuration, secrets) -> None:
        self.configuration = configuration
        self.secrets = secrets
        self.close_count = 0

    async def search(self, request, context, execution):
        return _page(context, request.query)

    async def probe(self, execution):
        return ProviderProbe(provider="fixture-provider", capability="search", status="available")

    async def close(self):
        self.close_count += 1


def _manager() -> ProviderManager:
    return ProviderManager(
        config_resolver=lambda _manifest: {"enabled": True},
        secret_resolver=lambda _manifest, _references: {"FIXTURE_PROVIDER_API_KEY": "test-only"},
    )


def _execution() -> ExecutionContext:
    return ExecutionContext.with_timeout(5)


def _request(query: str = "query") -> SearchRequest:
    return SearchRequest(query=query, domains=("paper",))


def _request_context() -> RequestContext:
    return RequestContext(request_id="provider-manager-test")


def _page(context: RequestContext, title: str = "query") -> SearchPage:
    return SearchPage(
        items=(
            SearchItem(
                id=f"fixture:{title}",
                title=title,
                rank=1,
                provenance=(Provenance(provider="fixture-search", outcome="success"),),
            ),
        ),
        page=PageInfo(limit=1),
        meta=SearchMeta(
            requested=("fixture-search",),
            succeeded=("fixture-search",),
        ),
        context=context,
    )


@pytest.mark.asyncio
async def test_discovery_preflights_factory_without_constructing_until_execution() -> None:
    manager = _manager()
    constructed = 0

    def factory(configuration, secrets):
        nonlocal constructed
        constructed += 1
        return FixtureSearchProvider(configuration, secrets)

    manager.register_factory(
        package_id="fixture-provider-package",
        export="FixtureSearchProvider",
        factory=factory,
        provider_type=FixtureSearchProvider,
    )

    result = manager.discover([_manifest()])

    assert result[0].accepted is True
    assert manager.eligible_adapter_ids == ("fixture-search",)
    assert constructed == 0
    page = await manager.execute("fixture-search", _request(), _request_context(), _execution())
    assert page.items[0].title == "query"
    assert constructed == 1
    assert await manager.probe("fixture-search", _execution()) == ProviderProbe(
        provider="fixture-provider", capability="search", status="available"
    )


@pytest.mark.asyncio
async def test_config_or_secret_failure_is_provider_local_and_safe() -> None:
    manager = ProviderManager(
        config_resolver=lambda manifest: (
            {"enabled": True}
            if manifest.id == "healthy-provider-package"
            else {"unexpected": "literal-secret-value"}
        ),
        secret_resolver=lambda _manifest, _references: {"FIXTURE_PROVIDER_API_KEY": "test-only"},
    )
    for package_id, adapter_id, export in (
        ("fixture-provider-package", "fixture-search", "FixtureSearchProvider"),
        ("healthy-provider-package", "healthy-search", "FixtureSearchProvider"),
    ):
        manager.register_factory(
            package_id=package_id,
            export=export,
            factory=FixtureSearchProvider,
            provider_type=FixtureSearchProvider,
        )

    manager.discover(
        [
            _manifest(),
            _manifest(package_id="healthy-provider-package", adapter_id="healthy-search"),
        ]
    )

    assert manager.eligible_adapter_ids == ("healthy-search",)
    with pytest.raises(ProviderManagerError, match="adapter_not_eligible"):
        await manager.execute("fixture-search", _request(), _request_context(), _execution())
    page = await manager.execute("healthy-search", _request(), _request_context(), _execution())
    assert page.items[0].title == "query"
    assert all("literal-secret-value" not in repr(item) for item in manager.diagnostics)
    assert manager.diagnostics[0].reason_code == "config_invalid"


@pytest.mark.parametrize(
    "resolved",
    ({}, {"FIXTURE_PROVIDER_API_KEY": ""}, {"FIXTURE_PROVIDER_API_KEY": "   "}),
)
def test_declared_secret_references_must_resolve_to_nonempty_strings(resolved) -> None:
    manager = ProviderManager(
        config_resolver=lambda _manifest: {"enabled": True},
        secret_resolver=lambda _manifest, _references: resolved,
    )
    manager.register_factory(
        package_id="fixture-provider-package",
        export="FixtureSearchProvider",
        factory=FixtureSearchProvider,
        provider_type=FixtureSearchProvider,
    )

    manager.discover([_manifest()])

    assert manager.eligible_adapter_ids == ()
    assert manager.diagnostics[-1].reason_code == "secret_unavailable"


@pytest.mark.asyncio
async def test_optional_secret_reference_does_not_block_and_is_forwarded_only_when_present() -> (
    None
):
    declaration = _manifest()
    declaration["secrets"] = {
        "references": [],
        "optional_references": ["FIXTURE_PROVIDER_API_KEY"],
    }
    captured: list[dict[str, str]] = []

    def factory(configuration, secrets):
        captured.append(dict(secrets))
        return FixtureSearchProvider(configuration, secrets)

    for resolved in ({}, {"FIXTURE_PROVIDER_API_KEY": "test-only"}):
        manager = ProviderManager(
            config_resolver=lambda _manifest: {"enabled": True},
            secret_resolver=lambda _manifest, _references, resolved=resolved: resolved,
        )
        manager.register_factory(
            package_id="fixture-provider-package",
            export="FixtureSearchProvider",
            factory=factory,
            provider_type=FixtureSearchProvider,
        )
        manager.discover([declaration])
        assert manager.eligible_adapter_ids == ("fixture-search",)
        await manager.execute("fixture-search", _request(), _request_context(), _execution())

    assert captured == [{}, {"FIXTURE_PROVIDER_API_KEY": "test-only"}]


@pytest.mark.asyncio
async def test_execution_rejects_noncanonical_context_before_provider_construction() -> None:
    manager = _manager()
    constructions = 0

    def factory(configuration, secrets):
        nonlocal constructions
        constructions += 1
        return FixtureSearchProvider(configuration, secrets)

    manager.register_factory(
        package_id="fixture-provider-package",
        export="FixtureSearchProvider",
        factory=factory,
        provider_type=FixtureSearchProvider,
    )
    manager.discover([_manifest()])

    with pytest.raises(ProviderManagerError, match="invalid_request_context"):
        await manager.execute("fixture-search", _request(), object(), _execution())
    with pytest.raises(ProviderManagerError, match="invalid_execution_context"):
        await manager.execute("fixture-search", _request(), _request_context(), object())
    assert constructions == 0


@pytest.mark.asyncio
async def test_export_or_capability_mismatch_never_calls_factory() -> None:
    manager = _manager()
    calls = 0

    def factory(configuration, secrets):
        nonlocal calls
        calls += 1
        return FixtureSearchProvider(configuration, secrets)

    class WrongCapabilityProvider(FixtureSearchProvider):
        capability = "fetch"

    manager.register_factory(
        package_id="fixture-provider-package",
        export="WrongCapabilityProvider",
        factory=factory,
        provider_type=WrongCapabilityProvider,
    )
    manager.discover([_manifest(export="WrongCapabilityProvider")])

    assert manager.eligible_adapter_ids == ()
    assert calls == 0
    assert manager.diagnostics[-1].reason_code == "factory_capability_mismatch"


@pytest.mark.asyncio
async def test_execute_dispatches_fetch_capability_to_fetch_provider_method() -> None:
    calls: list[str] = []

    class FixtureFetchProvider:
        capability = "fetch"

        def __init__(self, configuration, secrets) -> None:
            self.configuration = configuration
            self.secrets = secrets

        async def fetch(self, request, context, execution):
            calls.append("fetch")
            return FetchResult(
                target=request.target,
                status="success",
                content="fixture article",
                content_metadata=ContentMetadata(
                    media_type="text/plain", truncated=False, quality="low"
                ),
                provenance=(Provenance(provider="fixture-search", outcome="success"),),
            )

        async def probe(self, execution):
            return ProviderProbe(
                provider="fixture-provider", capability="fetch", status="available"
            )

        async def close(self):
            return None

    declaration = _manifest(export="FixtureFetchProvider")
    declaration["capabilities"] = ["fetch"]
    declaration["adapters"][0]["capability"] = "fetch"
    manager = _manager()
    manager.register_factory(
        package_id="fixture-provider-package",
        export="FixtureFetchProvider",
        factory=FixtureFetchProvider,
        provider_type=FixtureFetchProvider,
    )
    manager.discover([declaration])

    result = await manager.execute(
        "fixture-search",
        FetchTargetRequest(target="https://example.com/article"),
        _request_context(),
        _execution(),
    )

    assert str(result.target) == "https://example.com/article"
    assert calls == ["fetch"]


@pytest.mark.asyncio
async def test_deadline_cancel_and_idempotent_close_do_not_leak_provider_details() -> None:
    manager = _manager()
    instance: FixtureSearchProvider | None = None

    def factory(configuration, secrets):
        nonlocal instance
        instance = FixtureSearchProvider(configuration, secrets)
        return instance

    manager.register_factory(
        package_id="fixture-provider-package",
        export="FixtureSearchProvider",
        factory=factory,
        provider_type=FixtureSearchProvider,
    )
    manager.discover([_manifest()])

    with pytest.raises(ProviderError) as exc_info:
        cancel_event = asyncio.Event()
        cancel_event.set()
        await manager.execute(
            "fixture-search",
            _request(),
            _request_context(),
            ExecutionContext.with_timeout(5, cancel_event=cancel_event),
        )
    assert exc_info.value.code is ProviderErrorCode.CANCELLED
    assert instance is None

    await manager.execute("fixture-search", _request(), _request_context(), _execution())
    await manager.close("fixture-search")
    await manager.close("fixture-search")

    assert instance is not None
    assert instance.close_count == 1


@pytest.mark.asyncio
async def test_cancellation_signal_stops_an_in_flight_provider_call() -> None:
    entered = asyncio.Event()
    cancelled = asyncio.Event()

    class CancellableProvider(FixtureSearchProvider):
        async def search(self, request, context, execution):
            entered.set()
            try:
                await asyncio.Future()
            except asyncio.CancelledError:
                cancelled.set()
                raise

    manager = _manager()
    manager.register_factory(
        package_id="fixture-provider-package",
        export="CancellableProvider",
        factory=CancellableProvider,
        provider_type=CancellableProvider,
    )
    manager.discover([_manifest(export="CancellableProvider")])
    cancel_event = asyncio.Event()
    task = asyncio.create_task(
        manager.execute(
            "fixture-search",
            _request(),
            _request_context(),
            ExecutionContext.with_timeout(5, cancel_event=cancel_event),
        )
    )

    await asyncio.wait_for(entered.wait(), timeout=1)
    cancel_event.set()

    with pytest.raises(ProviderError) as exc_info:
        await asyncio.wait_for(task, timeout=1)
    assert exc_info.value.code is ProviderErrorCode.CANCELLED
    assert cancelled.is_set()


@pytest.mark.asyncio
async def test_provider_failure_quarantines_only_the_failing_adapter() -> None:
    class FailingProvider(FixtureSearchProvider):
        async def search(self, request, context, execution):
            raise RuntimeError("secret=literal-secret-value")

    manager = _manager()
    manager.register_factory(
        package_id="fixture-provider-package",
        export="FailingProvider",
        factory=FailingProvider,
        provider_type=FailingProvider,
    )
    manager.register_factory(
        package_id="healthy-provider-package",
        export="FixtureSearchProvider",
        factory=FixtureSearchProvider,
        provider_type=FixtureSearchProvider,
    )
    manager.discover(
        [
            _manifest(export="FailingProvider"),
            _manifest(package_id="healthy-provider-package", adapter_id="healthy-search"),
        ]
    )

    with pytest.raises(ProviderManagerError, match="provider_failed"):
        await manager.execute("fixture-search", _request(), _request_context(), _execution())
    page = await manager.execute("healthy-search", _request(), _request_context(), _execution())
    assert page.items[0].title == "query"
    assert manager.diagnostics[-1].reason_code == "provider_failed"
    assert all("literal-secret-value" not in repr(item) for item in manager.diagnostics)


@pytest.mark.asyncio
async def test_each_adapter_uses_a_loop_local_concurrency_limit_of_ten() -> None:
    entered = asyncio.Event()
    release = asyncio.Event()
    calls = 0

    class BlockingProvider(FixtureSearchProvider):
        async def search(self, request, context, execution):
            nonlocal calls
            calls += 1
            if calls == 10:
                entered.set()
            await release.wait()
            return _page(context, request.query)

    manager = _manager()
    manager.register_factory(
        package_id="fixture-provider-package",
        export="BlockingProvider",
        factory=BlockingProvider,
        provider_type=BlockingProvider,
    )
    manager.discover([_manifest(export="BlockingProvider")])

    tasks = [
        asyncio.create_task(
            manager.execute(
                "fixture-search", _request(f"query-{index}"), _request_context(), _execution()
            )
        )
        for index in range(11)
    ]
    await asyncio.wait_for(entered.wait(), timeout=1)
    assert calls == 10
    release.set()
    pages = await asyncio.gather(*tasks)
    assert {page.items[0].title for page in pages} == {f"query-{index}" for index in range(11)}


@pytest.mark.asyncio
async def test_noncanonical_provider_output_quarantines_only_that_adapter() -> None:
    class RawProvider(FixtureSearchProvider):
        async def search(self, request, context, execution):
            return {"raw": "upstream"}

    manager = _manager()
    manager.register_factory(
        package_id="fixture-provider-package",
        export="RawProvider",
        factory=RawProvider,
        provider_type=RawProvider,
    )
    manager.discover([_manifest(export="RawProvider")])

    with pytest.raises(ProviderManagerError, match="invalid_provider_result"):
        await manager.execute("fixture-search", _request(), _request_context(), _execution())

    assert manager.diagnostics[-1].reason_code == "invalid_provider_result"
