"""Small host-only response models outside the generated target API."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class WhoamiResponse(BaseModel):
    role: Literal["guest", "user", "admin"]
    features: dict[str, bool | str] = Field(default_factory=dict)
    guest_enabled: bool
    user_password_set: bool
    admin_password_set: bool
    admin_open: bool


class ErrorResponse(BaseModel):
    error: str
    detail: str
    request_id: str


__all__ = ["ErrorResponse", "WhoamiResponse"]
