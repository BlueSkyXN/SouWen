"""Explicit, lazy assembly for already-declared Provider v2 adapters.

The manager never imports provider modules by name.  A composition root must
register a factory and its concrete provider type explicitly before discovery.
"""

from __future__ import annotations

import asyncio
import inspect
import time
from collections.abc import Awaitable, Callable, Iterable, Mapping
from contextlib import suppress
from dataclasses import dataclass, field
from typing import Any, Protocol

from souwen.common_runtime.resilience.concurrency import LoopLocalSemaphorePool
from souwen.platform.manifest_registry.models import AdapterDeclaration, ProviderManifest
from souwen.platform.manifest_registry.registry import ManifestRegistration, ManifestRegistry
from souwen.platform.provider_spi import (
    Capability,
    ExecutionContext,
    FetchResult,
    FetchTargetRequest,
    LLMSearchRequest,
    LLMSearchResult,
    ProviderError,
    ProviderErrorCode,
    ProviderProbe,
    RequestContext,
    SearchPage,
    SearchRequest,
)


class ProviderFactory(Protocol):
    """Construct one adapter from its already-resolved local inputs."""

    def __call__(self, configuration: Mapping[str, Any], secrets: Mapping[str, str]) -> Any: ...


ConfigResolver = Callable[[ProviderManifest], Mapping[str, Any]]
SecretResolver = Callable[[ProviderManifest, tuple[str, ...]], Mapping[str, str]]
SchemaValidator = Callable[[ProviderManifest, Mapping[str, Any]], Mapping[str, Any]]

_SAFE_MANAGER_CODES = frozenset(
    {
        "adapter_not_registered",
        "adapter_not_eligible",
        "adapter_quarantined",
        "config_invalid",
        "secret_unavailable",
        "factory_missing",
        "factory_export_mismatch",
        "factory_capability_mismatch",
        "factory_spi_mismatch",
        "factory_failed",
        "execution_context_required",
        "invalid_request_context",
        "invalid_execution_context",
        "invalid_request",
        "invalid_provider_result",
        "invalid_probe_result",
        "provider_failed",
        "probe_failed",
        "close_failed",
    }
)


class ProviderManagerError(RuntimeError):
    """Bounded runtime error that intentionally has no upstream exception text."""

    def __init__(self, code: str) -> None:
        if code not in _SAFE_MANAGER_CODES:
            raise ValueError("unsupported provider manager error code")
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class ProviderDiagnostic:
    """Safe, bounded lifecycle diagnostic without config, secret, or exception data."""

    reason_code: str
    package_id: str
    adapter_id: str
    capability: str


@dataclass(frozen=True, slots=True)
class FactoryRegistration:
    """An explicit factory declaration; provider_type enables static preflight."""

    package_id: str
    export: str
    factory: ProviderFactory
    provider_type: type[Any] | None = None


@dataclass(slots=True)
class _AdapterRuntime:
    manifest: ProviderManifest
    adapter: AdapterDeclaration
    configuration: Mapping[str, Any]
    secrets: Mapping[str, str]
    factory: ProviderFactory
    provider_type: type[Any]
    semaphore_pool: LoopLocalSemaphorePool = field(default_factory=LoopLocalSemaphorePool)
    instance: Any | None = None
    closed: bool = False
    quarantined: bool = False


class ProviderManager:
    """Manage v2 provider eligibility, lazy instances, and provider-local faults."""

    def __init__(
        self,
        registry: ManifestRegistry | None = None,
        *,
        config_resolver: ConfigResolver | None = None,
        secret_resolver: SecretResolver | None = None,
        schema_validator: SchemaValidator | None = None,
    ) -> None:
        self.registry = registry or ManifestRegistry()
        self._config_resolver = config_resolver or _default_config_resolver
        self._secret_resolver = secret_resolver or _default_secret_resolver
        self._schema_validator = schema_validator or _default_schema_validator
        self._factories: dict[tuple[str, str], FactoryRegistration] = {}
        self._runtimes: dict[str, _AdapterRuntime] = {}
        self._diagnostics: list[ProviderDiagnostic] = []

    def register_factory(
        self,
        *,
        package_id: str,
        export: str,
        factory: ProviderFactory,
        provider_type: type[Any] | None = None,
    ) -> None:
        """Add a factory explicitly; this intentionally accepts no module path."""
        if not callable(factory):
            raise TypeError("factory must be callable")
        self._factories[(package_id, export)] = FactoryRegistration(
            package_id=package_id,
            export=export,
            factory=factory,
            provider_type=provider_type,
        )

    def discover(
        self, declarations: Iterable[ProviderManifest | Mapping[str, Any]]
    ) -> tuple[ManifestRegistration, ...]:
        """Statically register then preflight eligibility without creating an instance."""
        registrations = self.registry.discover(declarations)
        for registration in registrations:
            if registration.manifest is not None:
                self._preflight_manifest(registration.manifest)
        return registrations

    def preflight_registered(self) -> None:
        """Re-evaluate static packages after an explicit factory registration change."""
        for manifest in self.registry.packages:
            self._preflight_manifest(manifest)

    async def execute(
        self,
        adapter_id: str,
        request: Any,
        request_context: Any,
        execution: Any,
        *,
        timeout: float | None = None,
    ) -> Any:
        """Lazily create and execute a declared adapter under its loop-local limit."""
        runtime = self._runtime_for(adapter_id)
        _validate_execution_inputs(runtime.adapter.capability, request, request_context, execution)
        self._raise_if_cancelled(execution)
        provider = self._instance_for(runtime)
        timeout = _execution_timeout(execution, timeout)
        try:
            async with runtime.semaphore_pool.get(10):
                self._raise_if_cancelled(execution)
                call = _provider_call(
                    provider,
                    runtime.adapter.capability,
                    request,
                    request_context,
                    execution,
                )
                result = await _await_with_execution(call, execution, timeout)
                if not _provider_result_matches(
                    runtime.adapter.capability, request, request_context, result
                ):
                    await self._quarantine(runtime, "invalid_provider_result")
                    raise ProviderManagerError("invalid_provider_result")
                return result
        except asyncio.CancelledError:
            raise
        except ProviderError:
            raise
        except TimeoutError as exc:
            raise ProviderError(ProviderErrorCode.DEADLINE_EXCEEDED) from exc
        except ProviderManagerError:
            raise
        except Exception as exc:
            await self._quarantine(runtime, "provider_failed")
            raise ProviderManagerError("provider_failed") from exc

    async def probe(self, adapter_id: str, execution: Any, *, timeout: float | None = None) -> Any:
        """Explicitly probe one eligible adapter without changing its eligibility."""
        runtime = self._runtime_for(adapter_id)
        if not isinstance(execution, ExecutionContext):
            raise ProviderManagerError("invalid_execution_context")
        self._raise_if_cancelled(execution)
        provider = self._instance_for(runtime)
        timeout = _execution_timeout(execution, timeout)
        try:
            async with runtime.semaphore_pool.get(10):
                result = await _await_with_execution(provider.probe(execution), execution, timeout)
                if (
                    not isinstance(result, ProviderProbe)
                    or result.capability != runtime.adapter.capability
                ):
                    await self._quarantine(runtime, "invalid_probe_result")
                    raise ProviderManagerError("invalid_probe_result")
                return result
        except asyncio.CancelledError:
            raise
        except ProviderError:
            raise
        except TimeoutError as exc:
            raise ProviderError(ProviderErrorCode.DEADLINE_EXCEEDED) from exc
        except ProviderManagerError:
            raise
        except Exception as exc:
            await self._quarantine(runtime, "probe_failed")
            raise ProviderManagerError("probe_failed") from exc

    async def close(self, adapter_id: str) -> None:
        """Close one owned adapter at most once; unrelated adapters remain active."""
        runtime = self._runtimes.get(adapter_id)
        if runtime is None or runtime.closed:
            return
        runtime.closed = True
        if runtime.instance is None:
            return
        try:
            result = runtime.instance.close()
            if inspect.isawaitable(result):
                await result
        except asyncio.CancelledError:
            runtime.closed = False
            raise
        except Exception as exc:
            self._diagnose(runtime, "close_failed")
            raise ProviderManagerError("close_failed") from exc

    async def close_all(self) -> None:
        """Close every created adapter, preserving the first safe failure."""
        failure: ProviderManagerError | None = None
        for adapter_id in tuple(self._runtimes):
            try:
                await self.close(adapter_id)
            except ProviderManagerError as exc:
                if failure is None:
                    failure = exc
        if failure is not None:
            raise failure

    @property
    def diagnostics(self) -> tuple[ProviderDiagnostic, ...]:
        return tuple(self._diagnostics)

    @property
    def eligible_adapter_ids(self) -> tuple[str, ...]:
        return tuple(self._runtimes)

    def _preflight_manifest(self, manifest: ProviderManifest) -> None:
        """Resolve local inputs and inspect exports, but do not call provider factories."""
        for adapter in manifest.adapters:
            runtime = self._preflight_adapter(manifest, adapter)
            if runtime is not None:
                self._runtimes[adapter.id] = runtime

    def _preflight_adapter(
        self, manifest: ProviderManifest, adapter: AdapterDeclaration
    ) -> _AdapterRuntime | None:
        factory_registration = self._factories.get((manifest.id, adapter.export))
        if factory_registration is None:
            self._diagnose_declaration(manifest, adapter, "factory_missing")
            return None
        provider_type = _provider_type(factory_registration)
        if provider_type is None or provider_type.__name__ != adapter.export:
            self._diagnose_declaration(manifest, adapter, "factory_export_mismatch")
            return None
        capability = _capability_name(getattr(provider_type, "capability", None))
        if capability != adapter.capability:
            self._diagnose_declaration(manifest, adapter, "factory_capability_mismatch")
            return None
        capability_method = "fetch" if adapter.capability == "fetch" else "search"
        if not all(
            callable(getattr(provider_type, name, None))
            for name in (capability_method, "probe", "close")
        ):
            self._diagnose_declaration(manifest, adapter, "factory_spi_mismatch")
            return None
        try:
            configuration = self._schema_validator(manifest, self._config_resolver(manifest))
        except Exception:
            self._diagnose_declaration(manifest, adapter, "config_invalid")
            return None
        try:
            secrets = self._secret_resolver(manifest, manifest.secrets.all_references)
        except Exception:
            self._diagnose_declaration(manifest, adapter, "secret_unavailable")
            return None
        if not isinstance(configuration, Mapping):
            self._diagnose_declaration(manifest, adapter, "config_invalid")
            return None
        if not isinstance(secrets, Mapping) or not _has_declared_secrets(manifest, secrets):
            self._diagnose_declaration(manifest, adapter, "secret_unavailable")
            return None
        return _AdapterRuntime(
            manifest=manifest,
            adapter=adapter,
            configuration=dict(configuration),
            secrets=dict(secrets),
            factory=factory_registration.factory,
            provider_type=provider_type,
        )

    def _runtime_for(self, adapter_id: str) -> _AdapterRuntime:
        static = self.registry.adapter(adapter_id)
        if static is None:
            raise ProviderManagerError("adapter_not_registered")
        runtime = self._runtimes.get(adapter_id)
        if runtime is None:
            raise ProviderManagerError("adapter_not_eligible")
        if runtime.quarantined:
            raise ProviderManagerError("adapter_quarantined")
        if runtime.closed:
            raise ProviderManagerError("adapter_quarantined")
        return runtime

    def _instance_for(self, runtime: _AdapterRuntime) -> Any:
        if runtime.instance is not None:
            return runtime.instance
        try:
            instance = runtime.factory(runtime.configuration, runtime.secrets)
        except Exception as exc:
            runtime.quarantined = True
            self._diagnose(runtime, "factory_failed")
            raise ProviderManagerError("factory_failed") from exc
        if not isinstance(instance, runtime.provider_type):
            runtime.quarantined = True
            self._diagnose(runtime, "factory_spi_mismatch")
            raise ProviderManagerError("factory_spi_mismatch")
        runtime.instance = instance
        return instance

    async def _quarantine(self, runtime: _AdapterRuntime, reason_code: str) -> None:
        runtime.quarantined = True
        self._diagnose(runtime, reason_code)
        try:
            await self.close(runtime.adapter.id)
        except ProviderManagerError:
            pass

    def _diagnose(self, runtime: _AdapterRuntime, reason_code: str) -> None:
        self._diagnose_declaration(runtime.manifest, runtime.adapter, reason_code)

    def _diagnose_declaration(
        self, manifest: ProviderManifest, adapter: AdapterDeclaration, reason_code: str
    ) -> None:
        if reason_code not in _SAFE_MANAGER_CODES:
            raise ValueError("unsupported provider manager diagnostic code")
        self._diagnostics.append(
            ProviderDiagnostic(reason_code, manifest.id, adapter.id, adapter.capability)
        )

    @staticmethod
    def _raise_if_cancelled(context: Any) -> None:
        raise_if_cancelled = getattr(context, "raise_if_cancelled_or_expired", None)
        if callable(raise_if_cancelled):
            raise_if_cancelled()
        if _is_cancelled(context):
            raise ProviderError(ProviderErrorCode.CANCELLED)


def _provider_type(registration: FactoryRegistration) -> type[Any] | None:
    if registration.provider_type is not None:
        return registration.provider_type
    if isinstance(registration.factory, type):
        return registration.factory
    candidate = getattr(registration.factory, "provider_type", None)
    return candidate if isinstance(candidate, type) else None


def _capability_name(value: Any) -> Capability | None:
    candidate = getattr(value, "value", value)
    return candidate if candidate in {"search", "llm_search", "fetch"} else None


def _default_config_resolver(_manifest: ProviderManifest) -> Mapping[str, Any]:
    return {}


def _default_secret_resolver(
    _manifest: ProviderManifest, _references: tuple[str, ...]
) -> Mapping[str, str]:
    return {}


def _default_schema_validator(
    manifest: ProviderManifest, configuration: Mapping[str, Any]
) -> Mapping[str, Any]:
    if not isinstance(configuration, Mapping):
        raise TypeError("provider configuration must be a mapping")
    if manifest.configuration.unknown_key_policy == "reject":
        unknown = set(configuration).difference(manifest.configuration.non_secret_keys)
        if unknown:
            raise ValueError("unknown provider configuration key")
    return configuration


def _has_declared_secrets(manifest: ProviderManifest, secrets: Mapping[str, str]) -> bool:
    """Require mandatory references while accepting only nonblank declared optionals."""
    declared = set(manifest.secrets.all_references)
    if set(secrets).difference(declared):
        return False
    if not all(
        isinstance(secrets.get(reference), str) and bool(secrets[reference].strip())
        for reference in manifest.secrets.references
    ):
        return False
    return all(
        reference not in secrets
        or (isinstance(secrets[reference], str) and bool(secrets[reference].strip()))
        for reference in manifest.secrets.optional_references
    )


def _validate_execution_inputs(
    capability: Capability,
    request: Any,
    request_context: Any,
    execution: Any,
) -> None:
    """Reject non-canonical call inputs before provider construction or invocation."""
    if not isinstance(request_context, RequestContext):
        raise ProviderManagerError("invalid_request_context")
    if not isinstance(execution, ExecutionContext):
        raise ProviderManagerError("invalid_execution_context")
    expected_type = (
        FetchTargetRequest
        if capability == "fetch"
        else (LLMSearchRequest if capability == "llm_search" else SearchRequest)
    )
    if not isinstance(request, expected_type):
        raise ProviderManagerError("invalid_request")


def _is_cancelled(context: Any) -> bool:
    value = getattr(context, "cancelled", False)
    if callable(value):
        value = value()
    if hasattr(value, "is_set"):
        value = value.is_set()
    return bool(value)


def _execution_timeout(context: Any, explicit_timeout: float | None) -> float | None:
    """Use the shortest explicit or monotonic deadline without exposing it in diagnostics."""
    candidates = [timeout for timeout in (explicit_timeout,) if timeout is not None]
    deadline = getattr(context, "deadline_monotonic", getattr(context, "deadline", None))
    if isinstance(deadline, (int, float)) and not isinstance(deadline, bool):
        candidates.append(max(0.0, float(deadline) - time.monotonic()))
    if not candidates:
        return None
    timeout = min(candidates)
    if timeout < 0:
        raise ProviderError(ProviderErrorCode.DEADLINE_EXCEEDED)
    return timeout


async def _await_with_execution(
    value: Awaitable[Any], execution: ExecutionContext, timeout: float | None
) -> Any:
    """Bound a provider awaitable by both deadline and live cancellation signal."""
    provider_task = asyncio.ensure_future(value)
    cancellation_task = asyncio.create_task(execution.cancel_event.wait())
    try:
        done, _pending = await asyncio.wait(
            {provider_task, cancellation_task},
            timeout=timeout,
            return_when=asyncio.FIRST_COMPLETED,
        )
        if provider_task in done:
            return await provider_task

        provider_task.cancel()
        with suppress(asyncio.CancelledError):
            await provider_task
        code = (
            ProviderErrorCode.CANCELLED
            if cancellation_task in done
            else ProviderErrorCode.DEADLINE_EXCEEDED
        )
        raise ProviderError(code)
    finally:
        cancellation_task.cancel()
        if not provider_task.done():
            provider_task.cancel()
        await asyncio.gather(provider_task, cancellation_task, return_exceptions=True)


def _provider_call(
    provider: Any,
    capability: str,
    request: Any,
    request_context: Any,
    execution: Any,
) -> Awaitable[Any]:
    """Dispatch exactly one declared SPI capability; no provider cross-call is possible."""
    method = provider.fetch if capability == "fetch" else provider.search
    return method(request, request_context, execution)


def _provider_result_matches(
    capability: Capability,
    request: SearchRequest | LLMSearchRequest | FetchTargetRequest,
    request_context: RequestContext,
    result: Any,
) -> bool:
    """Reject raw or capability-mismatched provider output at the assembly boundary."""
    if capability == "fetch":
        return (
            isinstance(request, FetchTargetRequest)
            and isinstance(result, FetchResult)
            and str(result.target) == str(request.target)
        )
    if capability == "llm_search":
        return isinstance(result, LLMSearchResult) and result.context == request_context
    return isinstance(result, SearchPage) and result.context == request_context
