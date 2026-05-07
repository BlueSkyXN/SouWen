"""tools/gen_docs.py — 从 registry 派生数据源清单文档

输出 `docs/data-sources.md` 的 Markdown 表格。未来在 CI 里做 diff 校验。

用法：
    python tools/gen_docs.py                   # 打印
    python tools/gen_docs.py -o docs/data-sources.md  # 写入文件
    python tools/gen_docs.py --check           # 校验 docs/data-sources.md 是否最新
"""

from __future__ import annotations

import argparse
import difflib
import os
import subprocess
import sys
from pathlib import Path


DOMAIN_TITLES = {
    "paper": "学术论文",
    "patent": "专利",
    "web": "通用网页搜索",
    "social": "社交平台",
    "video": "视频平台",
    "knowledge": "百科/知识库",
    "developer": "开发者社区",
    "cn_tech": "中文技术社区",
    "office": "企业/办公",
    "archive": "档案/历史",
    "fetch": "内容抓取",
}


def _configure_cli_stdio() -> None:
    """Use UTF-8 for CLI output so generated Chinese docs work on Windows."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8")


def render(*, include_plugins: bool = False) -> str:
    """渲染 docs/data-sources.md 的 Markdown 内容。

    ``include_plugins=False`` 只会阻止本次首次导入 registry 时自动加载外部插件；
    若调用前 registry 已在当前进程被插件污染，请使用 CLI 默认路径或
    ``render_cli_content()``，它会在需要时开新子进程隔离 runtime 状态。
    """
    old_autoload = os.environ.get("SOUWEN_PLUGIN_AUTOLOAD")
    if not include_plugins:
        # Checked-in docs should be reproducible even when local development
        # environments have third-party souwen.plugins entry points installed.
        os.environ["SOUWEN_PLUGIN_AUTOLOAD"] = "0"

    try:
        from souwen.registry import all_adapters, all_domains, external_plugins
        from souwen.registry.catalog import public_source_catalog, source_categories
        from souwen.registry.meta import (
            AUTH_REQUIREMENT_LABELS,
            DISTRIBUTION_LABELS,
            OPTIONAL_CREDENTIAL_EFFECT_LABELS,
            RISK_LEVEL_LABELS,
            STABILITY_LABELS,
        )
    finally:
        if not include_plugins:
            if old_autoload is None:
                os.environ.pop("SOUWEN_PLUGIN_AUTOLOAD", None)
            else:
                os.environ["SOUWEN_PLUGIN_AUTOLOAD"] = old_autoload

    loaded_adapters = all_adapters()
    external_names = set(external_plugins())
    public_catalog = public_source_catalog()
    adapters = {
        name: adapter
        for name, adapter in loaded_adapters.items()
        if name in public_catalog and (include_plugins or name not in external_names)
    }
    visible_external_count = len(external_names) if include_plugins else 0
    hidden_or_internal_count = len(loaded_adapters) - len(public_catalog)
    category_labels = {category.key: category.label for category in source_categories()}

    lines: list[str] = []
    lines.append("# SouWen 数据源指南与清单")
    lines.append("")
    lines.append(
        f"**总计**：**{len(adapters)}** 个公开数据源（从正式 Source Catalog 自动生成；"
        f"其中外部插件 **{visible_external_count}** 个，隐藏/内部源 **{hidden_or_internal_count}** 个）。"
    )
    lines.append("")
    lines.append("## 事实来源")
    lines.append("")
    lines.append(
        "本页不是手工维护的静态表，而是由 `src/souwen/registry/sources/` 中的 "
        "`SourceAdapter` 声明投影为正式 Source Catalog 后，经 `tools/gen_docs.py` 生成。"
        "`SourceAdapter` 同时驱动 CLI、REST API、doctor、Panel 和插件视图。"
    )
    lines.append("")
    lines.append(
        "默认生成只包含内置源，并显式关闭外部插件自动加载；这样即使本机安装了 "
        "`souwen.plugins` entry point，checked-in 文档也能稳定复现。需要把本机插件一并"
        "展示时再使用 `--include-plugins`。"
    )
    lines.append("")
    lines.append("## 如何阅读")
    lines.append("")
    lines.append(
        "- 本页主表按 registry domain 展示：`paper` / `patent` / `web` / `social` / "
        "`video` / `knowledge` / `developer` / `cn_tech` / `office` / `archive` / `fetch`。"
    )
    lines.append(
        "- 正式 Source Catalog 使用展示分类："
        + " / ".join(f"`{key}`（{label}）" for key, label in category_labels.items())
        + "。"
    )
    lines.append(
        "- `/api/v1/sources` 和 Panel 在过渡期仍使用兼容分类：`general` / `professional` "
        "会拆分 `web` 源，`knowledge` 显示为 `wiki`，`archive` 与跨域抓取能力归入 `fetch`。"
    )
    lines.append(
        "- `Capabilities` 是门面层可派发能力；`fetch` 既可以是主 domain，也可以是 "
        "`tavily` / `firecrawl` / `exa` / `xcrawl` / `wayback` 等源的跨域能力。"
    )
    lines.append("")
    lines.append("## 配置口径")
    lines.append("")
    lines.append(
        "- Auth 的取值是 `none` / `optional` / `required` / `self_hosted`。"
        "`optional` 表示缺凭据仍可用，但配置后可提升限流、配额、质量或登录态能力；"
        "`required` 与 `self_hosted` 缺少声明字段时不会出现在 `/api/v1/sources`。"
    )
    lines.append(
        "- `Credentials` 列出完整字段；多字段源必须全部满足。频道级 "
        "`sources.<name>.api_key` 只覆盖主 `config_field`，其余字段仍读取 flat config。"
    )
    lines.append(
        "- 自建实例源优先读取 `sources.<name>.base_url`，并兼容旧的 "
        "`sources.<name>.api_key` 与 flat `<name>_url`。当前内置自建源为 "
        "`searxng`、`whoogle`、`websurfx`。"
    )
    lines.append(
        "- `Risk` 只描述默认调度风险，不等同于接入方式；`Distribution` 描述推荐安装/"
        "治理边界；`Extra` 是推荐安装的 optional dependency 组。"
    )
    lines.append("")
    lines.append("## 运行时可见性")
    lines.append("")
    lines.append(
        "`/api/v1/sources` 会从 live registry 派生，并过滤已禁用、缺必需凭据或缺自建实例"
        "地址的源；doctor 和管理端 `/api/v1/admin/sources/config` 会展示所有注册源及其"
        "状态、凭据字段、频道配置和 catalog 元数据。"
    )
    lines.append("")
    lines.append("<!-- BEGIN AUTO -->")
    lines.append("")

    visible_domains = [
        dom for dom in all_domains() if any(dom in adapter.domains for adapter in adapters.values())
    ]
    for dom in visible_domains:
        dom_adapters = sorted(
            [a for a in adapters.values() if dom in a.domains],
            key=lambda a: a.name,
        )
        title = DOMAIN_TITLES.get(dom, dom)
        lines.append(f"## {title} · `{dom}`（{len(dom_adapters)} 源）")
        lines.append("")
        lines.append(
            "| Name | Integration | Auth | Risk | Distribution | Stability | Extra | "
            "Capabilities | Credentials |"
        )
        lines.append("|---|---|---|---|---|---|---|---|---|")
        for a in dom_adapters:
            caps = ", ".join(sorted(a.capabilities))
            credentials = ", ".join(f"`{f}`" for f in a.resolved_credential_fields) or "—"
            high_risk = " ⚠️" if "high_risk" in a.tags else ""
            auth = AUTH_REQUIREMENT_LABELS.get(
                a.resolved_auth_requirement, a.resolved_auth_requirement
            )
            if a.optional_credential_effect:
                effect = OPTIONAL_CREDENTIAL_EFFECT_LABELS.get(
                    a.optional_credential_effect, a.optional_credential_effect
                )
                auth = f"{auth} ({effect})"
            risk = RISK_LEVEL_LABELS.get(a.resolved_risk_level, a.resolved_risk_level)
            distribution = (
                "plugin"
                if include_plugins and a.name in external_names
                else a.resolved_distribution
            )
            dist = DISTRIBUTION_LABELS.get(distribution, distribution)
            stability = STABILITY_LABELS.get(a.resolved_stability, a.resolved_stability)
            extra = f"`{a.resolved_package_extra}`" if a.resolved_package_extra else "—"
            lines.append(
                f"| `{a.name}`{high_risk} | {a.integration} | {auth} | {risk} | {dist} | "
                f"{stability} | {extra} | {caps} | {credentials} |"
            )
        lines.append("")

    lines.append("<!-- END AUTO -->")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 图例")
    lines.append("")
    lines.append("- ⚠️ high_risk：兼容旧标签，等价于 `risk_level=high`。")
    lines.append(
        "- Integration 描述接入方式：`open_api` / `scraper` / `official_api` / `self_hosted`。"
    )
    lines.append("- Auth 描述运行前配置要求：免配置 / 可选凭据 / 必须凭据 / 自建实例。")
    lines.append("- Risk 描述默认调度风险，不等同于 Integration。")
    lines.append("- Distribution 描述推荐治理/安装范围：核心内置 / 可选依赖 / 外部插件。")
    lines.append("- Extra 表示建议安装的 optional dependency 组。")
    lines.append("- Stability 描述接入成熟度：稳定 / Beta / 实验性 / 已弃用。")
    lines.append("")
    lines.append("## 重新生成与校验")
    lines.append("")
    lines.append("```bash")
    lines.append("PYTHONPATH=src python3 tools/gen_docs.py -o docs/data-sources.md")
    lines.append("PYTHONPATH=src python3 tools/gen_docs.py --check")
    lines.append("```")
    lines.append("")
    lines.append("如需在本机 catalog 中展示已安装的外部插件，可追加 `--include-plugins`。")
    return "\n".join(lines) + "\n"


def render_cli_content(*, include_plugins: bool = False) -> str:
    if include_plugins or "souwen.registry" not in sys.modules:
        return render(include_plugins=include_plugins)

    env = os.environ.copy()
    env["SOUWEN_PLUGIN_AUTOLOAD"] = "0"
    env["PYTHONIOENCODING"] = "utf-8"
    proc = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), "--_render-only"],
        check=True,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        encoding="utf-8",
        text=True,
    )
    return proc.stdout


def main() -> int:
    _configure_cli_stdio()
    parser = argparse.ArgumentParser()
    parser.add_argument("-o", "--output", type=Path, help="写入文件；缺省则打印到 stdout")
    parser.add_argument(
        "--check",
        action="store_true",
        help="校验目标文件是否与 registry 生成结果一致；默认检查 docs/data-sources.md",
    )
    parser.add_argument(
        "--include-plugins",
        action="store_true",
        help="包含当前环境已加载的外部 souwen.plugins entry point；默认只生成内置源",
    )
    parser.add_argument("--_render-only", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()

    content = (
        render(include_plugins=args.include_plugins)
        if args._render_only
        else render_cli_content(include_plugins=args.include_plugins)
    )
    if args.check:
        target = args.output or Path("docs/data-sources.md")
        if not target.exists():
            print(
                f"ERROR: {target} does not exist; run: "
                f"PYTHONPATH=src python3 tools/gen_docs.py -o {target}",
                file=sys.stderr,
            )
            return 1
        current = target.read_text(encoding="utf-8")
        if current == content:
            print(f"OK: {target} is up to date")
            return 0
        print(
            f"ERROR: {target} is out of date; regenerate it with:",
            file=sys.stderr,
        )
        print(f"  PYTHONPATH=src python3 tools/gen_docs.py -o {target}", file=sys.stderr)
        diff = difflib.unified_diff(
            current.splitlines(keepends=True),
            content.splitlines(keepends=True),
            fromfile=str(target),
            tofile="generated",
        )
        sys.stderr.writelines(diff)
        return 1
    if args.output:
        args.output.write_text(content, encoding="utf-8")
        print(f"OK: wrote {args.output}")
    else:
        sys.stdout.write(content)
    return 0


if __name__ == "__main__":
    sys.exit(main())
