"""管理子路由聚合 — 暴露统一的 ``admin_router``

每个子模块自带的 ``router`` 在此处合并到一个 ``admin_router``。
本聚合路由会被父级 ``routes/__init__.py`` 引用并附加 ``require_auth``
依赖（在父级声明，避免在每个子模块重复）。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from souwen.server.auth import require_auth
from souwen.server.routes.admin.config import router as config_router
from souwen.server.routes.admin.doctor import router as doctor_router
from souwen.server.routes.admin.http_backend import router as http_backend_router
from souwen.server.routes.admin.proxy import router as proxy_router
from souwen.server.routes.admin.sources import router as sources_router
from souwen.server.routes.admin.warp import router as warp_router
from souwen.server.routes.admin.wayback import router as wayback_router

admin_router = APIRouter(dependencies=[Depends(require_auth)])

admin_router.include_router(config_router)
admin_router.include_router(doctor_router)
admin_router.include_router(sources_router)
admin_router.include_router(proxy_router)
admin_router.include_router(http_backend_router)
admin_router.include_router(warp_router)
admin_router.include_router(wayback_router)

__all__ = ["admin_router"]
