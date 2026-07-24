"""Provider v2 adapters for structured UniAPI Ark web-search annotations."""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import ipaddress
from collections.abc import Mapping
from contextlib import suppress
from datetime import datetime, timezone
from typing import Any, Callable, ClassVar, Protocol
from urllib.parse import urlsplit, urlunsplit

from souwen.common_runtime.errors import SouWenError
from souwen.common_runtime.transport.errors import (
    AuthError,
    RateLimitError,
    SourceUnavailableError,
)
from souwen.common_runtime.transport.http_client import HttpTransport
from souwen.platform.provider_spi import (
    EvidenceItem,
    ExecutionContext,
    LLMSearchRequest,
    LLMSearchResult,
    ProviderError,
    ProviderErrorCode,
    ProviderProbe,
    Provenance,
    RequestContext,
    SearchItem,
    SearchMeta,
    Usage,
)

from .manifest import DEEPSEEK_ADAPTER_ID, DOUBAO_ADAPTER_ID


_RESPONSE_PATH = "/v1/responses"
_DEFAULT_TIMEOUT_SECONDS = 45.0
_DEFAULT_MAX_KEYWORD = 10
_MAX_RESULTS = 50


class _ResponseProtocol(Protocol):
    def json(self) -> Any:
        """Return a decoded response payload."""


class ArkTransportProtocol(Protocol):
    async def post(
        self,
        url: str,
        json: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        retry_policy: str = "default",
    ) -> _ResponseProtocol:
        """Execute one Ark Responses request."""

    async def close(self) -> None:
        """Release owned transport resources."""


class _UniApiArkAnnotationsProvider:
    """One exact source/model binding with no request-side identity override."""

    capability = "llm_search"
    ADAPTER_ID: ClassVar[str]
    MODEL_ID: ClassVar[str]

    def __init__(
        self,
        configuration: Mapping[str, Any],
        secrets: Mapping[str, str],
        *,
        transport: ArkTransportProtocol | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._enabled, self._max_keyword, timeout = _validated_configuration(configuration)
        api_key, base_url = _validated_secrets(secrets)
        self._transport = transport or HttpTransport(
            base_url=base_url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout=timeout,
            max_retries=0,
            proxy=None,
            follow_redirects=False,
        )
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._closed = False

    async def search(
        self,
        request: LLMSearchRequest,
        context: RequestContext,
        execution: ExecutionContext,
    ) -> LLMSearchResult:
        """Execute one paid, single-attempt Ark request and require structured evidence."""
        execution.raise_if_cancelled_or_expired()
        if self._closed or not self._enabled:
            raise ProviderError(ProviderErrorCode.INVALID_CONFIG, provider_id=self.ADAPTER_ID)
        if (
            request.strategy != "single"
            or len(request.providers) != 1
            or request.providers[0].kind != "llm_search"
            or request.providers[0].id != self.ADAPTER_ID
            or request.fetch is not None
            or request.synthesis_profile is not None
        ):
            raise ProviderError(ProviderErrorCode.INVALID_REQUEST, provider_id=self.ADAPTER_ID)

        max_results = request.max_results_per_provider or self._max_keyword
        if not 1 <= max_results <= _MAX_RESULTS:
            raise ProviderError(ProviderErrorCode.INVALID_REQUEST, provider_id=self.ADAPTER_ID)
        payload = {
            "model": self.MODEL_ID,
            "input": request.query,
            "tools": [{"type": "web_search", "max_keyword": max_results}],
        }
        try:
            response = await _await_with_execution(
                self._transport.post(
                    _RESPONSE_PATH,
                    json=payload,
                    retry_policy="single_attempt",
                ),
                execution,
                self.ADAPTER_ID,
            )
            execution.raise_if_cancelled_or_expired()
            response_payload = response.json()
            retrieved_at = self._clock()
            if retrieved_at.tzinfo is None:
                raise ValueError("retrieval timestamp must be timezone-aware")
            return _parse_result(
                response_payload,
                adapter_id=self.ADAPTER_ID,
                model_id=self.MODEL_ID,
                query=request.query,
                context=context,
                retrieved_at=retrieved_at,
                max_results=max_results,
            )
        except asyncio.CancelledError:
            raise
        except ProviderError:
            raise
        except RateLimitError as exc:
            raise ProviderError(
                ProviderErrorCode.RATE_LIMITED,
                provider_id=self.ADAPTER_ID,
                retry_after_seconds=getattr(exc, "retry_after", None),
            ) from None
        except AuthError:
            raise ProviderError(
                ProviderErrorCode.INVALID_CONFIG,
                provider_id=self.ADAPTER_ID,
            ) from None
        except TimeoutError:
            raise ProviderError(
                ProviderErrorCode.DEADLINE_EXCEEDED,
                provider_id=self.ADAPTER_ID,
            ) from None
        except SourceUnavailableError:
            raise ProviderError(
                ProviderErrorCode.PROVIDER_UNAVAILABLE,
                provider_id=self.ADAPTER_ID,
            ) from None
        except (AttributeError, TypeError, ValueError):
            raise ProviderError(
                ProviderErrorCode.INVALID_UPSTREAM_RESPONSE,
                provider_id=self.ADAPTER_ID,
            ) from None
        except SouWenError:
            raise ProviderError(
                ProviderErrorCode.INVALID_UPSTREAM_RESPONSE,
                provider_id=self.ADAPTER_ID,
            ) from None
        except Exception:
            raise ProviderError(
                ProviderErrorCode.PROVIDER_UNAVAILABLE,
                provider_id=self.ADAPTER_ID,
            ) from None

    async def probe(self, execution: ExecutionContext) -> ProviderProbe:
        """Return credential/config readiness without a network or paid request."""
        execution.raise_if_cancelled_or_expired()
        return ProviderProbe(
            provider=self.ADAPTER_ID,
            capability="llm_search",
            status="unavailable" if self._closed or not self._enabled else "available",
        )

    async def close(self) -> None:
        """Close the owned transport at most once."""
        if self._closed:
            return
        self._closed = True
        closer = getattr(self._transport, "close", None)
        if closer is None:
            return
        try:
            result = closer()
            if inspect.isawaitable(result):
                await result
        except asyncio.CancelledError:
            self._closed = False
            raise


class UniApiArkAnnotationsDeepSeekProvider(_UniApiArkAnnotationsProvider):
    """Ark annotations adapter bound to DeepSeek V3.2's exact model ID."""

    ADAPTER_ID = DEEPSEEK_ADAPTER_ID
    MODEL_ID = "deepseek-v3-2-251201"


class UniApiArkAnnotationsDoubaoProvider(_UniApiArkAnnotationsProvider):
    """Ark annotations adapter bound to Doubao Seed 2.0 Lite's exact model ID."""

    ADAPTER_ID = DOUBAO_ADAPTER_ID
    MODEL_ID = "doubao-seed-2-0-lite-260428"


def _validated_configuration(configuration: Mapping[str, Any]) -> tuple[bool, int, float]:
    if not isinstance(configuration, Mapping) or set(configuration).difference(
        {"enabled", "max_keyword", "timeout_seconds"}
    ):
        raise ValueError("invalid provider configuration")
    enabled = configuration.get("enabled")
    if enabled is not True:
        raise ValueError("provider must be explicitly enabled")
    max_keyword = configuration.get("max_keyword", _DEFAULT_MAX_KEYWORD)
    timeout = configuration.get("timeout_seconds", _DEFAULT_TIMEOUT_SECONDS)
    if (
        not isinstance(max_keyword, int)
        or isinstance(max_keyword, bool)
        or not 1 <= max_keyword <= _MAX_RESULTS
    ):
        raise ValueError("invalid max_keyword")
    if (
        not isinstance(timeout, (int, float))
        or isinstance(timeout, bool)
        or not 1 <= float(timeout) <= 120
    ):
        raise ValueError("invalid timeout_seconds")
    return enabled, max_keyword, float(timeout)


def _validated_secrets(secrets: Mapping[str, str]) -> tuple[str, str]:
    if not isinstance(secrets, Mapping):
        raise ValueError("invalid provider secrets")
    api_key = secrets.get("UNIAPI_API_KEY")
    base_url = secrets.get("UNIAPI_BASE_URL")
    if not isinstance(api_key, str) or not api_key.strip():
        raise ValueError("missing provider credential")
    if not isinstance(base_url, str) or not base_url.strip():
        raise ValueError("missing provider gateway")
    parsed = urlsplit(base_url.strip())
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise ValueError("invalid provider gateway")
    return api_key.strip(), base_url.strip().rstrip("/")


async def _await_with_execution(
    value: Any,
    execution: ExecutionContext,
    provider_id: str,
) -> Any:
    provider_task = asyncio.ensure_future(value)
    cancellation_task = asyncio.create_task(execution.cancel_event.wait())
    try:
        done, _pending = await asyncio.wait(
            {provider_task, cancellation_task},
            timeout=execution.remaining_seconds,
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
        raise ProviderError(code, provider_id=provider_id)
    finally:
        cancellation_task.cancel()
        if not provider_task.done():
            provider_task.cancel()
        await asyncio.gather(provider_task, cancellation_task, return_exceptions=True)


def _parse_result(
    payload: Any,
    *,
    adapter_id: str,
    model_id: str,
    query: str,
    context: RequestContext,
    retrieved_at: datetime,
    max_results: int,
) -> LLMSearchResult:
    if not isinstance(payload, Mapping):
        raise ValueError("response must be an object")
    if payload.get("status") not in {"completed", "incomplete"}:
        raise ValueError("response status is invalid")
    if payload.get("model") != model_id:
        raise ValueError("served model does not match immutable adapter")
    output = payload.get("output")
    if not isinstance(output, list) or not any(
        isinstance(item, Mapping)
        and item.get("type") == "web_search_call"
        and item.get("status") == "completed"
        for item in output
    ):
        raise ValueError("response has no completed search receipt")

    items: list[SearchItem] = []
    evidence: list[EvidenceItem] = []
    seen_urls: set[str] = set()
    for annotation in _structured_annotations(output):
        if annotation.get("type") != "url_citation":
            continue
        title = annotation.get("title")
        url = annotation.get("url")
        if not isinstance(title, str) or not title.strip() or not isinstance(url, str):
            continue
        normalized_url = _public_url(url)
        if normalized_url is None or normalized_url in seen_urls:
            continue
        seen_urls.add(normalized_url)
        digest = hashlib.sha256(normalized_url.encode("utf-8")).hexdigest()
        item_id = f"url:{digest}"
        evidence_id = f"evidence:{digest}"
        summary = annotation.get("summary")
        snippet = summary.strip() if isinstance(summary, str) and summary.strip() else None
        provenance = Provenance(
            provider=adapter_id,
            attempt=1,
            outcome="success",
            retrieved_at=retrieved_at,
        )
        items.append(
            SearchItem(
                id=item_id,
                title=title.strip(),
                url=normalized_url,
                snippet=snippet,
                rank=len(items) + 1,
                provenance=(provenance,),
            )
        )
        evidence.append(
            EvidenceItem(
                id=evidence_id,
                item_id=item_id,
                provider=adapter_id,
                public_url=normalized_url,
                title_or_snippet=snippet or title.strip(),
                retrieved_at=retrieved_at,
            )
        )
        if len(items) >= max_results:
            break
    if not items:
        raise ValueError("response has no structured public evidence")

    usage = payload.get("usage")
    return LLMSearchResult(
        query=query,
        items=tuple(items),
        evidence=tuple(evidence),
        # RC2 never guesses or rewrites citations from answer text. The
        # structured evidence result remains useful without an answer.
        answer=None,
        meta=SearchMeta(requested=(adapter_id,), succeeded=(adapter_id,)),
        usage=Usage(
            input_tokens=_reported_usage(usage, "input_tokens"),
            output_tokens=_reported_usage(usage, "output_tokens"),
            cost=None,
            currency=None,
        ),
        context=context,
    )


def _structured_annotations(output: list[Any]) -> tuple[Mapping[str, Any], ...]:
    annotations: list[Mapping[str, Any]] = []
    for item in output:
        if not isinstance(item, Mapping) or item.get("status") not in {"completed", "incomplete"}:
            continue
        message = item.get("message")
        if not isinstance(message, Mapping):
            continue
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if not isinstance(part, Mapping):
                continue
            part_annotations = part.get("annotations")
            if isinstance(part_annotations, list):
                annotations.extend(
                    annotation for annotation in part_annotations if isinstance(annotation, Mapping)
                )
    return tuple(annotations)


def _public_url(value: str) -> str | None:
    parsed = urlsplit(value.strip())
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        return None
    host = parsed.hostname.rstrip(".").lower()
    if host == "localhost" or host.endswith(".localhost") or host.endswith(".local"):
        return None
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        if not address.is_global:
            return None
    port = parsed.port
    netloc = f"[{host}]" if ":" in host else host
    if port is not None and not (
        (parsed.scheme == "http" and port == 80) or (parsed.scheme == "https" and port == 443)
    ):
        netloc = f"{netloc}:{port}"
    return urlunsplit((parsed.scheme.lower(), netloc, parsed.path or "/", parsed.query, ""))


def _reported_usage(value: Any, field: str) -> int | None:
    if not isinstance(value, Mapping):
        return None
    candidate = value.get(field)
    if isinstance(candidate, int) and not isinstance(candidate, bool) and candidate >= 0:
        return candidate
    return None


__all__ = [
    "ArkTransportProtocol",
    "UniApiArkAnnotationsDeepSeekProvider",
    "UniApiArkAnnotationsDoubaoProvider",
]
