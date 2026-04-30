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
    import logging

    from souwen.plugin import get_loaded_plugins

    plugin = get_loaded_plugins().get(name)
    if plugin is None:
        raise HTTPException(status_code=404, detail=f"插件 {name!r} 未加载")
    if plugin.health_check is None:
        return {"status": "ok", "message": "no health check defined"}
    try:
        result = plugin.health_check()
        if inspect.isawaitable(result):
            result = await result
        return result
    except Exception as exc:
        logging.getLogger("souwen.server").warning(
            "插件 %r 健康检查失败: %s", name, exc, exc_info=True
        )
        return {"status": "error", "message": f"插件 {name!r} 健康检查异常"}


@router.post("/plugins/{name}/enable")
async def enable(name: str):
    """启用插件（重启后生效）"""
    from souwen.plugin_manager import enable_plugin

    return enable_plugin(name)


@router.post("/plugins/{name}/disable")
async def disable(name: str):
    """禁用插件（重启后生效）"""
    from souwen.plugin_manager import disable_plugin_async

    result = await disable_plugin_async(name)
    return {
        "success": result.get("success", False),
        "restart_required": result.get("restart_required", False),
        "message": result.get("message", ""),
    }


@router.post("/plugins/install")
async def install(req: InstallRequest):
    """安装插件包（需 SOUWEN_ENABLE_PLUGIN_INSTALL=1）"""
    from souwen.plugin_manager import install_plugin

    result = await install_plugin(req.package)
    return _sanitize_pip_result(result, package=req.package)


@router.post("/plugins/uninstall")
async def uninstall(req: UninstallRequest):
    """卸载插件包（需 SOUWEN_ENABLE_PLUGIN_INSTALL=1）"""
    from souwen.plugin_manager import uninstall_plugin

    result = await uninstall_plugin(req.package)
    return _sanitize_pip_result(result, package=req.package)


def _sanitize_pip_result(result: dict, package: str = "") -> dict:
    """Strip raw pip output from install/uninstall result before API response."""
    import logging

    if not result.get("success"):
        logging.getLogger("souwen.server").warning(
            "pip 操作失败，原始输出: %s", result.get("output", "")
        )
    return {
        "success": result.get("success", False),
        "package": result.get("package", package),
        "restart_required": result.get("restart_required", False),
        "message": "操作成功" if result.get("success") else "操作失败，详见服务端日志",
    }


def _sanitize_errors(errors: list[dict]) -> list[dict]:
    """Strip exception details from plugin error dicts before API response."""
    return [{"source": e.get("source", ""), "name": e.get("name", "")} for e in errors]


@router.post("/plugins/reload")
async def reload():
    """重新扫描 entry point 插件（追加模式）"""
    from souwen.plugin_manager import reload_plugins

    result = reload_plugins()
    return {
        "loaded": result.get("loaded", []),
        "errors": _sanitize_errors(result.get("errors", [])),
        "message": result.get("message", ""),
    }
