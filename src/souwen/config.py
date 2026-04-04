"""SouWen 统一配置管理

优先级从高到低：
1. 环境变量（SOUWEN_<FIELD_NAME>）
2. 项目根目录 ./souwen.yaml
3. ~/.config/souwen/config.yaml
4. 项目根目录 .env 文件
5. 内置默认值
"""

from __future__ import annotations

import os
from pathlib import Path
from functools import lru_cache

from dotenv import load_dotenv
from pydantic import BaseModel

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
    searxng_url: str | None = None        # SearXNG 自建实例 URL
    tavily_api_key: str | None = None     # Tavily AI 搜索
    exa_api_key: str | None = None        # Exa 语义搜索
    serper_api_key: str | None = None     # Serper (Google SERP)
    brave_api_key: str | None = None      # Brave Search 官方 API

    # ===== 通用 =====
    proxy: str | None = None
    timeout: int = 30
    max_retries: int = 3
    data_dir: str = "~/.local/share/souwen"

    @property
    def data_path(self) -> Path:
        """返回展开后的数据目录路径"""
        return Path(self.data_dir).expanduser()


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
            with open(path, encoding="utf-8") as f:
                raw = yaml.safe_load(f)
            break

    if not raw or not isinstance(raw, dict):
        return {}

    valid_fields = set(SouWenConfig.model_fields)
    flat: dict = {}
    for _group, values in raw.items():
        if isinstance(values, dict):
            for k, v in values.items():
                if k in valid_fields:
                    flat[k] = v
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
                val = int(val)
            kwargs[field_name] = val

    return SouWenConfig(**kwargs)


def reload_config() -> SouWenConfig:
    """清除缓存并返回重新加载的配置"""
    get_config.cache_clear()
    return get_config()
