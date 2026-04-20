"""SouWen 统一配置管理

文件用途:
    集中管理所有 SouWen 配置项,支持多层级优先级(环境变量 > YAML > .env > 默认值).
    提供便捷的代理、HTTP 后端、频道配置解析接口.

类清单:
    SourceChannelConfig(Pydantic BaseModel)
        - 功能:单个数据源的频道配置
        - 字段:enabled (bool), proxy (str), http_backend (str),
                base_url (str|None), api_key (str|None),
                headers (dict[str,str]), params (dict)
        - 用途:覆盖全局配置,按源定制化管理

    SouWenConfig(Pydantic BaseModel)
        - 功能:全局配置对象,包含所有配置项
        - 主要字段组:
          * 论文源 API Key: openalex_email, semantic_scholar_api_key, ...
          * 专利源 API Key: uspto_api_key, epo_consumer_key, ...
          * Web 源 API Key: tavily_api_key, serper_api_key, ...
          * 通用设置:proxy, timeout, max_retries, data_dir
          * HTTP 后端:default_http_backend, http_backend (dict)
          * 服务配置:api_password, cors_origins, expose_docs
          * WARP 代理:warp_enabled, warp_mode, warp_socks_port
          * 频道配置:sources (dict[str, SourceChannelConfig])
        - 方法:
          * get_proxy() → str|None — 优先池随机选取,回退到单一代理
          * get_http_backend(source) → Literal — 获取指定源的 HTTP 后端
          * resolve_proxy/backend/api_key/base_url/headers/params(source) — 解析源特定配置

    get_config() → SouWenConfig
        - 功能:获取全局配置(LRU 缓存单例)
        - 返回:SouWenConfig 实例
        - 优先级:环境变量 > YAML > .env > 默认值

    reload_config() → SouWenConfig
        - 功能:清除缓存并重新加载配置(用于 Docker 动态更新)

    ensure_config_file() → Path | None
        - 功能:若无配置文件则自动生成默认配置到 ~/.config/souwen/config.yaml

配置优先级:
    1. 环境变量(SOUWEN_<FIELD_NAME>)— 最高
    2. ./souwen.yaml 或 ~/.config/souwen/config.yaml
    3. .env 文件
    4. 内置默认值 — 最低

环境变量特殊处理:
    - WARP_* 系列支持不带前缀(Docker entrypoint 兼容性)
    - 布尔字段:1/true/yes/on → True
    - 整数字段:自动转换
    - JSON 字段(http_backend、sources):JSON 解析

模块依赖:
    - pydantic: 配置验证和序列化
    - yaml: YAML 文件解析(可选)
    - dotenv: .env 文件加载
    - urllib.parse: 代理 URL 校验
"""

from __future__ import annotations

import json
import logging
import os
import random
from pathlib import Path
from functools import lru_cache
from typing import Literal
from urllib.parse import urlparse

from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger("souwen.config")

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore[assignment]


# 加载 .env 文件
load_dotenv()


# ==============================================================================
# 代理 URL 校验
# ==============================================================================
# 仅允许常见代理协议;禁止 file:// / javascript: 等潜在危险 scheme

_ALLOWED_PROXY_SCHEMES = {"http", "https", "socks5", "socks5h", "socks4", "socks4a"}


def _validate_proxy_url(url: str | None) -> str | None:
    """校验显式代理 URL 合法性

    非字符串 / 空串返回 None;非法则抛 ValueError.

    Args:
        url: 代理 URL 字符串

    Returns:
        合法的 URL 字符串,或 None(空值)

    Raises:
        ValueError: URL 格式错误或协议不被允许
    """
    if url is None:
        return None
    if not isinstance(url, str):
        raise ValueError(f"代理 URL 必须为字符串: {url!r}")
    u = url.strip()
    if not u:
        return None
    try:
        parsed = urlparse(u)
    except Exception as e:
        raise ValueError(f"非法的代理 URL: {url!r} ({e})") from e
    if parsed.scheme.lower() not in _ALLOWED_PROXY_SCHEMES:
        raise ValueError(
            f"不支持的代理协议 {parsed.scheme!r}: {url!r}(允许:{sorted(_ALLOWED_PROXY_SCHEMES)})"
        )
    if not parsed.hostname:
        raise ValueError(f"代理 URL 缺少 host: {url!r}")
    return u


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
                        perplexity_api_key, linkup_api_key, scrapingdog_api_key,
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

        WARP 代理: warp_enabled, warp_mode (auto|wireproxy|kernel),
                  warp_socks_port, warp_endpoint

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
    pubmed_api_key: str | None = None
    unpaywall_email: str | None = None
    ieee_api_key: str | None = None

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
    scrapingdog_api_key: str | None = None  # ScrapingDog SERP API
    whoogle_url: str | None = None  # Whoogle 自建实例 URL
    websurfx_url: str | None = None  # Websurfx 自建实例 URL
    # 社区 / 视频平台
    github_token: str | None = None  # GitHub PAT（可选，提升速率限制）
    stackoverflow_api_key: str | None = None  # StackOverflow API Key（可选，提升配额）
    youtube_api_key: str | None = None  # YouTube Data API v3 Key
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

    # ===== 通用 =====
    proxy: str | None = None
    proxy_pool: list[str] = []
    timeout: int = 30
    max_retries: int = 3
    data_dir: str = "~/.local/share/souwen"

    # ===== HTTP 后端 =====
    # 全局默认 HTTP 后端:auto(自动选择)| curl_cffi | httpx
    default_http_backend: str = "auto"
    # 按源覆盖,例如 {"duckduckgo": "httpx", "google_patents": "curl_cffi"}
    http_backend: dict[str, str] = Field(default_factory=dict)

    # ===== 服务（认证） =====
    api_password: str | None = None  # 旧版统一密码(向后兼容,同时作用于访客和管理)
    visitor_password: str | None = None  # 访客密码(保护搜索端点)
    admin_password: str | None = None  # 管理密码(保护管理端点)

    @property
    def effective_visitor_password(self) -> str | None:
        """解析生效的访客密码: visitor_password > api_password > None(开放)。
        显式设为空字符串表示"强制开放,忽略 api_password 回退"。"""
        if self.visitor_password is not None:
            return self.visitor_password or None
        return self.api_password

    @property
    def effective_admin_password(self) -> str | None:
        """解析生效的管理密码: admin_password > api_password > None(开放)。
        显式设为空字符串表示"强制开放,忽略 api_password 回退"。"""
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
    warp_mode: str = "auto"  # auto | wireproxy | kernel
    warp_socks_port: int = 1080
    warp_endpoint: str | None = None

    # ===== 数据源频道配置 =====
    sources: dict[str, SourceChannelConfig] = Field(default_factory=dict)

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


def _load_yaml_config() -> dict:
    """尝试加载 YAML 配置文件,返回扁平化的配置字典

    查找顺序:./souwen.yaml → ~/.config/souwen/config.yaml
    YAML 文件使用嵌套分组结构(paper:、patents: 等),加载后展平为与
    SouWenConfig 字段名一致的键值对,供 Pydantic 模型初始化.

    Returns:
        字典,键为配置字段名

    Warning:
        配置文件解析失败时返回空字典并记录日志,不中断程序
    """
    if yaml is None:
        return {}

    candidates = [
        Path("souwen.yaml"),
        Path("~/.config/souwen/config.yaml").expanduser(),
    ]

    raw: dict | None = None
    for path in candidates:
        if path.is_file():
            try:
                with open(path, encoding="utf-8") as f:
                    raw = yaml.safe_load(f)
            except (yaml.YAMLError, OSError) as exc:
                logger.warning("配置文件 %s 解析失败,已跳过: %s", path, exc)
                return {}
            break

    if not raw or not isinstance(raw, dict):
        return {}

    valid_fields = set(SouWenConfig.model_fields)
    flat: dict = {}
    for key, values in raw.items():
        if key == "sources" and isinstance(values, dict):
            # sources 是嵌套结构,直接传递给 Pydantic 解析
            flat["sources"] = values
        elif isinstance(values, dict):
            # 嵌套分组结构: paper: {openalex_email: ...}
            for k, v in values.items():
                if k in valid_fields:
                    flat[k] = v
        elif key in valid_fields:
            # 扁平结构: openalex_email: ...
            flat[key] = values
    return flat


@lru_cache(maxsize=1)
def get_config() -> SouWenConfig:
    """获取全局配置(LRU 缓存单例)

    配置加载优先级:环境变量 > YAML > .env > 默认值

    环境变量规则:
        - 标准字段:SOUWEN_<FIELD_NAME>(大小写不敏感)
        - 布尔字段:1/true/yes/on → True;0/false/no/off → False
        - 整数字段:自动转换
        - 列表字段:JSON 数组格式 "[...]" 或逗号分隔
        - WARP 字段:支持不带 SOUWEN_ 前缀(Docker entrypoint 兼容)

    Returns:
        SouWenConfig 实例(缓存的单例)

    Raises:
        ValueError: 环境变量格式无效或配置值非法

    Note:
        若需要重新加载配置,调用 reload_config().
    """
    # 先加载 YAML 配置(优先级低于环境变量)
    kwargs: dict = _load_yaml_config()

    # 环境变量覆盖 YAML 值
    env_prefix = "SOUWEN_"
    # WARP 相关字段也支持不带前缀的环境变量 (兼容 Docker entrypoint)
    _warp_env_aliases = {
        "warp_enabled": "WARP_ENABLED",
        "warp_mode": "WARP_MODE",
        "warp_socks_port": "WARP_SOCKS_PORT",
        "warp_endpoint": "WARP_ENDPOINT",
    }
    for field_name in SouWenConfig.model_fields:
        env_key = f"{env_prefix}{field_name.upper()}"
        val = os.getenv(env_key)
        # 回退到不带前缀的别名
        if val is None and field_name in _warp_env_aliases:
            val = os.getenv(_warp_env_aliases[field_name])
        if val is not None:
            field_info = SouWenConfig.model_fields[field_name]
            # 布尔字段
            if field_info.annotation is bool:
                val = val.lower() in ("1", "true", "yes", "on")
            # 整数字段
            elif field_info.annotation in (int, int | None):
                try:
                    val = int(val)
                except (ValueError, TypeError):
                    logger.warning("环境变量 %s=%r 无法转为整数,已忽略", env_key, val)
                    continue
            # proxy_pool / cors_origins / trusted_proxies: 逗号分隔字符串 → list[str]
            elif field_name in ("proxy_pool", "cors_origins", "trusted_proxies"):
                val = [p.strip() for p in val.split(",") if p.strip()]
            # http_backend: JSON 字符串 → dict[str, str]
            elif field_name == "http_backend":
                try:
                    parsed = json.loads(val)
                    if isinstance(parsed, dict):
                        val = parsed
                    else:
                        logger.warning("环境变量 %s 应为 JSON 对象,已忽略", env_key)
                        continue
                except json.JSONDecodeError:
                    logger.warning("环境变量 %s JSON 解析失败,已忽略", env_key)
                    continue
            # sources: JSON 字符串 → dict[str, SourceChannelConfig]
            elif field_name == "sources":
                try:
                    parsed = json.loads(val)
                    if isinstance(parsed, dict):
                        val = parsed
                    else:
                        logger.warning("环境变量 %s 应为 JSON 对象,已忽略", env_key)
                        continue
                except json.JSONDecodeError:
                    logger.warning("环境变量 %s JSON 解析失败,已忽略", env_key)
                    continue
            kwargs[field_name] = val

    return SouWenConfig(**kwargs)


def reload_config() -> SouWenConfig:
    """清除缓存并返回重新加载的配置

    重新读取 .env 文件但不覆盖已有的环境变量(override=False),
    这样 `docker run -e SOUWEN_API_PASSWORD=xxx` 不会被 .env 文件冲掉.
    用于 Docker 容器初始化或配置热更新场景.

    Returns:
        新加载的 SouWenConfig 实例
    """
    load_dotenv(override=False)
    get_config.cache_clear()
    return get_config()


# ---------------------------------------------------------------------------
# 默认配置模板（涵盖主要字段，详见 souwen.example.yaml 获取完整示例）
# ---------------------------------------------------------------------------
_DEFAULT_CONFIG_TEMPLATE = """\
# SouWen 配置文件(自动生成)
# 优先级:环境变量 > ./souwen.yaml > ~/.config/souwen/config.yaml > .env > 默认值

# ===== 论文数据源 =====
paper:
  openalex_email: ~
  semantic_scholar_api_key: ~
  core_api_key: ~
  pubmed_api_key: ~
  unpaywall_email: ~
  ieee_api_key: ~

# ===== 专利数据源 =====
patent:
  uspto_api_key: ~
  epo_consumer_key: ~
  epo_consumer_secret: ~
  cnipa_client_id: ~
  cnipa_client_secret: ~
  lens_api_token: ~
  patsnap_api_key: ~

# ===== 常规搜索 =====
web:
  searxng_url: ~
  tavily_api_key: ~
  exa_api_key: ~
  serper_api_key: ~
  brave_api_key: ~
  serpapi_api_key: ~
  firecrawl_api_key: ~
  perplexity_api_key: ~
  linkup_api_key: ~
  scrapingdog_api_key: ~
  whoogle_url: ~
  websurfx_url: ~
  github_token: ~
  stackoverflow_api_key: ~
  youtube_api_key: ~
  jina_api_key: ~
  scrapfly_api_key: ~
  diffbot_api_token: ~
  scrapingbee_api_key: ~
  zenrows_api_key: ~
  scraperapi_api_key: ~
  apify_api_token: ~
  cloudflare_api_token: ~
  cloudflare_account_id: ~

# ===== 通用设置 =====
general:
  proxy: ~
  proxy_pool: []
  timeout: 30
  max_retries: 3
  data_dir: ~/.local/share/souwen
  default_http_backend: auto
  http_backend: {}

# ===== 服务 =====
server:
  # 旧版统一密码（同时作用于访客和管理端点，向后兼容）
  api_password: ~
  # 访客密码（仅保护搜索端点，优先于 api_password）
  visitor_password: ~
  # 管理密码（仅保护管理端点，优先于 api_password）
  admin_password: ~
  # 允许跨域的来源列表（CORS Origins），留空表示不启用 CORS
  cors_origins: []
  # 受信反向代理 IP/CIDR 列表;只有来自这些地址的请求才会读取 X-Forwarded-For
  # 解析真实客户端 IP.不在此列表的直连客户端的 XFF 头将被忽略,避免伪造.
  # 示例: ["10.0.0.0/8", "172.16.0.0/12", "127.0.0.1"]
  trusted_proxies: []
  # 是否暴露 /docs、/redoc、/openapi.json;生产建议设为 false
  expose_docs: true

# ===== WARP 代理 =====
# 内嵌 Cloudflare WARP 代理(Docker 部署专用)
# 详见 scripts/warp-init.sh
warp:
  warp_enabled: false
  warp_mode: auto         # auto | wireproxy | kernel
  warp_socks_port: 1080
  warp_endpoint: ~        # 自定义 Endpoint (如 162.159.192.1:4500)

# ===== 数据源频道配置 =====
# 按源名称配置,覆盖全局默认值.
# 可用字段: enabled, proxy, http_backend, base_url, api_key, headers, params
# proxy 取值: inherit(继承全局) | none | warp | socks5://... | http://...
# 示例:
# sources:
#   duckduckgo:
#     enabled: true
#     proxy: warp
#     http_backend: curl_cffi
#   tavily:
#     api_key: tvly-xxxx
#     params:
#       search_depth: advanced
#   google_patents:
#     enabled: false
sources: {}
"""


def ensure_config_file() -> Path | None:
    """若不存在任何配置文件则自动生成一份到 ~/.config/souwen/config.yaml

    检查顺序:./souwen.yaml → ~/.config/souwen/config.yaml
    若都不存在,则创建 ~/.config/souwen/config.yaml(包含默认模板).

    Returns:
        配置文件路径(若成功生成)或 None(文件系统只读或其他错误)

    Note:
        用于初次设置或 Docker 容器首次启动时生成默认配置模板.
    """
    candidates = [
        Path("souwen.yaml"),
        Path("~/.config/souwen/config.yaml").expanduser(),
    ]
    for p in candidates:
        if p.is_file():
            return p

    target = Path("~/.config/souwen/config.yaml").expanduser()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(_DEFAULT_CONFIG_TEMPLATE, encoding="utf-8")
        return target
    except OSError:
        return None
