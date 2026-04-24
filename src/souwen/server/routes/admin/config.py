"""管理端配置查看与重载 — /admin/config、/admin/config/reload、/admin/config/yaml"""

from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import APIRouter, HTTPException

from souwen.server.routes._common import _is_secret_field
from souwen.server.schemas import ConfigReloadResponse, YamlConfigResponse, YamlConfigSaveRequest

router = APIRouter()

_YAML_CANDIDATES = [
    Path("souwen.yaml"),
    Path("~/.config/souwen/config.yaml").expanduser(),
]

# 配置写入锁 — 防止并发写入冲突
_CONFIG_WRITE_LOCK = asyncio.Lock()


def _find_config_path() -> Path | None:
    """返回当前存在的配置文件路径，不存在返回 None。"""
    for p in _YAML_CANDIDATES:
        if p.is_file():
            return p
    return None


@router.get("/config")
async def get_config_view():
    """查看当前配置（敏感字段脱敏）— 管理端点。"""
    from souwen.config import SouWenConfig, get_config

    cfg = get_config()
    result = {}
    for field_name in SouWenConfig.model_fields:
        val = getattr(cfg, field_name)
        if _is_secret_field(field_name) and val is not None:
            result[field_name] = "***"
        else:
            result[field_name] = val
    return result


@router.post("/config/reload", response_model=ConfigReloadResponse)
async def reload_config_endpoint():
    """重新加载配置 — 从 YAML + .env 重新读取。"""
    from souwen.config import reload_config

    cfg = reload_config()
    return {
        "status": "ok",
        "password_set": cfg.effective_admin_password is not None,
    }


@router.get("/config/yaml", response_model=YamlConfigResponse)
async def get_config_yaml():
    """获取原始 YAML 配置文件内容 — 管理端点。

    若未找到配置文件，返回内置默认模板（path 为 None）。
    """
    try:
        import yaml as _yaml  # noqa: F401
    except ImportError:
        raise HTTPException(status_code=500, detail="PyYAML 未安装，无法读取 YAML 配置")

    path = _find_config_path()
    if path is None:
        from souwen.config.template import _DEFAULT_CONFIG_TEMPLATE

        return YamlConfigResponse(content=_DEFAULT_CONFIG_TEMPLATE, path=None)

    try:
        content = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"读取配置文件失败: {exc}")

    return YamlConfigResponse(content=content, path=str(path))


@router.put("/config/yaml", response_model=YamlConfigResponse)
async def save_config_yaml(body: YamlConfigSaveRequest):
    """保存 YAML 配置文件并重载 — 管理端点。

    先校验 YAML 语法和 Pydantic 模型，再写入配置文件，最后重载并返回结果。
    若当前无配置文件，写入 ~/.config/souwen/config.yaml。
    并发写入由 asyncio.Lock 保护。
    """
    async with _CONFIG_WRITE_LOCK:
        try:
            import yaml as _yaml
        except ImportError:
            raise HTTPException(status_code=500, detail="PyYAML 未安装，无法写入 YAML 配置")

        # 语法校验
        try:
            parsed_dict = _yaml.safe_load(body.content) or {}
        except _yaml.YAMLError as exc:
            raise HTTPException(status_code=422, detail=f"YAML 语法错误: {exc}")

        # Pydantic 模型校验（dry-run）
        # parsed_dict 是嵌套结构 {paper: {...}, web: {...}, ...}，
        # 而 SouWenConfig 期望扁平字段名，需先扁平化（与 loader._load_yaml_config 一致）
        try:
            from souwen.config import SouWenConfig

            valid_fields = set(SouWenConfig.model_fields)
            flat_dict: dict = {}
            for key, values in parsed_dict.items():
                if key == "sources" and isinstance(values, dict):
                    flat_dict["sources"] = values
                elif isinstance(values, dict):
                    for k, v in values.items():
                        if k in valid_fields:
                            flat_dict[k] = v
                elif key in valid_fields:
                    flat_dict[key] = values

            SouWenConfig(**flat_dict)
        except Exception as exc:
            raise HTTPException(status_code=422, detail=f"配置校验失败: {exc}")

        # 确定写入路径
        target = _find_config_path()
        if target is None:
            target = Path("~/.config/souwen/config.yaml").expanduser()
            target.parent.mkdir(parents=True, exist_ok=True)

        try:
            target.write_text(body.content, encoding="utf-8")
        except OSError as exc:
            raise HTTPException(status_code=500, detail=f"写入配置文件失败: {exc}")

        # 重载配置（可能失败）
        from souwen.config import reload_config

        try:
            reload_config()
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail=f"配置重载失败（文件已写入）: {exc}，请手动检查配置文件或重启服务",
            )

        return YamlConfigResponse(content=body.content, path=str(target))
