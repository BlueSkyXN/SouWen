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
    console.print("将以下配置添加到你的 AI Agent 的 MCP 配置文件中：\n")
    from rich import print_json

    print_json(json.dumps(config, indent=2))
    console.print("\n[dim]Claude Code: ~/.claude/claude_code_config.json[/dim]")
    console.print("[dim]Cursor: .cursor/mcp.json[/dim]")
