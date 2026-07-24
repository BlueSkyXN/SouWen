"""Canonical LLM Search orchestration through an injected Provider Manager port."""

from __future__ import annotations

from typing import Protocol

from souwen.platform.provider_spi import (
    ExecutionContext,
    LLMSearchRequest,
    LLMSearchResult,
    ProviderError,
    ProviderErrorCode,
    RequestContext,
)


class LLMSearchProviderManager(Protocol):
    """Minimal manager port used by LLM Search Core."""

    async def execute(
        self,
        adapter_id: str,
        request: LLMSearchRequest,
        request_context: RequestContext,
        execution: ExecutionContext,
    ) -> LLMSearchResult:
        """Execute exactly one configured LLM Search adapter."""


class LLMSearchModuleService:
    """Execute the deployment-selected immutable LLM Search provider.

    RC2 intentionally permits exactly one YAML-enabled UniAPI adapter. The
    request identifies that public provider for contract transparency, but it
    cannot select a different source, scheme, gateway, or model.
    """

    def __init__(self, manager: LLMSearchProviderManager, configured_adapter_id: str) -> None:
        configured_adapter_id = configured_adapter_id.strip()
        if not configured_adapter_id:
            raise ValueError("configured_adapter_id must not be blank")
        self._manager = manager
        self._configured_adapter_id = configured_adapter_id

    async def search(
        self,
        request: LLMSearchRequest,
        context: RequestContext,
        execution: ExecutionContext,
    ) -> LLMSearchResult:
        """Reject request-side provider overrides before any provider call."""
        execution.raise_if_cancelled_or_expired()
        if request.strategy != "single" or len(request.providers) != 1:
            raise ProviderError(ProviderErrorCode.INVALID_REQUEST)
        provider = request.providers[0]
        if provider.kind != "llm_search" or provider.id != self._configured_adapter_id:
            raise ProviderError(ProviderErrorCode.INVALID_REQUEST)

        result = await self._manager.execute(
            self._configured_adapter_id,
            request,
            context,
            execution,
        )
        execution.raise_if_cancelled_or_expired()
        if result.query != request.query or result.context != context:
            raise ProviderError(
                ProviderErrorCode.INVALID_UPSTREAM_RESPONSE,
                provider_id=self._configured_adapter_id,
            )
        return result


__all__ = ["LLMSearchModuleService", "LLMSearchProviderManager"]
