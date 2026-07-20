"""GET /doctor — user-readable source status summary."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from souwen.server.auth import check_user_auth
from souwen.server.routes._doctor import build_doctor_payload
from souwen.server.schemas import DoctorResponse

router = APIRouter()


@router.get(
    "/doctor",
    response_model=DoctorResponse,
    dependencies=[Depends(check_user_auth)],
)
async def doctor_check(
    live: bool = Query(False, description="显式执行真实联网探测，默认只返回静态配置状态"),
    source: list[str] | None = Query(
        None,
        description="live=true 时只探测指定 source，可重复",
    ),
    timeout: float = Query(5.0, ge=0.5, le=60.0, description="单源 live probe 超时秒数"),
):
    """返回用户可读的数据源配置状态摘要。"""
    return await build_doctor_payload(live=live, sources=source, timeout=timeout)
