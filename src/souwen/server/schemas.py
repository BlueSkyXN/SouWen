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


class SearchMeta(BaseModel):
    """搜索元信息 — 追踪哪些源成功/失败"""
    requested: list[str] = Field(description="请求的数据源列表")
    succeeded: list[str] = Field(description="成功返回结果的数据源")
    failed: list[str] = Field(description="失败或超时的数据源")


class SearchPaperResponse(BaseModel):
    query: str
    sources: list[str]
    results: list[dict]
    total: int
    meta: SearchMeta = Field(default_factory=lambda: SearchMeta(requested=[], succeeded=[], failed=[]))


class SearchPatentResponse(BaseModel):
    query: str
    sources: list[str]
    results: list[dict]
    total: int
    meta: SearchMeta = Field(default_factory=lambda: SearchMeta(requested=[], succeeded=[], failed=[]))


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


class UpdateSourceConfigRequest(BaseModel):
    """更新数据源频道配置的请求体（避免敏感信息出现在 URL 中）"""
    enabled: bool | None = None
    proxy: str | None = None
    http_backend: str | None = None
    base_url: str | None = None
    api_key: str | None = None


class ErrorResponse(BaseModel):
    """统一错误响应格式

    所有 4xx/5xx 响应均使用此结构，便于客户端统一处理。
    """
    error: str = Field(description="机器可读错误码", examples=["not_found"])
    detail: str = Field(description="人类可读错误描述", examples=["未知数据源: foo"])
    request_id: str = Field(description="关联 ID，用于日志追踪", examples=["a1b2c3d4e5f6"])
