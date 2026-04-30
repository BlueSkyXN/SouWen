"""配置加载与单例缓存

负责 .env 加载、YAML 文件读取、环境变量覆盖以及全局缓存单例.
"""

from __future__ import annotations

import json
import logging
import os
from functools import lru_cache
from pathlib import Path

from dotenv import dotenv_values

from .models import SouWenConfig
from .template import _DEFAULT_CONFIG_TEMPLATE

logger = logging.getLogger("souwen.config")

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore[assignment]


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
        if key in ("sources", "llm") and isinstance(values, dict):
            # sources / llm 是嵌套结构,直接传递给 Pydantic 解析
            flat[key] = values
        elif isinstance(values, dict):
            # 嵌套分组结构: paper: {openalex_email: ...}
            for k, v in values.items():
                if k in valid_fields:
                    flat[k] = v
        elif key in valid_fields:
            # 扁平结构: openalex_email: ...
            flat[key] = values
    return flat


_WARP_ENV_ALIASES = {
    "warp_enabled": "WARP_ENABLED",
    "warp_mode": "WARP_MODE",
    "warp_socks_port": "WARP_SOCKS_PORT",
    "warp_endpoint": "WARP_ENDPOINT",
    "warp_bind_address": "WARP_BIND_ADDRESS",
    "warp_startup_timeout": "WARP_STARTUP_TIMEOUT",
    "warp_device_name": "WARP_DEVICE_NAME",
    "warp_proxy_username": "WARP_PROXY_USERNAME",
    "warp_proxy_password": "WARP_PROXY_PASSWORD",
    "warp_usque_path": "WARP_USQUE_PATH",
    "warp_usque_config": "WARP_USQUE_CONFIG",
    "warp_usque_transport": "WARP_USQUE_TRANSPORT",
    "warp_usque_system_dns": "WARP_USQUE_SYSTEM_DNS",
    "warp_usque_on_connect": "WARP_USQUE_ON_CONNECT",
    "warp_usque_on_disconnect": "WARP_USQUE_ON_DISCONNECT",
    "warp_http_port": "WARP_HTTP_PORT",
    "warp_license_key": "WARP_LICENSE_KEY",
    "warp_team_token": "WARP_TEAM_TOKEN",
    "warp_gost_args": "WARP_GOST_ARGS",
    "warp_external_proxy": "WARP_EXTERNAL_PROXY",
}


def _coerce_env_value(field_name: str, raw_val: str, env_key: str):
    """按 SouWenConfig 字段类型解析环境变量 / .env 字符串值。"""
    val = raw_val
    field_info = SouWenConfig.model_fields[field_name]
    if field_info.annotation is bool:
        return val.lower() in ("1", "true", "yes", "on")
    if field_info.annotation in (int, int | None):
        try:
            return int(val)
        except (ValueError, TypeError):
            logger.warning("环境变量 %s=%r 无法转为整数,已忽略", env_key, val)
            return None
    if field_name in ("proxy_pool", "cors_origins", "trusted_proxies", "plugins"):
        stripped = val.strip()
        if stripped.startswith("["):
            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError:
                logger.warning("环境变量 %s JSON 解析失败,已忽略", env_key)
                return None
            if not isinstance(parsed, list):
                logger.warning("环境变量 %s 应为 JSON 数组,已忽略", env_key)
                return None
            return [str(p).strip() for p in parsed if str(p).strip()]
        return [p.strip() for p in val.split(",") if p.strip()]
    if field_name == "http_backend":
        try:
            parsed = json.loads(val)
        except json.JSONDecodeError:
            logger.warning("环境变量 %s JSON 解析失败,已忽略", env_key)
            return None
        if isinstance(parsed, dict):
            return parsed
        logger.warning("环境变量 %s 应为 JSON 对象,已忽略", env_key)
        return None
    if field_name == "sources":
        try:
            parsed = json.loads(val)
        except json.JSONDecodeError:
            logger.warning("环境变量 %s JSON 解析失败,已忽略", env_key)
            return None
        if isinstance(parsed, dict):
            return parsed
        logger.warning("环境变量 %s 应为 JSON 对象,已忽略", env_key)
        return None
    if field_name == "llm":
        try:
            parsed = json.loads(val)
        except json.JSONDecodeError:
            logger.warning("环境变量 %s JSON 解析失败,已忽略", env_key)
            return None
        if isinstance(parsed, dict):
            return parsed
        logger.warning("环境变量 %s 应为 JSON 对象,已忽略", env_key)
        return None
    return val


def _load_env_mapping(values: dict[str, str | None]) -> dict:
    """将 .env 或 os.environ 的键值映射为 SouWenConfig kwargs。"""
    kwargs: dict = {}
    env_prefix = "SOUWEN_"
    for field_name in SouWenConfig.model_fields:
        env_key = f"{env_prefix}{field_name.upper()}"
        val = values.get(env_key)
        alias_key = None
        if val is None and field_name in _WARP_ENV_ALIASES:
            alias_key = _WARP_ENV_ALIASES[field_name]
            val = values.get(alias_key)
        if val is None:
            continue
        source_key = alias_key or env_key
        parsed = _coerce_env_value(field_name, val, source_key)
        if parsed is not None:
            kwargs[field_name] = parsed
    return kwargs


def _load_dotenv_config() -> dict:
    """加载当前目录 .env，优先级低于 YAML，且不污染 os.environ。"""
    path = Path(".env")
    if not path.is_file():
        return {}
    return _load_env_mapping(dotenv_values(path))


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
    kwargs: dict = _load_dotenv_config()
    kwargs.update(_load_yaml_config())
    kwargs.update(_load_env_mapping(dict(os.environ)))

    cfg = SouWenConfig(**kwargs)

    # 配置加载完成后，加载 config.plugins 中手动指定的插件
    if cfg.plugins:
        try:
            from souwen.plugin import load_config_plugins

            load_config_plugins(cfg.plugins)
        except Exception:  # noqa: BLE001 — 插件加载不能拖垮配置
            logger.warning("配置插件加载失败,已跳过", exc_info=True)

    return cfg


def reload_config() -> SouWenConfig:
    """清除缓存并返回重新加载的配置

    清理缓存后重新按 环境变量 > YAML > .env > 默认值 的顺序加载配置。

    Returns:
        新加载的 SouWenConfig 实例
    """
    get_config.cache_clear()
    return get_config()


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
