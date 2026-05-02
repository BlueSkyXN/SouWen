"""通用响应模型 — 健康/源/元信息/错误"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """健康检查响应 — 用于容器编排系统探针"""

    status: str = Field(examples=["ok"])
    version: str = Field(examples=["0.4.0"])


class SourceInfo(BaseModel):
    """数据源信息卡片

    Attributes:
        name: 数据源名称（如 "openalex"）
        needs_key: 是否需要 API Key 才能使用
        key_requirement/auth_requirement: none / optional / required / self_hosted
        description: 对数据源的描述
    """

    name: str
    needs_key: bool
    description: str
    key_requirement: Literal["none", "optional", "required", "self_hosted"] = "none"
    auth_requirement: Literal["none", "optional", "required", "self_hosted"] = "none"
    credential_fields: list[str] = Field(default_factory=list)
    optional_credential_effect: str | None = None
    integration_type: str | None = None
    risk_level: Literal["low", "medium", "high"] = "low"
    risk_reasons: list[str] = Field(default_factory=list)
    distribution: Literal["core", "extra", "plugin"] = "core"
    package_extra: str | None = None
    stability: Literal["stable", "beta", "experimental", "deprecated"] = "stable"
    default_enabled: bool = True


class SourcesResponse(BaseModel):
    """数据源列表响应 — 按类别分组

    与 souwen.models.ALL_SOURCES 的 11 个分类一一对应，/sources 端点
    会按类别返回当前可用（凭据满足）的数据源列表。
    """

    paper: list[SourceInfo] = Field(default_factory=list)
    patent: list[SourceInfo] = Field(default_factory=list)
    general: list[SourceInfo] = Field(default_factory=list)
    professional: list[SourceInfo] = Field(default_factory=list)
    social: list[SourceInfo] = Field(default_factory=list)
    developer: list[SourceInfo] = Field(default_factory=list)
    wiki: list[SourceInfo] = Field(default_factory=list)
    video: list[SourceInfo] = Field(default_factory=list)
    fetch: list[SourceInfo] = Field(default_factory=list)
    cn_tech: list[SourceInfo] = Field(default_factory=list)
    office: list[SourceInfo] = Field(default_factory=list)


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
