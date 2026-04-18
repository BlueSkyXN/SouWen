"""SouWen API 双密钥认证模块

文件用途：
    提供 Bearer Token 认证和授权检查，保护搜索端点和管理端点。
    支持独立的访客密码（visitor_password）和管理密码（admin_password），
    并向后兼容旧版统一密码（api_password）。

密码解析优先级：
    - 访客端点：visitor_password > api_password > 无密码（开放）
    - 管理端点：admin_password > api_password > 无密码（开放）
    - 管理密码同时可用于访客端点（admin 是 visitor 的超集）

主要函数：
    require_auth(credentials) -> None
        - 功能：强制认证依赖 — 用于 /api/v1/admin/* 管理端点
        - 使用 effective_admin_password 验证

    check_search_auth(credentials) -> None
        - 功能：搜索端点认证检查
        - 使用 effective_visitor_password 验证
        - 同时接受管理密码（admin 是超集）

认证流程：
    - 请求头格式：Authorization: Bearer <password>
    - HTTP 方案：HTTPBearer (auto_error=False)
    - 密码未配置时默认开放访问
"""

from __future__ import annotations

import logging
import secrets

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from souwen.config import get_config

logger = logging.getLogger("souwen.server")

_bearer_scheme = HTTPBearer(auto_error=False)


def require_auth(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> None:
    """强制认证依赖 — 用于 /api/v1/admin/* 管理端点

    认证规则：
        1. 若 effective_admin_password 未配置 → 放行（开放访问）
        2. 若已配置 → 验证 Bearer Token（恒定时间比较防时序攻击）

    Args:
        credentials: 从请求头 Authorization: Bearer <token> 提取的凭证

    Raises:
        HTTPException：401 Unauthorized
    """
    password = get_config().effective_admin_password
    if not password:
        return
    if credentials is None or not secrets.compare_digest(credentials.credentials, password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="认证失败：无效的管理端 Bearer Token",
            headers={"WWW-Authenticate": "Bearer"},
        )


def check_search_auth(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> None:
    """搜索端点认证检查 — 同时接受访客密码和管理密码

    认证规则：
        1. 若 effective_visitor_password 未配置 → 放行
        2. 若已配置 → 验证 Bearer Token（同时接受管理密码）

    Args:
        credentials: 从请求头 Authorization: Bearer <token> 提取的凭证

    Raises:
        HTTPException：401 Unauthorized（仅当密码已配置但验证失败）
    """
    cfg = get_config()
    visitor_pw = cfg.effective_visitor_password
    if not visitor_pw:
        return
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="认证失败：无效的 Bearer Token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = credentials.credentials
    # Always execute both comparisons to prevent timing side-channel leaks
    visitor_ok = secrets.compare_digest(token, visitor_pw)
    admin_pw = cfg.effective_admin_password or ""
    admin_ok = secrets.compare_digest(token, admin_pw) if admin_pw else False
    if visitor_ok or admin_ok:
        return
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="认证失败：无效的 Bearer Token",
        headers={"WWW-Authenticate": "Bearer"},
    )
