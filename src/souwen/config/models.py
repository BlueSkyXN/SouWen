"""SouWen 配置数据模型

包含 SourceChannelConfig (单源频道配置) 与 SouWenConfig (全局配置)
两个 Pydantic 模型.
"""

from __future__ import annotations

import logging
import random
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from .validators import _validate_proxy_url

logger = logging.getLogger("souwen.config")


class SourceChannelConfig(BaseModel):
    """单源频道配置

    控制单个数据源的行为.所有字段都有合理默认值,
    只需覆盖想要自定义的部分.

    Attributes:
        enabled: 是否启用此数据源
        proxy: 代理策略 — inherit(继承全局) | none(不用代理) | warp(走WARP) | 显式URL
        http_backend: HTTP 后端 — auto | curl_cffi | httpx
        base_url: 覆盖数据源的基础 URL
        api_key: 覆盖 API Key(优先于全局 flat key)
        headers: 附加请求头(合并到默认头之上)
        params: 附加参数(传递给源的搜索方法)
    """

    enabled: bool = True
    proxy: str = "inherit"
    http_backend: str = "auto"
    base_url: str | None = None
    api_key: str | None = None
    headers: dict[str, str] = Field(default_factory=dict)
    params: dict[str, str | int | float | bool] = Field(default_factory=dict)


class SouWenConfig(BaseModel):
    """SouWen 全局配置

    包含所有数据源 API Key、代理设置、HTTP 后端选择、频道级覆盖配置.

    主要字段组:
        论文源 API Key: openalex_email, semantic_scholar_api_key, core_api_key,
                        pubmed_api_key, unpaywall_email, ieee_api_key

        专利源 API Key: uspto_api_key, epo_consumer_key/secret, cnipa_client_id/secret,
                        lens_api_token, patsnap_api_key

        搜索源 API Key: searxng_url, tavily_api_key, exa_api_key, serper_api_key,
                        brave_api_key, serpapi_api_key, firecrawl_api_key,
                        perplexity_api_key, linkup_api_key, xcrawl_api_key,
                        scrapingdog_api_key,
                        whoogle_url, websurfx_url, github_token,
                        stackoverflow_api_key, youtube_api_key, jina_api_key,
                        scrapfly_api_key, diffbot_api_token,
                        scrapingbee_api_key, zenrows_api_key,
                        scraperapi_api_key, apify_api_token,
                        cloudflare_api_token, cloudflare_account_id

        通用设置: proxy, proxy_pool (代理池), timeout (超时秒数),
                 max_retries (重试次数), data_dir (数据存储目录)

        HTTP 后端: default_http_backend (全局默认), http_backend (按源覆盖字典)

        服务配置: api_password (旧版统一密码), visitor_password (访客密码),
                 admin_password (管理密码), cors_origins, trusted_proxies,
                 expose_docs (是否暴露 Swagger 文档)

        WARP 代理: warp_enabled,
                  warp_mode (auto|wireproxy|kernel|usque|warp-cli|external),
                  warp_socks_port, warp_endpoint, warp_bind_address,
                  warp_startup_timeout, warp_device_name,
                  warp_proxy_username, warp_proxy_password,
                  warp_usque_path, warp_usque_config, warp_usque_transport,
                  warp_usque_system_dns, warp_usque_on_connect,
                  warp_usque_on_disconnect,
                  warp_http_port, warp_license_key, warp_team_token, warp_gost_args,
                  warp_external_proxy

        频道配置: sources (dict[源名, SourceChannelConfig])

    方法:
        get_proxy() → str|None — 从 proxy_pool 随机取(优先),否则用单一 proxy
        get_http_backend(source_name) → str — 获取指定源的 HTTP 后端
        resolve_proxy/api_key/base_url/headers/params(source_name) — 解析源级覆盖配置
    """

    # ===== 论文数据源 =====
    openalex_email: str | None = None
    semantic_scholar_api_key: str | None = None
    core_api_key: str | None = None
    openaire_api_key: str | None = None
    doaj_api_key: str | None = None
    zenodo_access_token: str | None = None
    pubmed_api_key: str | None = None
    unpaywall_email: str | None = None
    ieee_api_key: str | None = None
    # Zotero 个人文献库
    zotero_api_key: str | None = None  # Zotero Web API Key
    zotero_library_id: str | None = None  # 用户 ID 或群组 ID
    zotero_library_type: str | None = None  # "user" (默认) 或 "group"

    # ===== 专利数据源 =====
    uspto_api_key: str | None = None
    epo_consumer_key: str | None = None
    epo_consumer_secret: str | None = None
    cnipa_client_id: str | None = None
    cnipa_client_secret: str | None = None
    lens_api_token: str | None = None
    patsnap_api_key: str | None = None

    # ===== 常规搜索 =====
    # 爬虫引擎 (DuckDuckGo/Yahoo/Brave/Google/Bing) 无需 Key
    # API 引擎需要对应的 Key
    searxng_url: str | None = None  # SearXNG 自建实例 URL
    tavily_api_key: str | None = None  # Tavily AI 搜索
    exa_api_key: str | None = None  # Exa 语义搜索
    serper_api_key: str | None = None  # Serper (Google SERP)
    brave_api_key: str | None = None  # Brave Search 官方 API
    # 新增搜索引擎 API Key
    serpapi_api_key: str | None = None  # SerpAPI (多引擎 SERP)
    firecrawl_api_key: str | None = None  # Firecrawl (搜索+爬取)
    perplexity_api_key: str | None = None  # Perplexity Sonar API
    linkup_api_key: str | None = None  # Linkup 搜索 API
    xcrawl_api_key: str | None = None  # XCrawl 搜索+抓取 API
    scrapingdog_api_key: str | None = None  # ScrapingDog SERP API
    metaso_api_key: str | None = None  # Metaso 秘塔搜索 API
    whoogle_url: str | None = None  # Whoogle 自建实例 URL
    websurfx_url: str | None = None  # Websurfx 自建实例 URL
    zhipuai_api_key: str | None = None  # 智谱 AI Web Search Pro
    aliyun_iqs_api_key: str | None = None  # 阿里云 IQS 通义晓搜
    # 社区 / 视频平台
    github_token: str | None = None  # GitHub PAT（可选，提升速率限制）
    stackoverflow_api_key: str | None = None  # StackOverflow API Key（可选，提升配额）
    youtube_api_key: str | None = None  # YouTube Data API v3 Key
    bilibili_sessdata: str = (
        ""  # Bilibili SESSDATA Cookie（可选，启用授权 API：高画质/高频/字幕等）
    )
    # 国际社交媒体（官方 API）
    twitter_bearer_token: str | None = None  # Twitter/X API v2 Bearer Token（Basic 套餐及以上）
    reddit_client_id: str | None = None  # Reddit OAuth2 App Client ID
    reddit_client_secret: str | None = None  # Reddit OAuth2 App Client Secret
    facebook_app_id: str | None = None  # Meta Facebook App ID
    facebook_app_secret: str | None = None  # Meta Facebook App Secret
    # 企业/办公平台
    feishu_app_id: str | None = None  # 飞书自建应用 App ID
    feishu_app_secret: str | None = None  # 飞书自建应用 App Secret
    # 内容抓取
    jina_api_key: str | None = None  # Jina Reader API Key（可选，免费层无需 Key）
    scrapfly_api_key: str | None = None  # Scrapfly API Key（JS 渲染+AI 提取）
    diffbot_api_token: str | None = None  # Diffbot API Token（结构化内容提取）
    scrapingbee_api_key: str | None = None  # ScrapingBee API Key（代理+JS 渲染+反爬）
    zenrows_api_key: str | None = None  # ZenRows API Key（代理+JS 渲染+反爬）
    scraperapi_api_key: str | None = None  # ScraperAPI API Key（代理+JS 渲染）
    apify_api_token: str | None = None  # Apify API Token（平台化 Actor 爬虫）
    cloudflare_api_token: str | None = None  # Cloudflare API Token（Browser Rendering）
    cloudflare_account_id: str | None = None  # Cloudflare Account ID（Browser Rendering）

    # ===== MCP (Model Context Protocol) =====
    mcp_server_url: str | None = None  # MCP Server 端点 URL（如 https://mcp.example.com/mcp）
    mcp_transport: str = "streamable_http"  # 传输方式: streamable_http | sse
    mcp_fetch_tool_name: str = "fetch"  # MCP fetch 工具名称
    mcp_extra_headers: dict[str, str] = Field(default_factory=dict)  # MCP 请求附加头

    # ===== MCP HTTP 网络端点（服务端） =====
    mcp_http_enabled: bool = False  # 是否启用网络 MCP（SHTTP），挂载于 /mcp
    mcp_http_enable_sse: bool = True  # 是否额外启用 SSE 传输，挂载于 /mcp/sse
    mcp_http_stateless: bool = True  # SHTTP 是否使用无状态模式
    mcp_http_json_response: bool = True  # SHTTP 是否使用 JSON 响应（而非 SSE 流）

    # ===== 通用 =====
    proxy: str | None = None
    proxy_pool: list[str] = []
    timeout: int = 30
    max_retries: int = 3
    data_dir: str = "~/.local/share/souwen"
    respect_robots_txt: bool = False  # 是否遵守目标站点 robots.txt（builtin fetcher 使用）

    # ===== HTTP 后端 =====
    # 全局默认 HTTP 后端:auto(自动选择)| curl_cffi | httpx
    default_http_backend: str = "auto"
    # 按源覆盖,例如 {"duckduckgo": "httpx", "google_patents": "curl_cffi"}
    http_backend: dict[str, str] = Field(default_factory=dict)

    # ===== 服务（认证） =====
    api_password: str | None = None  # 旧版统一密码(向后兼容,同时作用于访客和管理)
    visitor_password: str | None = None  # 旧版访客密码(映射为 user_password)
    user_password: str | None = None  # 用户密码(保护搜索和 /sources)
    admin_password: str | None = None  # 管理密码(保护管理端点)
    guest_enabled: bool = False  # 是否启用游客访问(无Token可访问搜索)

    @property
    def effective_user_password(self) -> str | None:
        """解析生效的用户密码: user_password > visitor_password > api_password > None(开放)。
        显式设为空字符串表示"强制开放,忽略回退"。"""
        if self.user_password is not None:
            return self.user_password or None
        if self.visitor_password is not None:
            return self.visitor_password or None
        return self.api_password

    @property
    def effective_visitor_password(self) -> str | None:
        """向后兼容属性,映射到 effective_user_password。"""
        return self.effective_user_password

    @property
    def effective_admin_password(self) -> str | None:
        """解析生效的管理密码: admin_password > api_password > None。
        显式设为空字符串表示"不使用密码,忽略 api_password 回退";
        无密码 admin 访问仍需 SOUWEN_ADMIN_OPEN=1 显式放行。"""
        if self.admin_password is not None:
            return self.admin_password or None
        return self.api_password

    cors_origins: list[str] = Field(
        default_factory=list,
        description="CORS 允许的来源列表,为空时不启用 CORS",
    )
    trusted_proxies: list[str] = Field(
        default_factory=list,
        description=(
            "受信反向代理的 IP/CIDR 列表;只有来自这些地址的请求才会"
            "读取 X-Forwarded-For 头解析真实客户端 IP."
        ),
    )
    expose_docs: bool = Field(
        default=True,
        description="是否暴露 /docs、/redoc、/openapi.json;生产环境可设为 false.",
    )

    # ===== WARP 代理 =====
    warp_enabled: bool = False
    warp_mode: str = "auto"  # auto | wireproxy | kernel | usque | warp-cli | external
    warp_socks_port: int = 1080
    warp_endpoint: str | None = None
    warp_bind_address: str = "127.0.0.1"  # 代理绑定地址
    warp_startup_timeout: int = 15  # 启动健康检查超时(秒)
    warp_device_name: str | None = None  # 注册设备名
    warp_proxy_username: str | None = None  # 代理认证用户名
    warp_proxy_password: str | None = None  # 代理认证密码
    # usque 模式
    warp_usque_path: str | None = None  # usque 二进制路径（默认从 PATH 查找）
    warp_usque_config: str | None = None  # usque config.json 路径
    warp_usque_transport: str = "auto"  # auto | quic | http2
    warp_usque_system_dns: bool = False  # 使用系统 DNS 而非隧道 DNS
    warp_usque_on_connect: str | None = None  # 连接后执行的脚本路径
    warp_usque_on_disconnect: str | None = None  # 断开后执行的脚本路径
    warp_http_port: int = 0  # HTTP 代理端口（usque/warp-cli 模式，0=不启用）
    # warp-cli 模式
    warp_license_key: str | None = None  # WARP+ License Key
    warp_team_token: str | None = None  # ZeroTrust Team Token (JWT)
    warp_gost_args: str | None = None  # 自定义 GOST 启动参数
    # external 模式
    warp_external_proxy: str | None = None  # 外部 WARP 代理地址，如 socks5://warp:1080

    # ===== 数据源频道配置 =====
    sources: dict[str, SourceChannelConfig] = Field(default_factory=dict)

    # ===== 插件系统 =====
    plugins: list[str] = Field(
        default_factory=list,
        description="手动指定的插件列表，格式为 'module.path:attribute'",
    )

    @field_validator("proxy")
    @classmethod
    def _check_proxy(cls, v: str | None) -> str | None:
        # 仅校验显式 URL;空/None 放行
        return _validate_proxy_url(v)

    @field_validator("proxy_pool")
    @classmethod
    def _check_proxy_pool(cls, v: list[str]) -> list[str]:
        return [p for p in (_validate_proxy_url(u) for u in (v or [])) if p]

    @property
    def data_path(self) -> Path:
        """返回展开后的数据目录路径"""
        return Path(self.data_dir).expanduser()

    def get_proxy(self) -> str | None:
        """返回代理地址:优先从 proxy_pool 随机选取,否则回退到 proxy

        Returns:
            合法代理 URL 或 None
        """
        if self.proxy_pool:
            return random.choice(self.proxy_pool)
        return self.proxy

    def get_http_backend(self, source: str) -> Literal["auto", "curl_cffi", "httpx"]:
        """获取指定源的 HTTP 后端选择

        按优先级查询:http_backend[源] > default_http_backend.
        无效值记录警告后回退到 auto.

        Args:
            source: 数据源名称

        Returns:
            HTTP 后端选择:auto (自动选择) | curl_cffi | httpx
        """
        _VALID: set[str] = {"auto", "curl_cffi", "httpx"}
        val = self.http_backend.get(source, self.default_http_backend)
        if val not in _VALID:
            logger.warning("无效的 http_backend 值 %r(源=%s),回退到 auto", val, source)
            return "auto"
        return val  # type: ignore[return-value]

    # ── 数据源频道配置解析 ──────────────────────────────────

    def get_source_config(self, name: str) -> SourceChannelConfig:
        """获取指定源的频道配置,不存在则返回默认值"""
        return self.sources.get(name, SourceChannelConfig())

    def is_source_enabled(self, name: str) -> bool:
        """检查数据源是否启用"""
        return self.get_source_config(name).enabled

    def resolve_proxy(self, source: str) -> str | None:
        """解析数据源的代理地址

        按优先级:频道代理设置 > 全局代理.
        支持 inherit (继承全局) | none (无代理) | warp (WARP) | 显式 URL.

        Args:
            source: 数据源名称

        Returns:
            代理 URL 或 None
        """
        sc = self.get_source_config(source)
        mode = sc.proxy.strip().lower()
        if mode == "inherit":
            return self.get_proxy()
        if mode == "none":
            return None
        if mode == "warp":
            return f"socks5://localhost:{self.warp_socks_port}"
        # 显式 proxy URL — 校验后返回
        return _validate_proxy_url(sc.proxy)

    def resolve_backend(self, source: str) -> Literal["auto", "curl_cffi", "httpx"]:
        """解析数据源的 HTTP 后端

        按优先级:频道后端 > 全局后端.

        Args:
            source: 数据源名称

        Returns:
            HTTP 后端:auto | curl_cffi | httpx
        """
        _VALID: set[str] = {"auto", "curl_cffi", "httpx"}
        sc = self.get_source_config(source)
        if sc.http_backend != "auto":
            if sc.http_backend in _VALID:
                return sc.http_backend  # type: ignore[return-value]
            logger.warning("无效的 sources.%s.http_backend=%r,回退到 auto", source, sc.http_backend)
        # 回退到旧版 per-source dict → 全局默认
        return self.get_http_backend(source)

    def resolve_api_key(self, source: str, legacy_field: str | None = None) -> str | None:
        """解析 API Key:频道配置 > 旧版 flat key

        Args:
            source: 数据源名称
            legacy_field: 旧版 SouWenConfig 字段名(如 "tavily_api_key")
        """
        sc = self.get_source_config(source)
        if sc.api_key:
            return sc.api_key
        if legacy_field:
            return getattr(self, legacy_field, None)
        return None

    def resolve_base_url(self, source: str, default: str = "") -> str:
        """解析基础 URL:频道覆盖 > 默认值"""
        sc = self.get_source_config(source)
        return sc.base_url or default

    def resolve_headers(self, source: str) -> dict[str, str]:
        """获取频道自定义请求头"""
        return dict(self.get_source_config(source).headers)

    def resolve_params(self, source: str) -> dict[str, str | int | float | bool]:
        """获取频道自定义参数"""
        return dict(self.get_source_config(source).params)
