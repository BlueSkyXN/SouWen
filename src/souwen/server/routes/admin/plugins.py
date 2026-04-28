"""GET/POST /admin/plugins — 插件管理 API"""

from __future__ import annotations

import inspect

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()


class InstallRequest(BaseModel):
    package: str


class UninstallRequest(BaseModel):
    package: str


@router.get("/plugins")
async def list_all_plugins():
    """列出所有插件（已加载 + 目录 + 禁用）"""
    from souwen.plugin_manager import is_restart_required, list_plugins

    plugins = list_plugins()
    return {
        "plugins": [p.model_dump() for p in plugins],
        "restart_required": is_restart_required(),
    }


@router.get("/plugins/{name}")
async def get_plugin(name: str):
    """查询单个插件详情"""
    from souwen.plugin_manager import get_plugin_info

    info = get_plugin_info(name)
    if info is None:
        raise HTTPException(status_code=404, detail=f"插件 {name!r} 未找到")
    return info.model_dump()


@router.get("/plugins/{name}/health")
async def plugin_health(name: str):
    """运行单个已加载插件的健康检查。"""
    from souwen.plugin import get_loaded_plugins

    plugin = get_loaded_plugins().get(name)
    if plugin is None:
        raise HTTPException(status_code=404, detail=f"插件 {name!r} 未加载")
    if plugin.health_check is None:
        return {"status": "ok", "message": "no health check defined"}
    result = plugin.health_check()
    if inspect.isawaitable(result):
        result = await result
    return result


@router.post("/plugins/{name}/enable")
async def enable(name: str):
    """启用插件（重启后生效）"""
    from souwen.plugin_manager import enable_plugin

    return enable_plugin(name)


@router.post("/plugins/{name}/disable")
async def disable(name: str):
    """禁用插件（重启后生效）"""
    from souwen.plugin_manager import disable_plugin

    return disable_plugin(name)


@router.post("/plugins/install")
async def install(req: InstallRequest):
    """安装插件包（需 SOUWEN_ENABLE_PLUGIN_INSTALL=1）"""
    from souwen.plugin_manager import install_plugin

    return await install_plugin(req.package)


@router.post("/plugins/uninstall")
async def uninstall(req: UninstallRequest):
    """卸载插件包（需 SOUWEN_ENABLE_PLUGIN_INSTALL=1）"""
    from souwen.plugin_manager import uninstall_plugin

    return await uninstall_plugin(req.package)


@router.post("/plugins/reload")
async def reload():
    """重新扫描 entry point 插件（追加模式）"""
    from souwen.plugin_manager import reload_plugins

    return reload_plugins()
