"""SouWen API 认证模块"""

from __future__ import annotations

import os
import secrets

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from souwen.config import get_config

_bearer_scheme = HTTPBearer(auto_error=False)


def _admin_open_override() -> bool:
    """``SOUWEN_ADMIN_OPEN=1`` 可显式解除默认的管理端锁定。"""
    return os.getenv("SOUWEN_ADMIN_OPEN", "").strip().lower() in ("1", "true", "yes", "on")


def require_auth(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> None:
    """要求 Bearer Token 认证。

    当 api_password 已配置时，请求必须携带 ``Authorization: Bearer <password>``。
    当 api_password 未配置时，默认拒绝访问；可通过 ``SOUWEN_ADMIN_OPEN=1`` 显式放行。
    """
    password = get_config().api_password
    if not password:
        if _admin_open_override():
            return
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=(
                "Admin API 未配置密码，拒绝访问；"
                "请设置 api_password 或 SOUWEN_ADMIN_OPEN=1 以显式放行。"
            ),
            headers={"WWW-Authenticate": "Bearer"},
        )
    if credentials is None or not secrets.compare_digest(credentials.credentials, password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="认证失败：无效的 Bearer Token",
            headers={"WWW-Authenticate": "Bearer"},
        )


def check_search_auth(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> None:
    """搜索端点的认证检查。

    当 api_password 已配置时，要求 Bearer Token；未配置时放行。
    """
    password = get_config().api_password
    if not password:
        return
    if credentials is None or not secrets.compare_digest(credentials.credentials, password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="认证失败：无效的 Bearer Token",
            headers={"WWW-Authenticate": "Bearer"},
        )
