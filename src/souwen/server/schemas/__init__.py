"""Retained host-only schemas."""

from .admin import AdminConfigResponse, AdminPingResponse, DoctorResponse
from .common import ErrorResponse, WhoamiResponse

__all__ = [
    "AdminConfigResponse",
    "AdminPingResponse",
    "DoctorResponse",
    "ErrorResponse",
    "WhoamiResponse",
]
