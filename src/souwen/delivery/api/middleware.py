"""Target request correlation and API-major response headers."""

from __future__ import annotations

import re
from uuid import uuid4

from souwen.common_runtime.observability import get_request_id, request_id_var

_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_TARGET_CONTRACT_PATHS = frozenset(
    {
        "/api/v1/search",
        "/api/v1/llm-search",
        "/api/v1/fetch",
        "/api/v1/providers",
        "/health",
        "/healthz",
        "/readiness",
        "/readyz",
    }
)


def is_target_contract_path(path: str) -> bool:
    return path in _TARGET_CONTRACT_PATHS


def _request_id(scope: dict) -> str:
    headers = dict(scope.get("headers", ()))
    try:
        raw = headers.get(b"x-request-id", b"").decode("ascii")
    except UnicodeDecodeError:
        raw = ""
    return raw if _VALID_REQUEST_ID.fullmatch(raw) else uuid4().hex[:12]


def _with_contract_headers(message: dict, request_id: str) -> dict:
    existing = [
        (name, value)
        for name, value in message.get("headers", ())
        if name.lower() not in {b"x-request-id", b"x-souwen-api-major", b"x-souwen-rollout-mode"}
    ]
    return {
        **message,
        "headers": [
            *existing,
            (b"x-request-id", request_id.encode("ascii")),
            (b"x-souwen-api-major", b"2"),
            (b"x-souwen-rollout-mode", b"target"),
        ],
    }


class TargetRequestContextMiddleware:
    """Full request context for a standalone target Delivery application."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request_id = _request_id(scope)
        token = request_id_var.set(request_id)

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                message = _with_contract_headers(message, request_id)
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            request_id_var.reset(token)


class TargetContractHeadersMiddleware:
    """Add target headers when the host app owns request correlation."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http" or not is_target_contract_path(scope.get("path", "")):
            await self.app(scope, receive, send)
            return

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                message = _with_contract_headers(message, get_request_id())
            await send(message)

        await self.app(scope, receive, send_wrapper)


__all__ = [
    "TargetContractHeadersMiddleware",
    "TargetRequestContextMiddleware",
    "is_target_contract_path",
]
