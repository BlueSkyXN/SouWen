"""Small host-only response models outside the target API."""

from __future__ import annotations

from pydantic import BaseModel


class ErrorResponse(BaseModel):
    error: str
    detail: str
    request_id: str


__all__ = ["ErrorResponse"]
