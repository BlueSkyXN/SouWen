"""Citation-enrichment CLI commands."""

from __future__ import annotations

import asyncio
import json

import typer
from rich.table import Table

from souwen.cli._common import _run_async, console, redact_cli_text

citation_app = typer.Typer(help="OpenCitations 引用计数与引文图谱 enrichment")


def _run(coro, *, identifier: str, timeout: int):
    try:
        return _run_async(asyncio.wait_for(coro, timeout=timeout))
    except asyncio.TimeoutError:
        console.print(f"[red]⏱ citation enrichment 超时 (>{timeout}s)[/red]")
        raise typer.Exit(124) from None
    except Exception as exc:
        console.print(f"[red]❌ citation enrichment 失败: {redact_cli_text(exc)}[/red]")
        raise typer.Exit(1) from None


def _print_json(response) -> None:
    from rich import print_json

    print_json(json.dumps(response.model_dump(mode="json"), ensure_ascii=False))


@citation_app.command("count")
def citation_count(
    identifier: str = typer.Argument(..., help="DOI、PMID 或 OMID identifier"),
    json_output: bool = typer.Option(False, "--json", "-j"),
    timeout: int = typer.Option(30, "--timeout", "-t", min=1, max=120),
) -> None:
    """Query one work's OpenCitations incoming-citation count."""
    from souwen.citations import get_citation_count

    response = _run(get_citation_count(identifier), identifier=identifier, timeout=timeout)
    if json_output:
        _print_json(response)
        return
    console.print(
        f"[bold]OpenCitations count[/bold] {response.identifier.canonical}: {response.count}"
    )


def _graph_command(
    relation: str,
    identifier: str,
    max_edges: int,
    json_output: bool,
    timeout: int,
) -> None:
    from souwen.citations import get_incoming_citations, get_references

    call = get_incoming_citations if relation == "incoming" else get_references
    response = _run(call(identifier, max_edges=max_edges), identifier=identifier, timeout=timeout)
    if json_output:
        _print_json(response)
        return
    console.print(
        f"[bold]OpenCitations {relation}[/bold] {response.identifier.canonical}: "
        f"{response.returned_edges}/{response.total_edges} edges"
    )
    if response.truncated:
        console.print("[yellow]输出已按本地 max_edges 截断；这不是 upstream pagination。[/yellow]")
    table = Table(show_lines=True)
    table.add_column("OCI", style="cyan")
    table.add_column("Citing", max_width=45)
    table.add_column("Cited", max_width=45)
    table.add_column("Creation")
    for edge in response.edges:
        table.add_row(edge.oci, edge.citing_raw, edge.cited_raw, edge.creation or "")
    console.print(table)


@citation_app.command("incoming")
def citation_incoming(
    identifier: str = typer.Argument(..., help="DOI、PMID 或 OMID identifier"),
    max_edges: int = typer.Option(100, "--max-edges", "-n", min=1, max=1000),
    json_output: bool = typer.Option(False, "--json", "-j"),
    timeout: int = typer.Option(30, "--timeout", "-t", min=1, max=120),
) -> None:
    """Query incoming citation edges with a local output cap."""
    _graph_command("incoming", identifier, max_edges, json_output, timeout)


@citation_app.command("references")
def citation_references(
    identifier: str = typer.Argument(..., help="DOI、PMID 或 OMID identifier"),
    max_edges: int = typer.Option(100, "--max-edges", "-n", min=1, max=1000),
    json_output: bool = typer.Option(False, "--json", "-j"),
    timeout: int = typer.Option(30, "--timeout", "-t", min=1, max=120),
) -> None:
    """Query outgoing reference edges with a local output cap."""
    _graph_command("references", identifier, max_edges, json_output, timeout)
