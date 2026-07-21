"""Local catalog initialization, import and status commands."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from souwen.cli._common import console
from souwen.core.exceptions import SouWenError

catalog_app = typer.Typer(help="管理本地 SQLite catalog 与官方 metadata 导入")


def _status_payload() -> dict[str, object]:
    from souwen.config import get_config
    from souwen.local_catalog import LocalCatalog

    status = LocalCatalog(get_config().local_catalog_db_path).status()
    return {
        "path": str(status.path),
        "initialized": status.initialized,
        "schema_version": status.schema_version,
        "fts5_available": status.fts5_available,
        "integrity": status.integrity,
        "source_counts": status.source_counts,
        "completed_imports": status.completed_imports,
        "latest_imports": status.latest_imports,
    }


@catalog_app.command("status")
def catalog_status(json_output: bool = typer.Option(False, "--json", help="输出 JSON")) -> None:
    """显示 local catalog schema、FTS、完整性和 import run 摘要。"""
    try:
        payload = _status_payload()
    except SouWenError as exc:
        console.print(f"[red]✗ {exc}[/red]")
        raise typer.Exit(1) from exc
    if json_output:
        typer.echo(json.dumps(payload, ensure_ascii=False))
        return
    console.print_json(json.dumps(payload, ensure_ascii=False))


@catalog_app.command("import")
def catalog_import(
    source: str = typer.Argument(..., help="当前仅支持 gutenberg"),
    input_path: Path | None = typer.Argument(None, help="本地官方 RDF/XML 或 rdf-files.tar.bz2"),
    url: str | None = typer.Option(None, "--url", help="显式下载官方 Gutenberg catalog URL"),
    resume: bool = typer.Option(False, "--resume", help="从同一失败 import run checkpoint 恢复"),
    replace_source: bool = typer.Option(
        False, "--replace-source", help="确认输入为完整 snapshot 后删除已不存在的记录"
    ),
    json_output: bool = typer.Option(False, "--json", help="输出 JSON"),
) -> None:
    """导入 Project Gutenberg 官方 RDF metadata；绝不下载 ebook 正文。"""
    if source != "gutenberg":
        raise typer.BadParameter("当前仅支持 gutenberg", param_hint="source")
    if (input_path is None) == (url is None):
        raise typer.BadParameter("必须二选一提供本地 input_path 或 --url")
    from souwen.config import get_config
    from souwen.local_catalog import LocalCatalog
    from souwen.local_catalog.gutenberg import (
        download_official_gutenberg_catalog,
        import_gutenberg_input,
    )

    cfg = get_config()
    catalog = LocalCatalog(cfg.local_catalog_db_path)
    try:
        if url is not None:
            suffix = ".rdf" if url.endswith(".rdf") else ".tar.bz2"
            input_path = cfg.data_path / "catalog-inputs" / f"gutenberg{suffix}"
            receipt = download_official_gutenberg_catalog(url, input_path)
            acquisition = {
                "url": receipt.url,
                "content_length": receipt.content_length,
                "last_modified": receipt.last_modified,
                "observed_sha256": receipt.sha256,
                "retrieved_at": receipt.retrieved_at,
            }
        else:
            assert input_path is not None
            if not input_path.is_file():
                raise typer.BadParameter(
                    f"input does not exist: {input_path}", param_hint="input_path"
                )
            acquisition = {"url": None}
        counters = import_gutenberg_input(
            catalog,
            input_path,
            resume=resume,
            replace_source=replace_source,
            acquisition=acquisition,
        )
        payload = {
            "source": source,
            "input": str(input_path),
            "acquisition": acquisition,
            **counters,
        }
    except (SouWenError, OSError, ValueError) as exc:
        console.print(f"[red]✗ catalog import failed: {exc}[/red]")
        raise typer.Exit(1) from exc
    if json_output:
        typer.echo(json.dumps(payload, ensure_ascii=False))
    else:
        console.print_json(json.dumps(payload, ensure_ascii=False))
