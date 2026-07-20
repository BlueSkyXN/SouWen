"""tools/gen_docs.py — 从 registry 派生数据源文档

生成 `docs/data-sources.md`，并维护 README / architecture 中受控的 registry 摘要。

用法：
    python tools/gen_docs.py                   # 打印
    python tools/gen_docs.py -o docs/data-sources.md  # 只写数据源清单
    python tools/gen_docs.py --write           # 重建全部受控文档
    python tools/gen_docs.py --check           # 校验全部受控文档
"""

from __future__ import annotations

import argparse
import difflib
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

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

README_METRICS_MARKER = "SOURCE METRICS"
ARCHITECTURE_METRICS_MARKER = "REGISTRY SUMMARY"
ARCHITECTURE_CROSS_DOMAIN_MARKER = "CROSS-DOMAIN FETCH SOURCES"

DEFAULT_DATA_SOURCES_PATH = Path("docs/data-sources.md")


@dataclass(frozen=True, slots=True)
class RegistrySnapshot:
    """Registry-derived counts and adapter views used by all generated surfaces."""

    adapters: dict[str, Any]
    public_names: frozenset[str]
    external_names: frozenset[str]
    domains: tuple[str, ...]
    primary_counts: dict[str, int]
    fetch_primary: tuple[Any, ...]
    fetch_cross_domain: tuple[Any, ...]

    @property
    def registered_count(self) -> int:
        return len(self.adapters)

    @property
    def public_count(self) -> int:
        return len(self.public_names)

    @property
    def hidden_or_internal_count(self) -> int:
        return self.registered_count - self.public_count

    @property
    def visible_external_count(self) -> int:
        return len(self.external_names & self.public_names)

    @property
    def fetch_provider_count(self) -> int:
        return len(self.fetch_primary) + len(self.fetch_cross_domain)


def _configure_cli_stdio() -> None:
    """Use UTF-8 for CLI output so generated Chinese docs work on Windows."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8")


def _load_snapshot(*, include_plugins: bool = False) -> tuple[RegistrySnapshot, Any, Any]:
    """Load one deterministic registry snapshot and the catalog presentation metadata."""

    old_autoload = os.environ.get("SOUWEN_PLUGIN_AUTOLOAD")
    if not include_plugins:
        # Checked-in docs should be reproducible even when local development
        # environments have third-party souwen.plugins entry points installed.
        os.environ["SOUWEN_PLUGIN_AUTOLOAD"] = "0"

    try:
        from souwen.registry import all_adapters, all_domains, external_plugins
        from souwen.registry.catalog import public_source_catalog, source_categories
    finally:
        if not include_plugins:
            if old_autoload is None:
                os.environ.pop("SOUWEN_PLUGIN_AUTOLOAD", None)
            else:
                os.environ["SOUWEN_PLUGIN_AUTOLOAD"] = old_autoload

    loaded_adapters = all_adapters()
    external_names = frozenset(external_plugins())
    public_catalog = public_source_catalog()
    public_names = frozenset(
        name for name in public_catalog if include_plugins or name not in external_names
    )
    adapters = {
        name: adapter
        for name, adapter in loaded_adapters.items()
        if include_plugins or name not in external_names
    }
    domains = tuple(all_domains())
    primary_counts = {
        domain: sum(
            adapter.domain == domain and name in public_names for name, adapter in adapters.items()
        )
        for domain in domains
    }
    fetch_primary = tuple(
        sorted(
            (
                adapter
                for name, adapter in adapters.items()
                if name in public_names and adapter.domain == "fetch"
            ),
            key=lambda adapter: adapter.name,
        )
    )
    fetch_cross_domain = tuple(
        sorted(
            (
                adapter
                for name, adapter in adapters.items()
                if name in public_names and "fetch" in adapter.extra_domains
            ),
            key=lambda adapter: adapter.name,
        )
    )
    snapshot = RegistrySnapshot(
        adapters=adapters,
        public_names=public_names,
        external_names=external_names if include_plugins else frozenset(),
        domains=domains,
        primary_counts=primary_counts,
        fetch_primary=fetch_primary,
        fetch_cross_domain=fetch_cross_domain,
    )
    return snapshot, public_catalog, source_categories


def render(*, include_plugins: bool = False) -> str:
    """渲染 docs/data-sources.md 的 Markdown 内容。

    ``include_plugins=False`` 只会阻止本次首次导入 registry 时自动加载外部插件；
    若调用前 registry 已在当前进程被插件污染，请使用 CLI 默认路径或
    ``render_cli_content()``，它会在需要时开新子进程隔离 runtime 状态。
    """
    snapshot, public_catalog, source_categories = _load_snapshot(include_plugins=include_plugins)

    from souwen.registry.meta import (
        AUTH_REQUIREMENT_LABELS,
        DISTRIBUTION_LABELS,
        OPTIONAL_CREDENTIAL_EFFECT_LABELS,
        RISK_LEVEL_LABELS,
        STABILITY_LABELS,
    )

    loaded_adapters = snapshot.adapters
    external_names = snapshot.external_names
    adapters = {
        name: adapter for name, adapter in loaded_adapters.items() if name in snapshot.public_names
    }
    category_labels = {category.key: category.label for category in source_categories()}

    lines: list[str] = []
    lines.append("# SouWen 数据源指南与清单")
    lines.append("")
    lines.append("## Registry 指标")
    lines.append("")
    lines.append("| 指标 | 数量 | 定义 |")
    lines.append("|---|---:|---|")
    lines.append(
        f"| Registered | **{snapshot.registered_count}** | 当前生成进程注册的 "
        "`SourceAdapter`；默认只含内置源 |"
    )
    lines.append(
        f"| Public | **{snapshot.public_count}** | `catalog_visibility=public`，进入公开 "
        "Source Catalog |"
    )
    lines.append(
        f"| Hidden / internal | **{snapshot.hidden_or_internal_count}** | 已注册但不进入公开 "
        "Source Catalog |"
    )
    lines.append(
        f"| Fetch primary-domain | **{len(snapshot.fetch_primary)}** | 主 `domain=fetch` 的公开源 |"
    )
    lines.append(
        f"| Fetch cross-domain | **{len(snapshot.fetch_cross_domain)}** | 其他主 domain 通过 "
        "`extra_domains` 暴露 `fetch` |"
    )
    lines.append(
        f"| Fetch providers | **{snapshot.fetch_provider_count}** | primary-domain 与 "
        "cross-domain 的公开源并集 |"
    )
    if include_plugins:
        lines.append(
            f"| Visible external plugins | **{snapshot.visible_external_count}** | 本次通过 "
            "`--include-plugins` 纳入的公开插件源 |"
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
        "- `/api/v1/sources`、CLI 和 Panel 使用同一份公开 Source Catalog："
        "`sources[]` 保留全部公开条目，并用 `category`、`domain`、`capabilities`、"
        "`available` 描述展示和运行时可用性。"
    )
    lines.append(
        "- `Capabilities` 是门面层可派发能力；`fetch` 既可以属于主 domain，也可以由"
        "其他主 domain 源通过 `extra_domains` 声明为跨域能力。具体名单和计数均从 "
        "registry 派生。"
    )
    lines.append("")
    lines.append("## 配置口径")
    lines.append("")
    lines.append(
        "- Auth 的取值是 `none` / `optional` / `required` / `self_hosted`。"
        "`optional` 表示缺凭据仍可用，但配置后可提升限流、配额、质量或登录态能力；"
        "`required` 与 `self_hosted` 缺少声明字段时仍保留 catalog 条目，并以 "
        "`available=false` 标记。"
    )
    lines.append(
        "- `Credentials` 列出完整字段；多字段源必须全部满足。频道级 "
        "`sources.<name>.api_key` 只覆盖主 `config_field`，其余字段仍读取 flat config。"
    )
    lines.append(
        "- 自建实例源读取 `sources.<name>.base_url`；当前内置自建源为 "
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
        "`/api/v1/sources` 会从 live registry 派生公开 catalog，禁用源、缺必需凭据源"
        "和缺自建实例地址的源仍会保留条目，但 `available=false`；doctor 和管理端 "
        "`/api/v1/admin/sources/config` 会展示所有注册源及其状态、凭据字段、频道配置"
        "和 catalog 元数据。"
    )
    lines.append("")
    lines.append(
        "`stability` 是 registry 声明的接入成熟度，不是实时连通性承诺；"
        "`/api/v1/sources[].available` 只表示当前 edition、启用状态和凭据条件满足，"
        "也不证明上游此刻可达。doctor 默认 `live=false`，只有显式 live probe 的"
        "结果才描述当次联网观测。"
    )
    lines.append("")
    lines.append("<!-- BEGIN AUTO -->")
    lines.append("")

    visible_domains = [
        dom
        for dom in snapshot.domains
        if any(dom in adapter.domains for adapter in adapters.values())
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
    lines.append("- ⚠️ high_risk：高风险源，等价于 `risk_level=high`。")
    lines.append(
        "- Integration 描述接入方式：`open_api` / `scraper` / `official_api` / `self_hosted`。"
    )
    lines.append("- Auth 描述运行前配置要求：免配置 / 可选凭据 / 必须凭据 / 自建实例。")
    lines.append("- Risk 描述默认调度风险，不等同于 Integration。")
    lines.append("- Distribution 描述推荐治理/安装范围：核心内置 / 可选依赖 / 外部插件。")
    lines.append("- Extra 表示建议安装的 optional dependency 组。")
    lines.append(
        "- Stability 描述声明式接入成熟度：稳定 / Beta / 实验性 / 已弃用；"
        "不等于实时可用性或可达性。"
    )
    lines.append("")
    lines.append("## 重新生成与校验")
    lines.append("")
    lines.append("```bash")
    lines.append("PYTHONPATH=src python3 tools/gen_docs.py --write")
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


def _primary_domain_metrics(snapshot: RegistrySnapshot, *, english: bool) -> str:
    domain_counts = [
        f"`{domain}` {snapshot.primary_counts[domain]}"
        for domain in snapshot.domains
        if domain != "fetch"
    ]
    separator = " · "
    prefix = "Public sources by primary domain: " if english else "公开源主 domain："
    return prefix + separator.join(domain_counts)


def _readme_metrics(snapshot: RegistrySnapshot, *, english: bool) -> str:
    if english:
        lines = [
            (
                f"- **{snapshot.registered_count} registered built-in sources**: "
                f"**{snapshot.public_count} public** Source Catalog entries and "
                f"**{snapshot.hidden_or_internal_count} hidden/internal** entry. Runtime "
                "plugins may append additional entries."
            ),
            f"  - {_primary_domain_metrics(snapshot, english=True)}",
            (
                f"  - `fetch` cross-cutting view: **{snapshot.fetch_provider_count} providers** "
                f"= **{len(snapshot.fetch_primary)} primary fetch-domain** + "
                f"**{len(snapshot.fetch_cross_domain)} cross-domain** sources."
            ),
        ]
    else:
        lines = [
            (
                f"- **{snapshot.registered_count} 个内置 registered source**：正式 Source "
                f"Catalog 含 **{snapshot.public_count} 个 public** 条目，另有 "
                f"**{snapshot.hidden_or_internal_count} 个 hidden/internal** 条目；外部插件可在"
                "运行时追加。"
            ),
            f"  - {_primary_domain_metrics(snapshot, english=False)}",
            (
                f"  - `fetch` 横切视图：**{snapshot.fetch_provider_count} 个 provider** = "
                f"**{len(snapshot.fetch_primary)} 个 fetch 主 domain** + "
                f"**{len(snapshot.fetch_cross_domain)} 个跨域源**。"
            ),
        ]
    return "\n".join(lines)


def _architecture_metrics(snapshot: RegistrySnapshot) -> str:
    return "\n".join(
        [
            (
                f"**Registry 摘要**：当前内置 registry 共 **{snapshot.registered_count}** 个 "
                f"registered `SourceAdapter`，其中 **{snapshot.public_count}** 个进入 public "
                f"Source Catalog，**{snapshot.hidden_or_internal_count}** 个为 hidden/internal。"
            ),
            "",
            f"- {_primary_domain_metrics(snapshot, english=False)}",
            (
                f"- `fetch` 横切视图共 **{snapshot.fetch_provider_count}** 个 provider："
                f"**{len(snapshot.fetch_primary)}** 个主 `domain=fetch`，"
                f"**{len(snapshot.fetch_cross_domain)}** 个由其他主 domain 跨域提供。"
            ),
        ]
    )


def _architecture_cross_domain_table(snapshot: RegistrySnapshot) -> str:
    lines = [
        '有些源同时可做主 domain 能力和抓取（`extra_domains={"fetch"}`）：',
        "",
        "| Registry name | Registry description | 主 domain | Fetch client method | 全部 capabilities |",
        "|---|---|---|---|---|",
    ]
    for adapter in snapshot.fetch_cross_domain:
        method_name = adapter.methods["fetch"].method_name
        description = adapter.description.replace("|", "\\|")
        capabilities = ", ".join(f"`{item}`" for item in sorted(adapter.capabilities))
        lines.append(
            f"| `{adapter.name}` | {description} | `{adapter.domain}` | `{method_name}` | "
            f"{capabilities} |"
        )
    return "\n".join(lines)


def _marker(marker: str, *, begin: bool) -> str:
    edge = "BEGIN" if begin else "END"
    return f"<!-- {edge} AUTO: {marker} -->"


def _replace_managed_region(text: str, marker: str, generated: str, *, path: Path) -> str:
    start = _marker(marker, begin=True)
    end = _marker(marker, begin=False)
    if text.count(start) != 1 or text.count(end) != 1:
        raise ValueError(f"{path}: expected exactly one {start!r} and one {end!r}")
    before, remainder = text.split(start, 1)
    _old, after = remainder.split(end, 1)
    return f"{before}{start}\n{generated.rstrip()}\n{end}{after}"


def render_managed_files() -> dict[Path, str]:
    """Return complete README/architecture files with generated regions replaced."""

    snapshot, _public_catalog, _source_categories = _load_snapshot(include_plugins=False)
    replacements: dict[Path, tuple[tuple[str, str], ...]] = {
        Path("README.md"): ((README_METRICS_MARKER, _readme_metrics(snapshot, english=False)),),
        Path("README.en.md"): ((README_METRICS_MARKER, _readme_metrics(snapshot, english=True)),),
        Path("docs/architecture.md"): (
            (ARCHITECTURE_METRICS_MARKER, _architecture_metrics(snapshot)),
            (
                ARCHITECTURE_CROSS_DOMAIN_MARKER,
                _architecture_cross_domain_table(snapshot),
            ),
        ),
    }
    rendered: dict[Path, str] = {}
    for relative_path, regions in replacements.items():
        absolute_path = REPO_ROOT / relative_path
        content = absolute_path.read_text(encoding="utf-8")
        for marker, generated in regions:
            content = _replace_managed_region(
                content,
                marker,
                generated,
                path=relative_path,
            )
        rendered[relative_path] = content
    return rendered


def _display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _check_content(path: Path, expected: str) -> bool:
    display = _display_path(path)
    if not path.exists():
        print(f"ERROR: {display} does not exist", file=sys.stderr)
        return False
    current = path.read_text(encoding="utf-8")
    if current == expected:
        print(f"OK: {display} is up to date")
        return True
    print(f"ERROR: {display} is out of date", file=sys.stderr)
    diff = difflib.unified_diff(
        current.splitlines(keepends=True),
        expected.splitlines(keepends=True),
        fromfile=display,
        tofile=f"generated/{display}",
    )
    sys.stderr.writelines(diff)
    return False


def main() -> int:
    _configure_cli_stdio()
    parser = argparse.ArgumentParser()
    parser.add_argument("-o", "--output", type=Path, help="写入文件；缺省则打印到 stdout")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--check",
        action="store_true",
        help="校验数据源清单、双 README 和 architecture 受控区是否与 registry 一致",
    )
    mode.add_argument(
        "--write",
        action="store_true",
        help="重建数据源清单、双 README 和 architecture 受控区",
    )
    parser.add_argument(
        "--include-plugins",
        action="store_true",
        help="包含当前环境已加载的外部 souwen.plugins entry point；默认只生成内置源",
    )
    parser.add_argument("--_render-only", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args.write and args.output:
        parser.error("--write manages fixed repository paths and cannot be combined with --output")
    if (args.check or args.write) and args.include_plugins:
        parser.error("checked-in managed docs cannot be generated with --include-plugins")

    if args._render_only:
        sys.stdout.write(render(include_plugins=args.include_plugins))
        return 0

    content = render_cli_content(include_plugins=args.include_plugins)
    if args.check:
        data_target = args.output or REPO_ROOT / DEFAULT_DATA_SOURCES_PATH
        checks = [_check_content(data_target, content)]
        if args.output is None:
            try:
                managed_files = render_managed_files()
            except ValueError as exc:
                print(f"ERROR: {exc}", file=sys.stderr)
                return 1
            for relative_path, expected in managed_files.items():
                checks.append(_check_content(REPO_ROOT / relative_path, expected))
        if all(checks):
            return 0
        print(
            "Regenerate checked-in docs with: PYTHONPATH=src python3 tools/gen_docs.py --write",
            file=sys.stderr,
        )
        return 1
    if args.write:
        data_target = REPO_ROOT / DEFAULT_DATA_SOURCES_PATH
        try:
            managed_files = render_managed_files()
        except ValueError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        data_target.write_text(content, encoding="utf-8")
        print(f"OK: wrote {_display_path(data_target)}")
        for relative_path, expected in managed_files.items():
            absolute_path = REPO_ROOT / relative_path
            absolute_path.write_text(expected, encoding="utf-8")
            print(f"OK: updated {relative_path}")
        return 0
    if args.output:
        args.output.write_text(content, encoding="utf-8")
        print(f"OK: wrote {args.output}")
    else:
        sys.stdout.write(content)
    return 0


if __name__ == "__main__":
    sys.exit(main())
