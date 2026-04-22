"""配置加载与单例缓存

负责 .env 加载、YAML 文件读取、环境变量覆盖以及全局缓存单例.
"""

from __future__ import annotations

import json
import logging
import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

from .models import SouWenConfig
from .template import _DEFAULT_CONFIG_TEMPLATE

logger = logging.getLogger("souwen.config")

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore[assignment]


# 加载 .env 文件
load_dotenv()


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
