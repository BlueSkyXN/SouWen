"""serve 命令：启动 API 服务"""

from __future__ import annotations

import typer

from souwen.cli import app
from souwen.cli._common import console


@app.command("serve")
def serve(
    host: str = typer.Option("0.0.0.0", help="监听地址"),
    port: int = typer.Option(8000, help="监听端口"),
    reload: bool = typer.Option(False, help="开发模式自动重载"),
) -> None:
    """启动 API 服务"""
    try:
        import uvicorn
    except ImportError:
        console.print('[red]❌ 需要安装 server 依赖: pip install -e ".[server]"[/red]')
        raise typer.Exit(1)

    from souwen.logging_config import setup_logging

    setup_logging()

    from souwen.config import get_config
    from souwen.server.auth import is_admin_open_enabled

    cfg = get_config()
    console.print("[bold]━━━ SouWen 启动配置 ━━━[/bold]")
    # 访客密码状态
    v_pw = cfg.effective_visitor_password
    v_color = "green" if v_pw else "red"
    v_text = "已启用" if v_pw else "未启用（开放访问）"
    console.print(f"  访客密码:        [{v_color}]{v_text}[/]")
    # 管理密码状态
    a_pw = cfg.effective_admin_password
    admin_open = is_admin_open_enabled()
    a_color = "green" if a_pw else "yellow" if admin_open else "red"
    a_text = "已启用" if a_pw else "未启用（显式开放）" if admin_open else "未启用（默认锁定）"
    console.print(f"  管理密码:        [{a_color}]{a_text}[/]")
    console.print(f"  Docs:            {'已开放' if cfg.expose_docs else '已隐藏'}")
    console.print(
        f"  Trusted proxies: {', '.join(cfg.trusted_proxies) if cfg.trusted_proxies else '(未配置)'}"
    )
    console.print(
        f"  CORS origins:    {', '.join(cfg.cors_origins) if cfg.cors_origins else '(未配置)'}"
    )
    console.print(f"  监听:            http://{host}:{port}")
    console.print("[bold]━━━━━━━━━━━━━━━━━━━━━━[/bold]\n")

    uvicorn.run("souwen.server.app:app", host=host, port=port, reload=reload)
