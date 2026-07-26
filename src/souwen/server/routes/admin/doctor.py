"""Read-only Provider v2 status and authenticated ping routes."""

from __future__ import annotations

from fastapi import APIRouter, Request

from souwen.server.schemas import AdminPingResponse, DoctorResponse

router = APIRouter()


@router.get("/doctor", response_model=DoctorResponse)
async def doctor_check(request: Request):
    """Return the same safe Provider v2 eligibility projected by the target runtime."""

    items = request.app.state.target_runtime.services.provider_items
    providers = [
        {
            "provider": item.provider,
            "capabilities": list(item.capabilities),
            "availability": item.availability,
            "reason": item.reason,
            "missing_fields": list(item.missing_fields),
        }
        for item in items
    ]
    available = sum(item["availability"] == "available" for item in providers)
    return {
        "total": len(providers),
        "available": available,
        "unavailable": len(providers) - available,
        "providers": providers,
    }


@router.get("/ping", response_model=AdminPingResponse)
async def admin_ping():
    """轻量级管理端存活探测 — 完全通过认证后返回。"""
    return {"status": "ok"}
