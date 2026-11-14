"""SouWen 统一配置管理(子包)"""

from __future__ import annotations

from .loader import (
    _load_yaml_config,
    ensure_config_file,
    get_config,
    reload_config,
)
from .models import (
    DEFAULT_SEARCH_PROVIDERS,
    SEARCH_DOMAINS,
    SourceChannelConfig,
    SouWenConfig,
)
from .template import _DEFAULT_CONFIG_TEMPLATE
from .validators import _ALLOWED_PROXY_SCHEMES, _validate_proxy_url

__all__ = [
    "DEFAULT_SEARCH_PROVIDERS",
    "SEARCH_DOMAINS",
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
