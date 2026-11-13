"""SouWen 服务端认证

提供 Bearer Token 认证（user 凭据校验）。
上游代理占用 Authorization 头时，也接受 X-SouWen-Token 作为应用层凭据。

说明:
    - 认证基于 ``server.user_password``（环境变量 ``SOUWEN_USER_PASSWORD``）。
    - 未配置用户密码时 Data API 保持开放；一旦配置，所有请求必须携带有效 Token。
    - 三级角色（Guest/User/Admin）与管理端点已在 agent-first 线移除；
      本模块只保留 user 凭据校验，且校验行为与移除前的 user 路径一致。
"""

from __future__ import annotations

import logging
import secrets

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from souwen.config import get_config

logger = logging.getLogger("souwen.server")

_bearer_scheme = HTTPBearer(auto_error=False)


def _resolve_auth_credentials(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    souwen_token: str | None = Header(default=None, alias="X-SouWen-Token"),
) -> HTTPAuthorizationCredentials | None:
    """Resolve the application credential independently from an upstream proxy token.

    Private Hugging Face Spaces consume ``Authorization`` for the outer access
    boundary. ``X-SouWen-Token`` keeps SouWen's user credential separate.
    The custom header takes precedence when both headers are present; an invalid
    explicit application token must not fall back to another credential.
    """

    token = (souwen_token or "").strip()
    if token:
        return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    return credentials


def check_target_user_auth(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    souwen_token: str | None = Header(default=None, alias="X-SouWen-Token"),
) -> None:
    """Fail closed for target Data APIs unless open access is explicit."""
    cfg = get_config()
    custom_header_present = souwen_token is not None
    authorization_present = "authorization" in request.headers
    token = (
        (souwen_token or "").strip()
        if custom_header_present
        else (credentials.credentials if credentials else "")
    )
    user_password = cfg.effective_user_password or ""
    is_user = bool(user_password) and secrets.compare_digest(token, user_password)
    if is_user:
        return
    if custom_header_present or authorization_present:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="target Data API credential is invalid",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if cfg.user_password == "":
        return
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="target Data API requires an explicit user credential",
        headers={"WWW-Authenticate": "Bearer"},
    )


__all__ = ["McpAuthMiddleware", "check_target_user_auth"]


class McpAuthMiddleware:
    """Apply the same user-credential check to the mounted MCP ASGI app.

    The FastMCP streamable-HTTP app is mounted as a raw ASGI sub-app, so
    FastAPI dependencies cannot protect it. This pure ASGI middleware runs
    the identical fail-closed logic as ``check_target_user_auth`` for the
    ``/mcp`` path (Bearer token or ``X-SouWen-Token``).
    """

    _MCP_PATH = "/mcp"

    def __init__(self, app):  # ASGI app
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http" or scope.get("path") != self._MCP_PATH:
            await self.app(scope, receive, send)
            return
        headers = {
            key.decode("latin-1").lower(): value.decode("latin-1")
            for key, value in scope.get("headers", [])
        }
        cfg = get_config()
        custom_header_present = "x-souwen-token" in headers
        authorization_present = "authorization" in headers
        if custom_header_present:
            token = headers["x-souwen-token"].strip()
        else:
            scheme, separator, value = headers.get("authorization", "").partition(" ")
            token = value.strip() if separator and scheme.lower() == "bearer" else ""
        user_password = cfg.effective_user_password or ""
        valid = bool(user_password) and secrets.compare_digest(token, user_password)
        if valid:
            await self.app(scope, receive, send)
            return
        if not (custom_header_present or authorization_present) and cfg.user_password == "":
            await self.app(scope, receive, send)
            return
        await _send_unauthorized(send)


async def _send_unauthorized(send) -> None:
    body = b'{"error":"unauthorized","detail":"MCP endpoint requires a valid user credential"}'
    await send(
        {
            "type": "http.response.start",
            "status": 401,
            "headers": [
                (b"content-type", b"application/json"),
                (b"www-authenticate", b"Bearer"),
                (b"content-length", str(len(body)).encode("latin-1")),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})
