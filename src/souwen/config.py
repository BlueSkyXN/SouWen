"""SouWen 统一配置管理

优先级从高到低：
1. 环境变量（SOUWEN_<FIELD_NAME>）
2. 项目根目录 ./souwen.yaml
3. ~/.config/souwen/config.yaml
4. 项目根目录 .env 文件
5. 内置默认值
"""

from __future__ import annotations

import logging
import os
import random
from pathlib import Path
from functools import lru_cache

from dotenv import load_dotenv
from pydantic import BaseModel

logger = logging.getLogger("souwen.config")

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore[assignment]


# 加载 .env 文件
load_dotenv()


class SouWenConfig(BaseModel):
    """全局配置"""

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

    # ===== 通用 =====
    proxy: str | None = None
    proxy_pool: list[str] = []
    timeout: int = 30
    max_retries: int = 3
    data_dir: str = "~/.local/share/souwen"

    # ===== 服务 =====
    api_password: str | None = None  # API 访问密码（Bearer Token）

    @property
    def data_path(self) -> Path:
        """返回展开后的数据目录路径"""
        return Path(self.data_dir).expanduser()

    def get_proxy(self) -> str | None:
        """返回代理地址：优先从 proxy_pool 随机选取，否则回退到 proxy"""
        if self.proxy_pool:
            return random.choice(self.proxy_pool)
        return self.proxy


def _load_yaml_config() -> dict:
    """尝试加载 YAML 配置文件，返回扁平化的配置字典。

    查找顺序：./souwen.yaml → ~/.config/souwen/config.yaml
    YAML 文件使用嵌套分组结构，加载后展平为与 SouWenConfig 字段名一致的键值对。
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
                logger.warning("配置文件 %s 解析失败，已跳过: %s", path, exc)
                return {}
            break

    if not raw or not isinstance(raw, dict):
        return {}

    valid_fields = set(SouWenConfig.model_fields)
    flat: dict = {}
    for key, values in raw.items():
        if isinstance(values, dict):
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
    """获取全局配置（单例）"""
    # 先加载 YAML 配置（优先级低于环境变量）
    kwargs: dict = _load_yaml_config()

    # 环境变量覆盖 YAML 值
    env_prefix = "SOUWEN_"
    for field_name in SouWenConfig.model_fields:
        env_key = f"{env_prefix}{field_name.upper()}"
        val = os.getenv(env_key)
        if val is not None:
            # 对整数字段做类型转换
            field_info = SouWenConfig.model_fields[field_name]
            if field_info.annotation in (int, int | None):
                try:
                    val = int(val)
                except (ValueError, TypeError):
                    logger.warning("环境变量 %s=%r 无法转为整数，已忽略", env_key, val)
                    continue
            # proxy_pool: 逗号分隔字符串 → list[str]
            elif field_name == "proxy_pool":
                val = [p.strip() for p in val.split(",") if p.strip()]
            kwargs[field_name] = val

    return SouWenConfig(**kwargs)


def reload_config() -> SouWenConfig:
    """清除缓存并返回重新加载的配置。

    重新读取 .env 但不覆盖已有的环境变量（override=False），
    这样 ``docker run -e SOUWEN_API_PASSWORD=xxx`` 不会被 .env 文件冲掉。
    """
    load_dotenv(override=False)
    get_config.cache_clear()
    return get_config()


# ---------------------------------------------------------------------------
# 默认配置模板（与 souwen.example.yaml 保持一致）
# ---------------------------------------------------------------------------
_DEFAULT_CONFIG_TEMPLATE = """\
# SouWen 配置文件（自动生成）
# 优先级：环境变量 > ./souwen.yaml > ~/.config/souwen/config.yaml > .env > 默认值

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

# ===== 通用设置 =====
general:
  proxy: ~
  proxy_pool: []
  timeout: 30
  max_retries: 3
  data_dir: ~/.local/share/souwen

# ===== 服务 =====
server:
  api_password: ~
"""


def ensure_config_file() -> Path | None:
    """若不存在任何配置文件则自动生成一份到 ~/.config/souwen/config.yaml。

    在只读文件系统上静默跳过，返回 None。
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
