"""API 响应模型 — 使用 Pydantic BaseModel 定义

文件用途：
    定义所有 API 端点的请求和响应模型。
    使用 Pydantic 进行数据验证、序列化和 OpenAPI 文档生成。

主要类：
    HealthResponse
        - 应答：/health 端点
        - 字段：status, version

    SourceInfo
        - 单个数据源信息（名称、是否需要 API Key、描述）

    SourcesResponse
        - 应答：/sources 端点
        - 按类别分组：paper, patent, web

    SearchMeta
        - 搜索元信息，追踪哪些源成功/失败
        - 字段：requested（请求的源）、succeeded（成功的源）、failed（失败的源）

    SearchPaperResponse、SearchPatentResponse、SearchWebResponse
        - 论文、专利、网页搜索响应
        - 通用结构：query, results, total, meta

    ReadinessResponse
        - Kubernetes readiness 探针响应
        - 字段：ready, version, error

    ConfigReloadResponse
        - 配置重载端点响应

    DoctorResponse
        - 健康检查响应（汇总统计）

    HttpBackendResponse
        - HTTP 后端配置查询响应

    UpdateSourceConfigRequest
        - 更新数据源配置的请求体

    ErrorResponse
        - 统一错误响应格式（所有 4xx/5xx）
        - 字段：error（机器可读错误码）、detail（人类可读描述）、request_id

模块依赖：
    - pydantic：BaseModel 和字段验证
"""

from __future__ import annotations

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
        description: 对数据源的描述
    """

    name: str
    needs_key: bool
    description: str


class SourcesResponse(BaseModel):
    """数据源列表响应 — 按类别分组

    Attributes:
        paper: 论文搜索数据源列表
        patent: 专利搜索数据源列表
        web: 网页搜索数据源列表
    """

    paper: list[SourceInfo] = []
    patent: list[SourceInfo] = []
    web: list[SourceInfo] = []


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


class SearchPaperResponse(BaseModel):
    """论文搜索响应

    Attributes:
        query: 原始搜索关键词
        sources: 查询的数据源列表
        results: 搜索结果列表（字典格式）
        total: 返回结果总数
        meta: 搜索元信息（源的成功/失败状态）
    """

    query: str
    sources: list[str]
    results: list[dict]
    total: int
    meta: SearchMeta = Field(
        default_factory=lambda: SearchMeta(requested=[], succeeded=[], failed=[])
    )


class SearchPatentResponse(BaseModel):
    """专利搜索响应

    结构与 SearchPaperResponse 相同，sources 替换为专利数据源。
    """

    query: str
    sources: list[str]
    results: list[dict]
    total: int
    meta: SearchMeta = Field(
        default_factory=lambda: SearchMeta(requested=[], succeeded=[], failed=[])
    )


class SearchWebResponse(BaseModel):
    """/search/web 响应 — 对齐 paper/patent 的统一结构

    Attributes:
        query: 原始搜索关键词
        engines: 查询的搜索引擎列表
        results: 网页结果列表
        total: 返回结果总数
        meta: 搜索元信息（engines 的成功/失败状态）
    """

    query: str
    engines: list[str]
    results: list[dict]
    total: int
    meta: SearchMeta = Field(
        default_factory=lambda: SearchMeta(requested=[], succeeded=[], failed=[])
    )


class ReadinessResponse(BaseModel):
    """Kubernetes readiness 探针响应 — 检查本地依赖可用性

    用于 K8s 确定 Pod 是否准备好接收流量。不执行网络调用，避免探针超时。

    Attributes:
        ready: 是否准备就绪
        version: 应用版本
        error: 错误信息（若 ready=False）
    """

    ready: bool
    version: str | None = None
    error: str | None = None


class ConfigReloadResponse(BaseModel):
    """配置重载响应

    Attributes:
        status: 重载状态（"ok" 表示成功）
        password_set: 是否配置了 API 密码
    """

    status: str = Field(examples=["ok"])
    password_set: bool


class DoctorResponse(BaseModel):
    """数据源健康检查聚合响应

    Attributes:
        total: 检查的数据源总数
        ok: 状态正常的数据源数
        sources: 各数据源的详细检查结果
    """

    total: int
    ok: int
    sources: list[dict]


class HttpBackendResponse(BaseModel):
    """HTTP 后端配置查询响应

    Attributes:
        default: 全局默认 HTTP 后端
        overrides: 各数据源的个性化后端覆盖
        curl_cffi_available: curl_cffi 库是否可用
    """

    default: str = Field(examples=["auto"])
    overrides: dict[str, str] = Field(default_factory=dict)
    curl_cffi_available: bool


class UpdateSourceConfigRequest(BaseModel):
    """更新数据源频道配置的请求体 — 避免敏感信息出现在 URL 中

    使用 JSON 请求体而非 URL Query，确保 API Key 等敏感字段不被记录在日志中。
    所有字段均可选，缺失的字段不会被更新。

    Attributes:
        enabled: 是否启用该数据源
        proxy: HTTP/SOCKS 代理 URL（如 "socks5://127.0.0.1:1080"）
        http_backend: HTTP 后端优先级（auto/curl_cffi/httpx）
        base_url: 数据源的自定义 API 基础 URL
        api_key: 该数据源的 API Key
    """

    enabled: bool | None = None
    proxy: str | None = None
    http_backend: str | None = None
    base_url: str | None = None
    api_key: str | None = None


class ProxyConfigResponse(BaseModel):
    """全局代理配置查询响应

    Attributes:
        proxy: 全局代理 URL
        proxy_pool: 代理池 URL 列表
        socks_supported: httpx 是否支持 SOCKS 代理
    """

    proxy: str | None = None
    proxy_pool: list[str] = Field(default_factory=list)
    socks_supported: bool = False


class UpdateProxyConfigRequest(BaseModel):
    """更新全局代理配置的请求体

    Attributes:
        proxy: 全局代理 URL（空字符串清除）
        proxy_pool: 代理池 URL 列表（空列表清除）
    """

    proxy: str | None = None
    proxy_pool: list[str] | None = None


class ErrorResponse(BaseModel):
    """统一错误响应格式 — 所有 4xx/5xx 错误使用此结构

    便于客户端统一处理错误，仅根据 error 码而非状态码判断。
    request_id 用于日志系统追踪问题根源。

    Attributes:
        error: 机器可读错误码（如 "not_found"、"rate_limited"、"internal_error"）
        detail: 人类可读的错误描述
        request_id: 关联的请求 ID，便于日志追踪
    """

    error: str = Field(description="机器可读错误码", examples=["not_found"])
    detail: str = Field(description="人类可读错误描述", examples=["未知数据源: foo"])
    request_id: str = Field(description="关联 ID，用于日志追踪", examples=["a1b2c3d4e5f6"])


class FetchRequest(BaseModel):
    """内容抓取请求体

    Attributes:
        urls: 目标 URL 列表（1-20 条）
        provider: 提供者名称（默认 builtin）
        timeout: 每个 URL 超时秒数
    """

    urls: list[str] = Field(..., min_length=1, max_length=20)
    provider: str = Field(default="builtin")
    timeout: float = Field(default=30.0, ge=1.0, le=120.0)
