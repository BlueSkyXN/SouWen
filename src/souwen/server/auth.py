"""SouWen API 认证模块

文件用途：
    提供 Bearer Token 认证和授权检查，保护搜索端点和管理端点。

主要函数：
    _admin_open_override() -> bool
        - 功能：检查是否通过环境变量显式解除管理端锁定
        - 读取：SOUWEN_ADMIN_OPEN 环境变量
        - 返回：True 当值为 "1"、"true"、"yes"、"on"（不区分大小写）

    require_auth(credentials: HTTPAuthorizationCredentials | None) -> None
        - 功能：强制认证依赖 — 用于 /api/v1/admin/* 管理端点
        - 逻辑：
            1. 若 api_password 未配置，则拒绝访问（除非 SOUWEN_ADMIN_OPEN=1）
            2. 若已配置，检查 Bearer Token 是否与密码匹配（恒定时间比较）
        - 异常：HTTPException 401（未认证或认证失败）
        - 安全细节：使用 secrets.compare_digest 防止时序攻击

    check_search_auth(credentials: HTTPAuthorizationCredentials | None) -> None
        - 功能：搜索端点认证检查 — 宽松模式
        - 逻辑：
            1. 若 api_password 未配置，放行所有请求
            2. 若已配置，要求有效的 Bearer Token
        - 异常：HTTPException 401（已配置密码但认证失败）

认证流程：
    - 请求头格式：Authorization: Bearer <api_password>
    - HTTP 方案：HTTPBearer (auto_error=False，不自动抛异常，交由依赖函数处理)
    - WWW-Authenticate 响应头：提示客户端支持 Bearer 认证

模块依赖：
    - fastapi：FastAPI 框架和依赖注入
    - souwen.config：读取 api_password 配置
"""

from __future__ import annotations

import os
import secrets

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from souwen.config import get_config

_bearer_scheme = HTTPBearer(auto_error=False)


def _admin_open_override() -> bool:
    """检查是否通过环境变量显式解除管理端锁定
    
    当 SOUWEN_ADMIN_OPEN 环境变量为 "1"、"true"、"yes" 或 "on" 时返回 True。
    用于开发/演示环境临时绕过密码要求。
    
    Returns:
        True 当环境变量启用（不区分大小写），False 否则
    """
    return os.getenv("SOUWEN_ADMIN_OPEN", "").strip().lower() in ("1", "true", "yes", "on")


def require_auth(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> None:
    """强制认证依赖 — 用于 /api/v1/admin/* 管理端点
    
    认证规则：
        1. 若 api_password 未配置，除非 SOUWEN_ADMIN_OPEN=1，否则拒绝访问
        2. 若已配置，检查 Bearer Token 是否匹配密码（恒定时间比较防时序攻击）
        3. 失败时返回 401 Unauthorized 并带 WWW-Authenticate 头
    
    Args:
        credentials: 从请求头 Authorization: Bearer <token> 提取的凭证
        
    Raises:
        HTTPException：401 Unauthorized
    
    Security:
        - 使用 secrets.compare_digest 进行恒定时间的密码比较
        - 防止时序攻击（timing attack）泄露密码
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
    """搜索端点认证检查 — 宽松模式（密码未配置时放行）
    
    认证规则（对比 require_auth 的严格模式）：
        1. 若 api_password 未配置，放行所有搜索请求
        2. 若已配置，要求提供有效的 Bearer Token
        3. 失败时返回 401 Unauthorized
    
    Args:
        credentials: 从请求头 Authorization: Bearer <token> 提取的凭证
        
    Raises:
        HTTPException：401 Unauthorized（仅当密码已配置但验证失败）
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
