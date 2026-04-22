"""角色自检端点 — /whoami"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from souwen.config import get_config
from souwen.server.auth import Role, resolve_role

router = APIRouter()


@router.get("/whoami")
async def whoami(role: Role = Depends(resolve_role)):
    """返回当前请求的角色和可用功能

    根据 Bearer Token 判定角色后，返回该角色可用的功能列表。
    用于前端面板根据角色动态渲染 UI。
    """
    cfg = get_config()
    features = {
        "search": True,
        "raw_search": role >= Role.USER,
        "fetch": role >= Role.ADMIN,
        "wayback_save": role >= Role.ADMIN,
        "config_read": (
            "full" if role >= Role.ADMIN
            else "minimal" if role >= Role.USER
            else False
        ),
        "config_write": role >= Role.ADMIN,
        "sources_config_read": role >= Role.USER,
        "sources_config_write": role >= Role.ADMIN,
        "proxy_admin": role >= Role.ADMIN,
        "warp_admin": role >= Role.ADMIN,
        "doctor": role >= Role.USER,
        "doctor_full": role >= Role.ADMIN,
    }

    return {
        "role": role.name.lower(),
        "features": features,
        "guest_enabled": cfg.guest_enabled,
    }
