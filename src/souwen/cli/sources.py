"""sources 命令：列出所有数据源"""

from __future__ import annotations

from rich.table import Table

from souwen.cli import app
from souwen.cli._common import console


@app.command("sources")
def list_sources() -> None:
    """列出所有可用数据源"""
    from souwen.source_registry import get_all_sources

    _INTEGRATION_SHORT = {
        "open_api": "公开",
        "scraper": "爬虫",
        "official_api": "授权",
        "self_hosted": "自建",
    }

    table = Table(title="📚 SouWen 数据源", show_lines=True)
    table.add_column("Name", style="cyan")
    table.add_column("Category", style="yellow")
    table.add_column("Integration", style="magenta")
    table.add_column("Needs Key", justify="center")
    table.add_column("Description", style="dim")

    for name, meta in get_all_sources().items():
        needs_key = meta.config_field is not None
        key_indicator = "🔑" if needs_key else "✅"
        integration = _INTEGRATION_SHORT.get(meta.integration_type, meta.integration_type)
        table.add_row(name, meta.category, integration, key_indicator, meta.description)

    console.print(table)
