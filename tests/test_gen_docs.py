"""tools/gen_docs.py 回归测试。"""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys

from tools import gen_docs


def test_cli_render_excludes_runtime_plugin_after_registry_import(clean_registry):
    from souwen.registry.adapter import MethodSpec, SourceAdapter
    from souwen.registry.loader import lazy
    from souwen.registry.views import _reg_external

    plugin_name = "gen_docs_runtime_probe"
    adapter = SourceAdapter(
        name=plugin_name,
        domain="fetch",
        integration="scraper",
        description="gen docs runtime probe",
        config_field=None,
        client_loader=lazy("souwen.web.builtin:BuiltinFetcherClient"),
        methods={"fetch": MethodSpec("fetch")},
        needs_config=False,
    )

    assert _reg_external(adapter) is True
    assert plugin_name in gen_docs.render(include_plugins=True)
    assert plugin_name not in gen_docs.render_cli_content(include_plugins=False)


def test_checked_in_data_sources_matches_generator():
    docs_path = Path("docs/data-sources.md")
    assert docs_path.read_text(encoding="utf-8") == gen_docs.render_cli_content(
        include_plugins=False
    )


def test_check_flag_accepts_checked_in_data_sources():
    result = subprocess.run(
        [
            sys.executable,
            "tools/gen_docs.py",
            "--check",
        ],
        check=False,
        encoding="utf-8",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert result.returncode == 0, result.stderr
