"""mcp 命令：显示 MCP Server 配置"""

from __future__ import annotations

import json

from souwen.cli import app
from souwen.cli._common import console


@app.command("mcp")
def mcp_info() -> None:
    """显示 MCP Server 配置信息（用于 Claude Code / Cursor 集成）"""
    import sys

    config = {
        "mcpServers": {
            "souwen": {
                "command": sys.executable,
                "args": ["-m", "souwen.integrations.mcp_server"],
            }
        }
    }
    console.print("[bold]📡 SouWen MCP Server 配置[/bold]\n")

    # --- stdio 配置 ---
    console.print("[bold cyan]1. Stdio 模式（默认）[/bold cyan]")
    console.print("将以下配置添加到你的 AI Agent 的 MCP 配置文件中：\n")
    from rich import print_json

    print_json(json.dumps(config, indent=2))
    console.print("\n[dim]Claude Code: ~/.claude/claude_code_config.json[/dim]")
    console.print("[dim]Cursor: .cursor/mcp.json[/dim]")

    # --- HTTP 网络端点提示 ---
    console.print("\n[bold cyan]2. HTTP 网络模式（可选）[/bold cyan]")
    console.print(
        "启用后，MCP 客户端可通过 HTTP 连接 SouWen 服务端：\n"
        "  • Streamable HTTP: [green]http://<host>:<port>/mcp[/green]\n"
        "  • SSE:             [green]http://<host>:<port>/mcp/sse[/green]\n"
    )
    console.print("通过环境变量开启：")
    console.print("  [yellow]SOUWEN_MCP_HTTP_ENABLED=true[/yellow]       # 启用网络 MCP")
    console.print("  [dim]SOUWEN_MCP_HTTP_ENABLE_SSE=true[/dim]    # 额外启用 SSE（默认 true）")
    console.print("  [dim]SOUWEN_MCP_HTTP_STATELESS=true[/dim]     # SHTTP 无状态模式（默认 true）")
    console.print("  [dim]SOUWEN_MCP_HTTP_JSON_RESPONSE=true[/dim]  # SHTTP JSON 响应（默认 true）")
    console.print(
        "\n[dim]鉴权：复用现有 User/Admin Bearer Token，Guest 不可访问 MCP 网络端点。[/dim]"
    )
