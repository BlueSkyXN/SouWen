"""SouWen API 认证模块"""

from __future__ import annotations

import secrets

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from souwen.config import get_config

_bearer_scheme = HTTPBearer(auto_error=False)


def require_auth(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> None:
    """要求 Bearer Token 认证。

    当 api_password 已配置时，请求必须携带 ``Authorization: Bearer <password>``。
    当 api_password 未配置时，始终拒绝（管理端点不应在无密码时暴露）。
    """
    password = get_config().api_password
    if not password:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="管理端点需要先配置 api_password",
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
