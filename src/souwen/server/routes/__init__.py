"""Retained non-target host routes."""

from __future__ import annotations

from fastapi import APIRouter

from souwen.server.routes.admin import admin_router
from souwen.server.routes.whoami import router as whoami_router

router = APIRouter()

router.include_router(whoami_router)

__all__ = ["router", "admin_router"]
