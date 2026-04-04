"""SouWen 统一配置管理

优先级从高到低：
1. 环境变量
2. 项目根目录 .env 文件
3. ~/.config/souwen/config.toml（可选）
4. 内置默认值
"""

from __future__ import annotations

import os
from pathlib import Path
from functools import lru_cache

from dotenv import load_dotenv
from pydantic import BaseModel


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


@lru_cache(maxsize=1)
def get_config() -> SouWenConfig:
    """获取全局配置（单例）"""
    env_prefix = "SOUWEN_"
    kwargs: dict = {}

    # 遍历所有配置字段，从环境变量 SOUWEN_<FIELD_NAME> 读取覆盖值
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
