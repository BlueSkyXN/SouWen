"""SouWen 统一配置管理(子包)

将原 souwen.config 模块拆分为多个文件以提升可维护性,
对外 API 完全保持兼容.

子模块:
    validators: 代理 URL 校验 (_ALLOWED_PROXY_SCHEMES, _validate_proxy_url)
    models:     Pydantic 配置模型 (SourceChannelConfig, SouWenConfig)
    template:   默认 YAML 模板字符串 (_DEFAULT_CONFIG_TEMPLATE)
    loader:     .env / YAML 加载与缓存单例 (get_config, reload_config,
                ensure_config_file, _load_yaml_config)

配置优先级:
    1. 环境变量(SOUWEN_<FIELD_NAME>)— 最高
    2. ./souwen.yaml 或 ~/.config/souwen/config.yaml
    3. .env 文件
    4. 内置默认值 — 最低
"""

from __future__ import annotations

from .loader import (
    _load_yaml_config,
    ensure_config_file,
    get_config,
    reload_config,
)
from .models import SourceChannelConfig, SouWenConfig
from .template import _DEFAULT_CONFIG_TEMPLATE
from .validators import _ALLOWED_PROXY_SCHEMES, _validate_proxy_url

__all__ = [
    "SouWenConfig",
    "SourceChannelConfig",
    "get_config",
    "reload_config",
    "ensure_config_file",
    "_validate_proxy_url",
    "_ALLOWED_PROXY_SCHEMES",
    "_load_yaml_config",
    "_DEFAULT_CONFIG_TEMPLATE",
]
