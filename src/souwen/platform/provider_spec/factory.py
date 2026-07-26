"""Generic lifecycle/error wrapper for injected legacy REST JSON search clients."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass
from typing import Any

from souwen.common_runtime.errors import SouWenError
from souwen.common_runtime.transport.errors import AuthError, RateLimitError, SourceUnavailableError
from souwen.platform.provider_spi import (
    ExecutionContext,
    FetchResult,
    FetchTargetRequest,
    ProviderError,
    ProviderErrorCode,
    ProviderProbe,
    RequestContext,
    SearchDomain,
    SearchPage,
    SearchRequest,
)
from souwen.platform.provider_spec.models import RestJsonProviderSpec


@dataclass(frozen=True, slots=True)
class LegacySearchSpec:
    """Typed callbacks separating provider mapping from shared lifecycle behavior."""

    provider_id: str
    domain: SearchDomain
    invoke: Callable[[Any, SearchRequest, int], Awaitable[Any]]
    project: Callable[[Any, int, RequestContext], SearchPage]
    accepts_filters: bool = False


@dataclass(frozen=True, slots=True)
class LegacyFetchSpec:
    """Typed callbacks separating Fetch mapping from shared lifecycle behavior."""

    provider_id: str
    invoke: Callable[[Any, FetchTargetRequest], Awaitable[Any]]
    project: Callable[[Any, FetchTargetRequest, RequestContext], FetchResult]


class LegacyFetchProvider:
    """Reusable Fetch SPI wrapper for one fixed, injected legacy client."""

    capability = "fetch"

    def __init__(self, client: Any, spec: LegacyFetchSpec, *, enabled: bool = True) -> None:
        self._client, self._spec, self._enabled, self._closed = client, spec, enabled, False

    async def fetch(
        self,
        request: FetchTargetRequest,
        context: RequestContext,
        execution: ExecutionContext,
    ) -> FetchResult:
        execution.raise_if_cancelled_or_expired()
        if self._closed or not self._enabled:
            raise ProviderError(
                ProviderErrorCode.INVALID_CONFIG, provider_id=self._spec.provider_id
            )
        try:
            result = await _await(self._spec.invoke(self._client, request), execution)
            execution.raise_if_cancelled_or_expired()
            return self._spec.project(result, request, context)
        except asyncio.CancelledError:
            raise
        except ProviderError:
            raise
        except RateLimitError as exc:
            raise ProviderError(
                ProviderErrorCode.RATE_LIMITED,
                provider_id=self._spec.provider_id,
                retry_after_seconds=getattr(exc, "retry_after", None),
            ) from None
        except TimeoutError:
            raise ProviderError(
                ProviderErrorCode.DEADLINE_EXCEEDED, provider_id=self._spec.provider_id
            ) from None
        except AuthError:
            raise ProviderError(
                ProviderErrorCode.INVALID_CONFIG, provider_id=self._spec.provider_id
            ) from None
        except SourceUnavailableError:
            raise ProviderError(
                ProviderErrorCode.PROVIDER_UNAVAILABLE, provider_id=self._spec.provider_id
            ) from None
        except SouWenError as exc:
            code = (
                ProviderErrorCode.INVALID_CONFIG
                if type(exc).__name__ == "ConfigError"
                else ProviderErrorCode.INVALID_UPSTREAM_RESPONSE
            )
            raise ProviderError(code, provider_id=self._spec.provider_id) from None
        except (AttributeError, TypeError, ValueError):
            raise ProviderError(
                ProviderErrorCode.INVALID_UPSTREAM_RESPONSE, provider_id=self._spec.provider_id
            ) from None
        except Exception:
            raise ProviderError(
                ProviderErrorCode.PROVIDER_UNAVAILABLE, provider_id=self._spec.provider_id
            ) from None

    async def probe(self, execution: ExecutionContext) -> ProviderProbe:
        execution.raise_if_cancelled_or_expired()
        return ProviderProbe(
            provider=self._spec.provider_id,
            capability="fetch",
            status="unavailable" if self._closed or not self._enabled else "available",
        )

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        closer = getattr(self._client, "aclose", None) or getattr(self._client, "close", None)
        if closer is None:
            return
        try:
            value = closer()
            if inspect.isawaitable(value):
                await value
        except asyncio.CancelledError:
            self._closed = False
            raise


class LegacySearchProvider:
    """Reusable Search SPI wrapper for a fixed, injected legacy client."""

    capability = "search"

    def __init__(self, client: Any, spec: LegacySearchSpec, *, enabled: bool = True) -> None:
        self._client, self._spec, self._enabled, self._closed = client, spec, enabled, False

    async def search(
        self, request: SearchRequest, context: RequestContext, execution: ExecutionContext
    ) -> SearchPage:
        execution.raise_if_cancelled_or_expired()
        if self._closed or not self._enabled:
            raise ProviderError(
                ProviderErrorCode.INVALID_CONFIG, provider_id=self._spec.provider_id
            )
        if request.domains != (self._spec.domain,) or (request.page and request.page.cursor):
            raise ProviderError(
                ProviderErrorCode.INVALID_REQUEST, provider_id=self._spec.provider_id
            )
        if (
            not self._spec.accepts_filters
            and request.filters
            and request.filters.model_dump(exclude_none=True)
        ):
            raise ProviderError(
                ProviderErrorCode.INVALID_REQUEST, provider_id=self._spec.provider_id
            )
        try:
            result = await _await(
                self._spec.invoke(
                    self._client, request, request.page.limit if request.page else 10
                ),
                execution,
            )
            execution.raise_if_cancelled_or_expired()
            return self._spec.project(result, request.page.limit if request.page else 10, context)
        except asyncio.CancelledError:
            raise
        except ProviderError:
            raise
        except RateLimitError as exc:
            raise ProviderError(
                ProviderErrorCode.RATE_LIMITED,
                provider_id=self._spec.provider_id,
                retry_after_seconds=getattr(exc, "retry_after", None),
            ) from None
        except TimeoutError:
            raise ProviderError(
                ProviderErrorCode.DEADLINE_EXCEEDED, provider_id=self._spec.provider_id
            ) from None
        except AuthError:
            raise ProviderError(
                ProviderErrorCode.INVALID_CONFIG, provider_id=self._spec.provider_id
            ) from None
        except SourceUnavailableError:
            raise ProviderError(
                ProviderErrorCode.PROVIDER_UNAVAILABLE, provider_id=self._spec.provider_id
            ) from None
        except SouWenError as exc:
            code = (
                ProviderErrorCode.INVALID_CONFIG
                if type(exc).__name__ == "ConfigError"
                else ProviderErrorCode.INVALID_UPSTREAM_RESPONSE
            )
            raise ProviderError(code, provider_id=self._spec.provider_id) from None
        except (AttributeError, TypeError, ValueError):
            raise ProviderError(
                ProviderErrorCode.INVALID_UPSTREAM_RESPONSE, provider_id=self._spec.provider_id
            ) from None
        except Exception:
            raise ProviderError(
                ProviderErrorCode.PROVIDER_UNAVAILABLE, provider_id=self._spec.provider_id
            ) from None

    async def probe(self, execution: ExecutionContext) -> ProviderProbe:
        execution.raise_if_cancelled_or_expired()
        return ProviderProbe(
            provider=self._spec.provider_id,
            capability="search",
            status="unavailable" if self._closed or not self._enabled else "available",
        )

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        closer = getattr(self._client, "aclose", None) or getattr(self._client, "close", None)
        if closer is None:
            return
        try:
            value = closer()
            if inspect.isawaitable(value):
                await value
        except asyncio.CancelledError:
            self._closed = False
            raise


async def _await(value: Awaitable[Any], execution: ExecutionContext) -> Any:
    task, cancel = asyncio.ensure_future(value), asyncio.create_task(execution.cancel_event.wait())
    try:
        done, _ = await asyncio.wait(
            {task, cancel}, timeout=execution.remaining_seconds, return_when=asyncio.FIRST_COMPLETED
        )
        if task in done:
            return await task
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        raise ProviderError(
            ProviderErrorCode.CANCELLED if cancel in done else ProviderErrorCode.DEADLINE_EXCEEDED
        )
    finally:
        cancel.cancel()
        if not task.done():
            task.cancel()
        await asyncio.gather(task, cancel, return_exceptions=True)


class RestJsonSearchProvider(LegacySearchProvider):
    """Generic first-page projection driven by ``RestJsonProviderSpec`` mappings."""

    def __init__(self, client: Any, spec: RestJsonProviderSpec, *, enabled: bool = True) -> None:
        if spec.adapter_kind != "generic_rest_json" or spec.response_mapping is None:
            raise ValueError("generic factory requires a reviewed generic REST JSON spec")
        self.rest_spec = spec
        super().__init__(
            client,
            LegacySearchSpec(spec.provider_id, spec.domain, self._invoke, self._project),
            enabled=enabled,
        )

    async def _invoke(self, client: Any, request: SearchRequest, limit: int) -> Any:
        mapping = self.rest_spec.request_mapping
        params: dict[str, Any] = {mapping.query_field: request.query, mapping.limit_field: limit}
        params.update(mapping.fixed_fields)
        return await client.search(**params)

    def _project(self, response: Any, limit: int, context: RequestContext) -> SearchPage:
        from .projection import project_search_page

        assert self.rest_spec.response_mapping is not None
        return project_search_page(self.rest_spec, response, limit, context)
