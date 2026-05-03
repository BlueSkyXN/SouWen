"""tools/gen_docs.py 回归测试。"""

from __future__ import annotations

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
