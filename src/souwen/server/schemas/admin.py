"""管理端 / YouTube / Wayback 响应模型"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel, field_validator


class AdminConfigResponse(RootModel[dict[str, Any]]):
    """当前配置的脱敏视图响应。

    字段来自 ``SouWenConfig``，保持动态字典以避免在 REST schema 中复制配置模型。
    """


class ConfigReloadResponse(BaseModel):
    """配置重载响应"""

    status: str = Field(examples=["ok"])
    password_set: bool


class DoctorSourceResponse(BaseModel):
    """单个数据源的 doctor 状态条目。"""

    name: str
    category: str
    status: str
    integration_type: Literal["open_api", "scraper", "official_api", "self_hosted"]
    required_key: str | None = None
    key_requirement: Literal["none", "optional", "required", "self_hosted"]
    auth_requirement: Literal["none", "optional", "required", "self_hosted"]
    credential_fields: list[str] = Field(default_factory=list)
    optional_credential_effect: str | None = None
    risk_level: Literal["low", "medium", "high"]
    risk_reasons: list[str] = Field(default_factory=list)
    distribution: Literal["core", "extra", "plugin"]
    package_extra: str | None = None
    stability: Literal["stable", "beta", "experimental", "deprecated"]
    usage_note: str | None = None
    min_edition: Literal["basic", "pro", "full"]
    edition: Literal["basic", "pro", "full"]
    edition_available: bool
    edition_reason: str = ""
    runtime_available: bool
    runtime_reason: str = ""
    credentials_satisfied: bool
    config_available: bool
    config_reason: str = ""
    available: bool
    message: str
    enabled: bool
    description: str = ""
    channel: dict[str, str] | None = None
    live_probe: dict[str, Any] | None = None


class DoctorResponse(BaseModel):
    """数据源健康检查聚合响应"""

    total: int
    # 严格正常源数量，仅 status == "ok"。
    ok: int
    # 可用源数量，包含 ok / limited / warning / degraded。
    available: int = 0
    # 兼容字段：limited / warning / degraded 三类降级可用源总数。
    degraded: int = 0
    degraded_total: int = 0
    failed: int = 0
    limited: int = 0
    warning: int = 0
    missing_key: int = 0
    unavailable: int = 0
    disabled: int = 0
    status_counts: dict[str, int] = Field(default_factory=dict)
    edition: Literal["basic", "pro", "full"] = "pro"
    probe_mode: Literal["static", "live"] = "static"
    live_probe: dict[str, Any] | None = None
    sources: list[DoctorSourceResponse]


class AdminPingResponse(BaseModel):
    """管理端轻量存活探测响应。"""

    status: Literal["ok"]


class HttpBackendResponse(BaseModel):
    """HTTP 后端配置查询响应"""

    default: str = Field(examples=["auto"])
    overrides: dict[str, str] = Field(default_factory=dict)
    curl_cffi_available: bool


class HttpBackendUpdateResponse(BaseModel):
    """HTTP 后端配置更新响应。"""

    status: Literal["ok"]
    default: str = Field(examples=["auto"])
    overrides: dict[str, str] = Field(default_factory=dict)


class SourceChannelConfigResponse(BaseModel):
    """数据源频道配置响应。"""

    enabled: bool
    proxy: str
    http_backend: str
    base_url: str | None = None
    has_api_key: bool
    configured_credentials: bool
    credentials_satisfied: bool
    available: bool
    headers: dict[str, str] = Field(default_factory=dict)
    params: dict[str, str | int | float | bool] = Field(default_factory=dict)
    category: str
    domain: str
    capabilities: list[str] = Field(default_factory=list)
    integration_type: Literal["open_api", "scraper", "official_api", "self_hosted"]
    min_edition: Literal["basic", "pro", "full"]
    edition_available: bool
    edition_reason: str = ""
    key_requirement: Literal["none", "optional", "required", "self_hosted"]
    auth_requirement: Literal["none", "optional", "required", "self_hosted"]
    credential_fields: list[str] = Field(default_factory=list)
    optional_credential_effect: str | None = None
    risk_level: Literal["low", "medium", "high"]
    risk_reasons: list[str] = Field(default_factory=list)
    distribution: Literal["core", "extra", "plugin"]
    package_extra: str | None = None
    stability: Literal["stable", "beta", "experimental", "deprecated"]
    usage_note: str | None = None
    default_enabled: bool
    default_for: list[str] = Field(default_factory=list)
    description: str
    name: str | None = None


class UpdateSourceConfigRequest(BaseModel):
    """更新数据源频道配置的请求体 — 避免敏感信息出现在 URL 中"""

    enabled: bool | None = None
    proxy: str | None = None
    http_backend: str | None = None
    base_url: str | None = None
    api_key: str | None = None


class UpdateSourceConfigResponse(BaseModel):
    """数据源频道配置更新响应。"""

    status: Literal["ok"]
    source: str


class ProxyConfigResponse(BaseModel):
    """全局代理配置查询响应"""

    proxy: str | None = None
    proxy_pool: list[str] = Field(default_factory=list)
    socks_supported: bool = False


class UpdateProxyConfigRequest(BaseModel):
    """更新全局代理配置的请求体"""

    proxy: str | None = None
    proxy_pool: list[str] | None = None


class ProxyConfigUpdateResponse(BaseModel):
    """全局代理配置更新响应。"""

    status: Literal["ok"]
    proxy: str | None = None
    proxy_pool: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# WARP 管理响应
# ---------------------------------------------------------------------------


class WarpStatusResponse(BaseModel):
    """WARP 运行时状态响应。"""

    status: Literal["disabled", "starting", "enabled", "stopping", "error"]
    mode: str
    owner: str
    socks_port: int
    http_port: int
    ip: str
    pid: int
    interface: str | None = None
    last_error: str | None = None
    protocol: str
    proxy_type: str
    available_modes: dict[str, bool] = Field(default_factory=dict)


class WarpModeInfoResponse(BaseModel):
    """单个 WARP 模式能力与 edition 可用性。"""

    id: str
    name: str
    protocol: str
    installed: bool
    configured: bool | None = None
    requires_privilege: bool
    docker_only: bool
    proxy_types: list[str] = Field(default_factory=list)
    description: str
    reason: str = ""
    external_proxy: str | None = None
    min_edition: Literal["basic", "pro", "full"] | None = None
    edition_available: bool | None = None
    edition_reason: str | None = None


class WarpModesResponse(BaseModel):
    """WARP 模式列表响应。"""

    modes: list[WarpModeInfoResponse] = Field(default_factory=list)


class WarpActionResponse(BaseModel):
    """WARP 启停、注册、切换和卸载操作响应。"""

    model_config = ConfigDict(extra="allow")

    ok: bool
    mode: str | None = None
    ip: str | None = None
    message: str | None = None
    error: str | None = None
    error_code: str | None = None


class WarpTestResponse(BaseModel):
    """WARP 代理连通性测试响应。"""

    ok: bool
    ip: str
    port: int
    mode: str
    protocol: str
    proxy_type: str | None = None


class WarpConfigResponse(BaseModel):
    """当前 WARP 配置的脱敏展示响应。"""

    warp_enabled: bool
    warp_mode: str
    warp_socks_port: int
    warp_http_port: int
    warp_endpoint: str | None = None
    warp_bind_address: str
    warp_startup_timeout: int
    warp_device_name: str | None = None
    warp_usque_transport: str
    warp_usque_system_dns: bool
    warp_usque_on_connect: str | None = None
    warp_usque_on_disconnect: str | None = None
    warp_external_proxy: str | None = None
    warp_usque_path: str | None = None
    warp_usque_config: str | None = None
    warp_gost_args: str | None = None
    has_license_key: bool
    has_team_token: bool
    has_proxy_auth: bool


class WarpComponentInfoResponse(BaseModel):
    """WARP 组件安装状态。"""

    name: str
    installed: bool
    version: str | None = None
    path: str | None = None
    system_path: str | None = None
    source: Literal["runtime", "system", "not_installed"]


class WarpComponentsResponse(BaseModel):
    """WARP 组件状态列表响应。"""

    components: list[WarpComponentInfoResponse] = Field(default_factory=list)


class WarpComponentInstallResponse(BaseModel):
    """WARP 组件安装响应。"""

    model_config = ConfigDict(extra="allow")

    ok: bool
    component: str
    version: str | None = None
    path: str | None = None


# ---------------------------------------------------------------------------
# 插件管理响应
# ---------------------------------------------------------------------------


class PluginInfoResponse(BaseModel):
    """单个插件状态视图。"""

    name: str
    package: str | None = None
    version: str | None = None
    status: str
    source: str
    first_party: bool = False
    description: str = ""
    error: str | None = None
    source_adapters: list[str] = Field(default_factory=list)
    fetch_handlers: list[str] = Field(default_factory=list)
    restart_required: bool = False


class PluginListResponse(BaseModel):
    """插件清单响应。"""

    plugins: list[PluginInfoResponse] = Field(default_factory=list)
    restart_required: bool
    install_enabled: bool


class PluginHealthResponse(BaseModel):
    """插件健康检查响应，允许插件追加自定义安全字段。"""

    model_config = ConfigDict(extra="allow")

    status: str
    message: str | None = None


class PluginActionResponse(BaseModel):
    """插件启用 / 禁用操作响应。"""

    success: bool
    restart_required: bool
    message: str


class PluginPackageActionResponse(BaseModel):
    """插件安装 / 卸载操作响应。"""

    success: bool
    package: str
    restart_required: bool
    message: str


class PluginReloadErrorResponse(BaseModel):
    """插件 reload 错误条目，已移除异常详情。"""

    source: str = ""
    name: str = ""


class PluginReloadResponse(BaseModel):
    """插件 reload 响应。"""

    loaded: list[str] = Field(default_factory=list)
    errors: list[PluginReloadErrorResponse] = Field(default_factory=list)
    message: str = ""


# ---------------------------------------------------------------------------
# YouTube Data API 响应
# ---------------------------------------------------------------------------


class YouTubeTrendingResponse(BaseModel):
    """YouTube 热门视频响应 — 按地区/分类聚合"""

    region: str
    category: str = ""
    results: list[dict]
    total: int


class YouTubeVideoDetailResponse(BaseModel):
    """YouTube 视频详情响应 — 含统计信息"""

    video_ids: list[str]
    results: list[dict]
    total: int


class YouTubeTranscriptResponse(BaseModel):
    """YouTube 字幕响应 — 零配额消耗"""

    video_id: str
    lang: str
    segments: list[dict] = Field(default_factory=list)
    text: str = ""
    available: bool = True


# ---------------------------------------------------------------------------
# Wayback Machine 响应
# ---------------------------------------------------------------------------


class WaybackCDXApiResponse(BaseModel):
    """Wayback CDX 查询响应 — URL 历史快照列表"""

    url: str
    snapshots: list[dict] = Field(default_factory=list)
    total: int = 0


class WaybackAvailabilityResponse(BaseModel):
    """Wayback 可用性检查响应"""

    url: str
    available: bool = False
    snapshot_url: str | None = None
    timestamp: str | None = None
    status: int | None = None


class WaybackSaveRequest(BaseModel):
    """Wayback 存档请求体"""

    url: str = Field(..., min_length=1, description="待存档 URL")
    timeout: float = Field(60.0, ge=10, le=300, description="超时秒数")

    @field_validator("url", mode="before")
    @classmethod
    def _normalize_url(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        stripped = value.strip()
        if not stripped:
            raise ValueError("url 不能是空字符串")
        return stripped


class WaybackSaveResponse(BaseModel):
    """Wayback 存档响应"""

    url: str
    success: bool = False
    snapshot_url: str | None = None
    timestamp: str | None = None
    error: str | None = None


class YamlConfigResponse(BaseModel):
    """原始 YAML 配置文件内容响应"""

    content: str = Field(..., description="YAML 文件内容")
    path: str | None = Field(None, description="配置文件路径，None 表示返回默认模板")
    unknown_keys: list[str] = Field(
        default_factory=list,
        description="保存时被忽略的未知配置键（typo 或不支持的字段），仅在 PUT 响应中可能非空",
    )


class YamlConfigSaveRequest(BaseModel):
    """保存 YAML 配置文件请求体"""

    content: str = Field(..., description="YAML 配置文件内容")
