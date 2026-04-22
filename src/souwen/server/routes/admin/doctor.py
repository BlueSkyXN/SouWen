"""数据源健康检查与轻量 ping — /admin/doctor、/admin/ping"""

from __future__ import annotations

from fastapi import APIRouter

from souwen.server.schemas import DoctorResponse

router = APIRouter()


@router.get("/doctor", response_model=DoctorResponse)
async def doctor_check():
    """数据源健康检查 — 测试所有数据源连接性。"""
    from souwen.doctor import check_all

    results = check_all()
    ok_count = sum(1 for r in results if r["status"] == "ok")
    return {
        "total": len(results),
        "ok": ok_count,
        "sources": results,
    }


@router.get("/ping")
async def admin_ping():
    """轻量级管理端存活探测 — 完全通过认证后返回。"""
    return {"status": "ok"}
