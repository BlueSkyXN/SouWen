"""SouWen API 三级角色认证模块

文件用途：
    提供 Bearer Token 认证和三级角色（Guest/User/Admin）授权检查。
    支持独立的用户密码（user_password）和管理密码（admin_password）。

角色层级（Admin ⊃ User ⊃ Guest）：
    - Guest 游客：无 Token 即可访问搜索端点（受限源、限速）
    - User 用户：提供 user_password，可访问搜索 + /sources
    - Admin 管理员：提供 admin_password，拥有全部权限

密码解析规则：
    - Search 端点：未设置 user_password 时开放；设置后要求 User+，guest_enabled 可放行 Guest 搜索
    - User 端点：未设置 user_password 且未启用 guest_enabled 时开放；否则要求 User+
    - Admin 端点：admin_password > 无密码（需 SOUWEN_ADMIN_OPEN=1 显式开放）
    - Admin Token 自动满足 User/Guest 端点

主要接口：
    Role（枚举）：GUEST=0, USER=1, ADMIN=2

    resolve_role(credentials) -> Role
        - 根据 Bearer Token 判定角色
        - 始终执行恒定时间比较防时序攻击

    require_role(min_role) -> Depends
        - 工厂函数，生成 FastAPI 依赖
        - 低于 min_role 抛 401/403

    require_auth / check_user_auth / check_search_auth
        - 路由级认证依赖
"""

from __future__ import annotations

import enum
import logging
import os
import secrets

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from souwen.config import get_config

logger = logging.getLogger("souwen.server")

_bearer_scheme = HTTPBearer(auto_error=False)
_ADMIN_OPEN_VALUES = {"1", "true", "yes", "on"}


def is_admin_open_enabled() -> bool:
    """是否显式开放无密码 admin 端点。"""
    return os.getenv("SOUWEN_ADMIN_OPEN", "").strip().lower() in _ADMIN_OPEN_VALUES


class Role(enum.IntEnum):
    """三级角色枚举，数值越大权限越高"""

    GUEST = 0
    USER = 1
    ADMIN = 2


def resolve_role(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> Role:
    """根据 Bearer Token 判定角色

    三密码始终执行 compare_digest（哪怕未配置用空串占位），消除时序差异。

    Returns:
        Role.ADMIN / Role.USER / Role.GUEST

    Raises:
        HTTPException 401: guest_enabled=False 且无有效 Token
    """
    cfg = get_config()
    admin_pw = cfg.effective_admin_password or ""
    user_pw = cfg.effective_user_password or ""
    token = credentials.credentials if credentials else ""

    # 恒定时间比较 — 始终执行三次，消除时序旁路
    is_admin = bool(admin_pw) and secrets.compare_digest(token, admin_pw)
    is_user = bool(user_pw) and secrets.compare_digest(token, user_pw)
    # 如果 admin_pw == user_pw，admin token 也应算 user
    # （已由 is_admin 覆盖，因为 admin ⊃ user）

    if is_admin:
        return Role.ADMIN
    if is_user:
        return Role.USER

    if not admin_pw and is_admin_open_enabled():
        return Role.ADMIN
    if cfg.guest_enabled:
        return Role.GUEST
    if not user_pw:
        return Role.USER

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="认证失败：需要有效的 Bearer Token",
        headers={"WWW-Authenticate": "Bearer"},
    )


def require_role(min_role: Role):
    """工厂函数：生成要求最低角色的 FastAPI 依赖

    用法::

        @router.get("/sources", dependencies=[Depends(require_role(Role.GUEST))])
        def list_sources(role: Role = Depends(resolve_role)): ...

    Args:
        min_role: 端点要求的最低角色

    Returns:
        FastAPI Depends 依赖函数
    """

    def _check(role: Role = Depends(resolve_role)) -> Role:
        if role < min_role:
            if role == Role.GUEST:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="认证失败：此端点需要用户或管理员权限",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="权限不足：此端点需要管理员权限",
            )
        return role

    return Depends(_check)


# ===== 路由级认证依赖 =====


def require_auth(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> None:
    """管理端点认证

    行为：
    - 若管理密码未配置，必须设置 SOUWEN_ADMIN_OPEN=1 才显式放行
    - 否则要求 ADMIN 角色；有效但权限不足的 USER 返回 403
    """
    cfg = get_config()
    if not cfg.effective_admin_password:
        if is_admin_open_enabled():
            return
        if credentials and cfg.effective_user_password:
            role = resolve_role(credentials)
            if role >= Role.USER:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="权限不足：此端点需要管理员权限",
                )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="认证失败：管理端未配置密码，需设置 SOUWEN_ADMIN_OPEN=1 才允许无密码访问",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = credentials.credentials if credentials else ""
    admin_pw = cfg.effective_admin_password or ""
    user_pw = cfg.effective_user_password or ""
    is_admin = bool(admin_pw) and secrets.compare_digest(token, admin_pw)
    is_user = bool(user_pw) and secrets.compare_digest(token, user_pw)
    if is_admin:
        return
    if is_user:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="权限不足：此端点需要管理员权限",
        )
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="认证失败：无效的管理端 Bearer Token",
        headers={"WWW-Authenticate": "Bearer"},
    )


def check_user_auth(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> None:
    """用户端点认证

    行为：
    - 若用户密码未配置且未启用 guest 模式 → 放行（本地默认开放）
    - 若启用 guest 模式 → 无 Token 只得到 Guest，不能访问 User 端点
    - 否则要求 USER+ 角色
    """
    cfg = get_config()
    if not cfg.effective_user_password and not cfg.guest_enabled:
        return
    role = resolve_role(credentials)
    if role < Role.USER:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="认证失败：此端点需要用户或管理员权限",
            headers={"WWW-Authenticate": "Bearer"},
        )


def check_search_auth(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> None:
    """搜索端点认证

    行为：
    - 若搜索密码未配置（effective_user_password 为 None）→ 放行
    - 若启用 guest 模式 → 无 Token 可以按 Guest 搜索
    - 否则要求 USER+ 角色
    """
    cfg = get_config()
    if not cfg.effective_user_password:
        return  # 搜索密码未配置 → 搜索端点开放
    role = resolve_role(credentials)
    if role < Role.USER and not cfg.guest_enabled:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="认证失败：需要有效的 Bearer Token",
            headers={"WWW-Authenticate": "Bearer"},
        )
