"""管理端配置查看与重载 — /admin/config、/admin/config/reload"""

from __future__ import annotations

from fastapi import APIRouter

from souwen.server.routes._common import _is_secret_field
from souwen.server.schemas import ConfigReloadResponse

router = APIRouter()


@router.get("/config")
async def get_config_view():
    """查看当前配置（敏感字段脱敏）— 管理端点。"""
    from souwen.config import SouWenConfig, get_config

    cfg = get_config()
    result = {}
    for field_name in SouWenConfig.model_fields:
        val = getattr(cfg, field_name)
        if _is_secret_field(field_name) and val is not None:
            result[field_name] = "***"
        else:
            result[field_name] = val
    return result


@router.post("/config/reload", response_model=ConfigReloadResponse)
async def reload_config_endpoint():
    """重新加载配置 — 从 YAML + .env 重新读取。"""
    from souwen.config import reload_config

    cfg = reload_config()
    return {
        "status": "ok",
        "password_set": cfg.effective_admin_password is not None,
    }
