"""API 响应模型 — 子模块聚合再导出

为兼容 ``from souwen.server.schemas import XxxResponse`` 的旧代码，
此 ``__init__`` 将所有子模块中的模型重新导出。
"""

from __future__ import annotations

from souwen.server.schemas.admin import (
    ConfigReloadResponse,
    DoctorResponse,
    HttpBackendResponse,
    ProxyConfigResponse,
    UpdateProxyConfigRequest,
    UpdateSourceConfigRequest,
    WaybackAvailabilityResponse,
    WaybackCDXApiResponse,
    WaybackSaveRequest,
    WaybackSaveResponse,
    YamlConfigResponse,
    YamlConfigSaveRequest,
    YouTubeTranscriptResponse,
    YouTubeTrendingResponse,
    YouTubeVideoDetailResponse,
)
from souwen.server.schemas.common import (
    SOURCE_CATEGORY_ORDER,
    ErrorResponse,
    HealthResponse,
    ReadinessResponse,
    SearchMeta,
    SourceCatalogItem,
    SourceCatalogResponse,
    SourceCategoryInfo,
)
from souwen.server.schemas.fetch import FetchRequest
from souwen.server.schemas.search import (
    SearchImagesResponse,
    SearchPaperResponse,
    SearchPatentResponse,
    SearchVideosResponse,
    SearchWebResponse,
)

__all__ = [
    "SOURCE_CATEGORY_ORDER",
    "ConfigReloadResponse",
    "DoctorResponse",
    "ErrorResponse",
    "FetchRequest",
    "HealthResponse",
    "HttpBackendResponse",
    "ProxyConfigResponse",
    "ReadinessResponse",
    "SearchImagesResponse",
    "SearchMeta",
    "SearchPaperResponse",
    "SearchPatentResponse",
    "SearchVideosResponse",
    "SearchWebResponse",
    "SourceCatalogItem",
    "SourceCatalogResponse",
    "SourceCategoryInfo",
    "UpdateProxyConfigRequest",
    "UpdateSourceConfigRequest",
    "WaybackAvailabilityResponse",
    "WaybackCDXApiResponse",
    "WaybackSaveRequest",
    "WaybackSaveResponse",
    "YamlConfigResponse",
    "YamlConfigSaveRequest",
    "YouTubeTranscriptResponse",
    "YouTubeTrendingResponse",
    "YouTubeVideoDetailResponse",
]
