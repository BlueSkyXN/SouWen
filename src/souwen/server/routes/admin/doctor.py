"""数据源健康检查与轻量 ping — /admin/doctor、/admin/ping"""

from __future__ import annotations

from fastapi import APIRouter, Query

from souwen.server.routes._doctor import build_doctor_payload
from souwen.server.schemas import AdminPingResponse, DoctorResponse

router = APIRouter()


@router.get("/doctor", response_model=DoctorResponse)
async def doctor_check(
    live: bool = Query(False, description="显式执行真实联网探测，默认只返回静态配置状态"),
    source: list[str] | None = Query(
        None,
        description="live=true 时只探测指定 source，可重复",
    ),
    timeout: float = Query(5.0, ge=0.5, le=60.0, description="单源 live probe 超时秒数"),
):
    """数据源健康检查 — 测试所有数据源连接性。"""
    return await build_doctor_payload(live=live, sources=source, timeout=timeout)


@router.get("/ping", response_model=AdminPingResponse)
async def admin_ping():
    """轻量级管理端存活探测 — 完全通过认证后返回。"""
    return {"status": "ok"}
