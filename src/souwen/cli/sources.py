"""sources 命令：列出所有数据源"""

from __future__ import annotations

from rich.table import Table

from souwen.cli import app
from souwen.cli._common import console


@app.command("sources")
def list_sources() -> None:
    """列出所有可用数据源"""
    from souwen.registry.meta import (
        AUTH_REQUIREMENT_LABELS,
        DISTRIBUTION_LABELS,
        RISK_LEVEL_LABELS,
    )
    from souwen.registry.catalog import source_catalog

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
    table.add_column("Key Req", justify="center")
    table.add_column("Risk", justify="center")
    table.add_column("Dist", justify="center")
    table.add_column("Description", style="dim")

    for name, meta in source_catalog().items():
        key_indicator = AUTH_REQUIREMENT_LABELS.get(meta.auth_requirement, meta.auth_requirement)
        integration = _INTEGRATION_SHORT.get(meta.integration_type, meta.integration_type)
        risk = RISK_LEVEL_LABELS.get(meta.risk_level, meta.risk_level)
        dist = DISTRIBUTION_LABELS.get(meta.distribution, meta.distribution)
        table.add_row(name, meta.category, integration, key_indicator, risk, dist, meta.description)

    console.print(table)
