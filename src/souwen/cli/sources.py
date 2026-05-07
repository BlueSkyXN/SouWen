"""sources 命令：列出所有数据源"""

from __future__ import annotations

import json

import typer
from rich.table import Table

from souwen.cli import app
from souwen.cli._common import console


@app.command("sources")
def list_sources(
    json_output: bool = typer.Option(False, "--json", "-j", help="以 Source Catalog JSON 输出"),
    available_only: bool = typer.Option(False, "--available-only", help="仅列出当前配置下可用源"),
    category: str | None = typer.Option(None, "--category", help="按正式 catalog category 过滤"),
    capability: str | None = typer.Option(None, "--capability", help="按能力过滤，如 search/fetch"),
) -> None:
    """列出公开 Source Catalog。"""
    from souwen.config import get_config
    from souwen.registry.catalog import public_source_catalog_payload
    from souwen.registry.meta import (
        AUTH_REQUIREMENT_LABELS,
        DISTRIBUTION_LABELS,
        RISK_LEVEL_LABELS,
    )

    payload = public_source_catalog_payload(get_config())
    category_keys = {item["key"] for item in payload["categories"]}
    if category is not None and category not in category_keys:
        console.print(f"[red]未知 category: {category}[/red]")
        raise typer.Exit(1)

    sources = list(payload["sources"])
    if available_only:
        sources = [item for item in sources if item["available"]]
    if category is not None:
        sources = [item for item in sources if item["category"] == category]
    if capability is not None:
        sources = [item for item in sources if capability in item["capabilities"]]

    payload = {**payload, "sources": sources}
    if json_output:
        typer.echo(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return

    table = Table(title="📚 SouWen Source Catalog", show_lines=True)
    table.add_column("Name", style="cyan")
    table.add_column("Domain", style="blue")
    table.add_column("Category", style="yellow")
    table.add_column("Capabilities", style="magenta")
    table.add_column("Auth", justify="center")
    table.add_column("Creds", justify="center")
    table.add_column("Available", justify="center")
    table.add_column("Risk", justify="center")
    table.add_column("Dist", justify="center")
    table.add_column("Description", style="dim")

    for item in sources:
        auth = AUTH_REQUIREMENT_LABELS.get(item["auth_requirement"], item["auth_requirement"])
        risk = RISK_LEVEL_LABELS.get(item["risk_level"], item["risk_level"])
        dist = DISTRIBUTION_LABELS.get(item["distribution"], item["distribution"])
        table.add_row(
            item["name"],
            item["domain"],
            item["category"],
            ", ".join(item["capabilities"]) or "-",
            auth,
            "✅" if item["configured_credentials"] else "⬜",
            "✅" if item["available"] else "🚫",
            risk,
            dist,
            item["description"],
        )

    console.print(table)
