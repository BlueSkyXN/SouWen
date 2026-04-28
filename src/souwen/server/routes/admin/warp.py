"""WARP 代理管理与 Wayback 写入 — /admin/warp/*、/admin/wayback/save"""

from __future__ import annotations

import asyncio
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from fastapi import APIRouter, HTTPException, Query
from starlette.responses import StreamingResponse

from souwen.server.routes._common import logger
from souwen.server.schemas import WaybackSaveRequest, WaybackSaveResponse

router = APIRouter()


def _mask_proxy_url(proxy_url: str | None) -> str:
    """返回可展示的代理地址，避免泄露 URL 中的用户名和密码。"""
    if not proxy_url:
        return ""
    parsed = urlsplit(proxy_url)
    if "@" not in parsed.netloc:
        return proxy_url
    host = parsed.hostname or ""
    if parsed.port is not None:
        host = f"{host}:{parsed.port}"
    masked_netloc = f"***@{host}"
    return urlunsplit((parsed.scheme, masked_netloc, parsed.path, parsed.query, parsed.fragment))


@router.get("/warp")
async def warp_status():
    """获取 WARP 代理状态 — 包括模式、IP、PID 等。"""
    from souwen.server.warp import WarpManager

    mgr = WarpManager.get_instance()
    return mgr.get_status()


@router.get("/warp/modes")
async def warp_modes():
    """列出所有 WARP 模式的可用性和详细信息。"""
    from souwen.config import get_config
    from souwen.server.warp import WarpManager

    mgr = WarpManager.get_instance()
    cfg = get_config()
    has_wireproxy = mgr._has_wireproxy()
    has_kernel_wg = mgr._has_kernel_wg()
    has_usque = mgr._has_usque()
    has_warp_cli = mgr._has_warp_cli()
    has_external_proxy = bool(cfg.warp_external_proxy)

    modes = [
        {
            "id": "wireproxy",
            "name": "wireproxy (用户态)",
            "protocol": "wireguard",
            "installed": has_wireproxy,
            "requires_privilege": False,
            "docker_only": False,
            "proxy_types": ["socks5"],
            "description": "用户态 WireGuard → SOCKS5 代理，跨平台兼容，无需内核权限",
            "reason": "" if has_wireproxy else "wireproxy 二进制未找到",
        },
        {
            "id": "kernel",
            "name": "kernel (内核态)",
            "protocol": "wireguard",
            "installed": has_kernel_wg,
            "requires_privilege": True,
            "docker_only": False,
            "proxy_types": ["socks5"],
            "description": "Linux 内核 WireGuard + microsocks，高性能低延迟，需要 NET_ADMIN",
            "reason": "" if has_kernel_wg else "需要 wg (wireguard-tools) 和 microsocks",
        },
        {
            "id": "usque",
            "name": "usque (MASQUE/QUIC)",
            "protocol": "masque",
            "installed": has_usque,
            "requires_privilege": False,
            "docker_only": False,
            "proxy_types": ["socks5", "http"],
            "description": "MASQUE/QUIC 协议，现代化方案，支持 SOCKS5 和 HTTP 代理",
            "reason": ""
            if has_usque
            else "usque 二进制未找到 (需在 Docker 镜像中预装或手动安装到 PATH)",
        },
        {
            "id": "warp-cli",
            "name": "warp-cli (官方客户端)",
            "protocol": "official",
            "installed": has_warp_cli,
            "requires_privilege": True,
            "docker_only": True,
            "proxy_types": ["socks5", "http"],
            "description": "Cloudflare 官方客户端 + GOST，功能最全，仅 Docker 可用",
            "reason": "" if has_warp_cli else "warp-cli 未安装 (仅 Docker 可用)",
        },
        {
            "id": "external",
            "name": "外部代理",
            "protocol": "any",
            "installed": True,
            "configured": has_external_proxy,
            "requires_privilege": False,
            "docker_only": False,
            "proxy_types": ["socks5", "http"],
            "description": "连接外部 WARP 代理容器，零侵入，适合 sidecar 架构",
            "external_proxy": _mask_proxy_url(cfg.warp_external_proxy),
            "reason": "" if has_external_proxy else "未配置 warp_external_proxy 地址",
        },
    ]
    return {"modes": modes}


@router.post("/warp/enable")
async def warp_enable(
    mode: str = Query(
        "auto",
        description="模式: auto | wireproxy | kernel | usque | warp-cli | external",
    ),
    socks_port: int = Query(1080, ge=1, le=65535, description="SOCKS5 端口"),
    http_port: int = Query(0, ge=0, le=65535, description="HTTP 代理端口（0=不启用）"),
    endpoint: str | None = Query(None, description="自定义 WARP Endpoint"),
):
    """启用 WARP 代理 — 支持 auto、wireproxy、kernel、usque、warp-cli、external 模式。"""
    from souwen.server.warp import WarpManager

    mgr = WarpManager.get_instance()
    result = await mgr.enable(
        mode=mode,
        socks_port=socks_port,
        http_port=http_port,
        endpoint=endpoint,
    )
    if not result["ok"]:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.post("/warp/register")
async def warp_register(
    backend: str = Query("wgcf", description="注册后端: wgcf | usque"),
):
    """注册新的 Cloudflare WARP 账号。

    支持 wgcf（WireGuard 配置）和 usque（MASQUE 配置）两种注册方式。
    """
    from souwen.server.warp import WarpManager

    mgr = WarpManager.get_instance()

    if backend == "usque":
        import shutil

        usque_bin = shutil.which("usque")
        if not usque_bin:
            raise HTTPException(status_code=400, detail="usque 未安装")
        config_path = "/app/data/usque-config.json"
        Path(config_path).parent.mkdir(parents=True, exist_ok=True)
        success = await mgr._usque_register(usque_bin, config_path)
        if success:
            return {"ok": True, "backend": "usque", "config_path": config_path}
        raise HTTPException(status_code=500, detail="usque 注册失败（可能触发速率限制）")

    if backend == "wgcf":
        result = await asyncio.to_thread(mgr._wgcf_register)
        if result:
            return {"ok": True, "backend": "wgcf", "config_path": str(result)}
        raise HTTPException(status_code=500, detail="wgcf 注册失败（可能触发速率限制）")

    raise HTTPException(status_code=400, detail=f"未知注册后端: {backend}")


@router.post("/warp/test")
async def warp_test():
    """测试当前 WARP 代理连接 — 返回出口 IP 和 WARP 状态。"""
    from souwen.server.warp import WarpManager

    mgr = WarpManager.get_instance()
    status = mgr.get_status()

    if status["status"] != "enabled":
        raise HTTPException(status_code=400, detail="WARP 未启用")

    if status["mode"] == "external":
        from souwen.config import get_config

        proxy_url = get_config().warp_external_proxy or ""
        alive = await asyncio.to_thread(mgr._check_external_proxy_alive, proxy_url)
        ip = await asyncio.to_thread(mgr._get_external_proxy_ip, proxy_url) if alive else "unknown"
        port = status["socks_port"]
    else:
        port = status["socks_port"]
        alive = await asyncio.to_thread(mgr._check_socks_alive, port)
        ip = await asyncio.to_thread(mgr._get_warp_ip, port) if alive else "unknown"

    return {
        "ok": alive,
        "ip": ip,
        "port": port,
        "mode": status["mode"],
        "protocol": status.get("protocol", "wireguard"),
        "proxy_type": status.get("proxy_type", "socks5"),
    }


@router.get("/warp/config")
async def warp_config():
    """获取当前 WARP 相关配置项。"""
    from souwen.config import get_config

    cfg = get_config()
    return {
        "warp_enabled": cfg.warp_enabled,
        "warp_mode": cfg.warp_mode,
        "warp_socks_port": cfg.warp_socks_port,
        "warp_http_port": cfg.warp_http_port,
        "warp_endpoint": cfg.warp_endpoint,
        "warp_bind_address": cfg.warp_bind_address,
        "warp_startup_timeout": cfg.warp_startup_timeout,
        "warp_device_name": cfg.warp_device_name,
        "warp_usque_transport": cfg.warp_usque_transport,
        "warp_usque_system_dns": cfg.warp_usque_system_dns,
        "warp_usque_on_connect": cfg.warp_usque_on_connect,
        "warp_usque_on_disconnect": cfg.warp_usque_on_disconnect,
        "warp_external_proxy": _mask_proxy_url(cfg.warp_external_proxy),
        "warp_usque_path": cfg.warp_usque_path,
        "warp_usque_config": cfg.warp_usque_config,
        "warp_gost_args": cfg.warp_gost_args,
        "has_license_key": bool(cfg.warp_license_key),
        "has_team_token": bool(cfg.warp_team_token),
        "has_proxy_auth": bool(cfg.warp_proxy_username and cfg.warp_proxy_password),
    }


@router.post("/warp/disable")
async def warp_disable():
    """禁用 WARP 代理 — 清理进程和网络配置。"""
    from souwen.server.warp import WarpManager

    mgr = WarpManager.get_instance()
    result = await mgr.disable()
    if not result["ok"]:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.get("/warp/components")
async def warp_components():
    """获取 WARP 组件安装状态列表。"""
    from souwen.server.warp_installer import WarpInstaller

    installer = WarpInstaller()
    return {"components": installer.get_components_status()}


@router.post("/warp/components/install")
async def warp_component_install(
    component: str = Query(..., description="组件名: usque | wireproxy | wgcf"),
    version: str | None = Query(None, description="版本号 (如 3.0.0)，留空使用默认版本"),
):
    """从 GitHub Releases 下载安装 WARP 组件。"""
    from souwen.server.warp_installer import WarpInstaller

    installer = WarpInstaller()
    try:
        result = await installer.install(component, version)
        return result
    except ValueError as e:
        logger.warning("组件安装参数错误: %s — %s", component, e)
        raise HTTPException(status_code=400, detail=f"参数错误: {component}") from e
    except Exception as e:
        logger.exception("组件安装失败: %s", component)
        raise HTTPException(
            status_code=500, detail=f"安装 {component} 失败，请查看服务端日志"
        ) from e


@router.post("/warp/components/uninstall")
async def warp_component_uninstall(
    component: str = Query(..., description="组件名"),
):
    """卸载运行时安装的 WARP 组件（不影响系统预装）。"""
    from souwen.server.warp_installer import WarpInstaller

    installer = WarpInstaller()
    try:
        result = await installer.uninstall(component)
        return result
    except ValueError as e:
        logger.warning("组件卸载参数错误: %s — %s", component, e)
        raise HTTPException(status_code=400, detail=f"参数错误: {component}") from e
    except Exception as e:
        logger.exception("组件卸载失败: %s", component)
        raise HTTPException(
            status_code=500, detail=f"卸载 {component} 失败，请查看服务端日志"
        ) from e


@router.post("/warp/switch")
async def warp_switch(
    mode: str = Query(..., description="目标模式"),
    socks_port: int = Query(1080, ge=1, le=65535),
    http_port: int = Query(0, ge=0, le=65535),
    endpoint: str | None = Query(None),
):
    """一步切换 WARP 模式 — 先禁用当前模式，再以目标模式启用。"""
    from souwen.server.warp import WarpManager

    mgr = WarpManager.get_instance()

    status = mgr.get_status()
    if status["status"] in ("enabled", "starting", "error"):
        disable_result = await mgr.disable()
        if not disable_result["ok"]:
            logger.error("WARP 禁用失败: %s", disable_result.get("error"))
            raise HTTPException(status_code=500, detail="禁用当前模式失败，请查看服务端日志")

    result = await mgr.enable(
        mode=mode,
        socks_port=socks_port,
        http_port=http_port,
        endpoint=endpoint,
    )
    if not result["ok"]:
        logger.warning("WARP 切换失败: %s → %s", mode, result.get("error"))
        raise HTTPException(status_code=400, detail=f"切换到 {mode} 模式失败")
    safe_result = {k: v for k, v in result.items() if k != "error"}
    return safe_result


@router.get("/warp/events")
async def warp_events():
    """SSE 实时推送 WARP 状态变化。

    每 2 秒推送一次当前状态。客户端使用 EventSource 连接。
    """
    from souwen.server.warp import WarpManager

    async def event_stream():
        mgr = WarpManager.get_instance()
        last_status = None
        heartbeat = 0
        while True:
            try:
                current = mgr.get_status()
                status_key = (current["status"], current["mode"], current["ip"])
                heartbeat += 1
                if status_key != last_status or heartbeat >= 10:
                    import json

                    data = json.dumps(current, ensure_ascii=False)
                    yield f"data: {data}\n\n"
                    last_status = status_key
                    heartbeat = 0
                await asyncio.sleep(2)
            except asyncio.CancelledError:
                break
            except Exception:
                break

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# Wayback Machine — 写入操作（管理认证）
# ---------------------------------------------------------------------------


@router.post("/wayback/save", response_model=WaybackSaveResponse)
async def api_wayback_save(body: WaybackSaveRequest):
    """触发 Wayback Machine 立即存档 — 需要管理认证。"""
    from souwen.web.wayback import WaybackClient

    try:
        client = WaybackClient()
        resp = await asyncio.wait_for(
            client.save_page(url=body.url, timeout=body.timeout),
            timeout=body.timeout + 15,
        )
        return {
            "url": body.url,
            "success": resp.success,
            "snapshot_url": resp.snapshot_url,
            "timestamp": resp.timestamp,
            "error": resp.error,
        }
    except asyncio.TimeoutError:
        logger.warning("Wayback save 超时: url=%s timeout=%ss", body.url, body.timeout)
        raise HTTPException(status_code=504, detail=f"存档超时（{body.timeout}s）")
    except Exception:
        logger.warning("Wayback save 错误: url=%s", body.url, exc_info=True)
        raise
