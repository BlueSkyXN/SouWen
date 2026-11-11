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


__all__ = ["check_target_user_auth"]
