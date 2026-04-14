"""API 响应模型"""

from __future__ import annotations

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = Field(examples=["ok"])
    version: str = Field(examples=["0.3.0"])


class SourceInfo(BaseModel):
    name: str
    needs_key: bool
    description: str


class SourcesResponse(BaseModel):
    paper: list[SourceInfo] = []
    patent: list[SourceInfo] = []
    web: list[SourceInfo] = []


class SearchPaperResponse(BaseModel):
    query: str
    sources: list[str]
    results: list[dict]
    total: int


class SearchPatentResponse(BaseModel):
    query: str
    sources: list[str]
    results: list[dict]
    total: int


class ConfigReloadResponse(BaseModel):
    status: str = Field(examples=["ok"])
    password_set: bool


class DoctorResponse(BaseModel):
    total: int
    ok: int
    sources: list[dict]


class HttpBackendResponse(BaseModel):
    default: str = Field(examples=["auto"])
    overrides: dict[str, str] = Field(default_factory=dict)
    curl_cffi_available: bool
