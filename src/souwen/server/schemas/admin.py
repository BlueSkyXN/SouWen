"""管理端 / YouTube / Wayback 响应模型"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ConfigReloadResponse(BaseModel):
    """配置重载响应"""

    status: str = Field(examples=["ok"])
    password_set: bool


class DoctorResponse(BaseModel):
    """数据源健康检查聚合响应"""

    total: int
    ok: int
    sources: list[dict]


class HttpBackendResponse(BaseModel):
    """HTTP 后端配置查询响应"""

    default: str = Field(examples=["auto"])
    overrides: dict[str, str] = Field(default_factory=dict)
    curl_cffi_available: bool


class UpdateSourceConfigRequest(BaseModel):
    """更新数据源频道配置的请求体 — 避免敏感信息出现在 URL 中"""

    enabled: bool | None = None
    proxy: str | None = None
    http_backend: str | None = None
    base_url: str | None = None
    api_key: str | None = None


class ProxyConfigResponse(BaseModel):
    """全局代理配置查询响应"""

    proxy: str | None = None
    proxy_pool: list[str] = Field(default_factory=list)
    socks_supported: bool = False


class UpdateProxyConfigRequest(BaseModel):
    """更新全局代理配置的请求体"""

    proxy: str | None = None
    proxy_pool: list[str] | None = None


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

    url: str = Field(..., description="待存档 URL")
    timeout: float = Field(60.0, ge=10, le=300, description="超时秒数")


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
