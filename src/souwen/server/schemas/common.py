"""通用响应模型 — 健康/源/元信息/错误"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


SOURCE_CATEGORY_ORDER = (
    "paper",
    "patent",
    "web_general",
    "web_professional",
    "social",
    "office",
    "developer",
    "knowledge",
    "cn_tech",
    "video",
    "archive",
    "fetch",
)


class HealthResponse(BaseModel):
    """健康检查响应 — 用于容器编排系统探针"""

    status: str = Field(examples=["ok"])
    version: str = Field(examples=["0.4.0"])


class SourceCategoryInfo(BaseModel):
    """正式 Source Catalog 分类信息。"""

    key: str
    label: str
    order: int
    domain: str | None = None
    description: str = ""


class SourceCatalogItem(BaseModel):
    """正式 Source Catalog 单条数据源。"""

    name: str
    domain: str
    category: str
    capabilities: list[str] = Field(default_factory=list)
    description: str
    auth_requirement: Literal["none", "optional", "required", "self_hosted"]
    credential_fields: list[str] = Field(default_factory=list)
    credentials_satisfied: bool
    configured_credentials: bool
    risk_level: Literal["low", "medium", "high"]
    stability: Literal["stable", "beta", "experimental", "deprecated"]
    distribution: Literal["core", "extra", "plugin"]
    default_for: list[str] = Field(default_factory=list)
    available: bool


class SourceCatalogResponse(BaseModel):
    """正式 Source Catalog 响应。"""

    sources: list[SourceCatalogItem] = Field(default_factory=list)
    categories: list[SourceCategoryInfo] = Field(default_factory=list)
    defaults: dict[str, list[str]] = Field(default_factory=dict)


class SearchMeta(BaseModel):
    """搜索元信息 — 追踪哪些源成功/失败

    用于客户端了解查询结果的完整性，判断是否需要重试或切换数据源。

    Attributes:
        requested: 用户请求的数据源列表
        succeeded: 成功返回结果的数据源
        failed: 失败、超时或不可用的数据源
    """

    requested: list[str] = Field(description="请求的数据源列表")
    succeeded: list[str] = Field(description="成功返回结果的数据源")
    failed: list[str] = Field(description="失败或超时的数据源")


class ReadinessResponse(BaseModel):
    """Kubernetes readiness 探针响应 — 检查本地依赖可用性

    用于 K8s 确定 Pod 是否准备好接收流量。不执行网络调用，避免探针超时。
    """

    ready: bool
    version: str | None = None
    error: str | None = None


class ErrorResponse(BaseModel):
    """统一错误响应格式 — 所有 4xx/5xx 错误使用此结构

    便于客户端统一处理错误，仅根据 error 码而非状态码判断。
    request_id 用于日志系统追踪问题根源。
    """

    error: str = Field(description="机器可读错误码", examples=["not_found"])
    detail: str = Field(description="人类可读错误描述", examples=["未知数据源: foo"])
    request_id: str = Field(description="关联 ID，用于日志追踪", examples=["a1b2c3d4e5f6"])
