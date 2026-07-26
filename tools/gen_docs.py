"""Generate the built-in Provider v2 catalog and managed documentation summaries."""

from __future__ import annotations

import argparse
import difflib
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from souwen.platform.manifest_registry import ProviderManifest  # noqa: E402
from souwen.providers.catalog import builtin_provider_manifests  # noqa: E402


README_METRICS_MARKER = "SOURCE METRICS"
ARCHITECTURE_METRICS_MARKER = "REGISTRY SUMMARY"
ARCHITECTURE_CROSS_DOMAIN_MARKER = "CROSS-DOMAIN FETCH SOURCES"
DEFAULT_DATA_SOURCES_PATH = Path("docs/data-sources.md")


@dataclass(frozen=True, slots=True)
class ProviderSnapshot:
    manifests: tuple[ProviderManifest, ...]

    @property
    def package_count(self) -> int:
        return len(self.manifests)

    @property
    def adapter_count(self) -> int:
        return sum(len(manifest.adapters) for manifest in self.manifests)

    def capability_count(self, capability: str) -> int:
        return sum(capability in manifest.capabilities for manifest in self.manifests)

    @property
    def multi_capability(self) -> tuple[ProviderManifest, ...]:
        return tuple(manifest for manifest in self.manifests if len(manifest.capabilities) > 1)


def _configure_cli_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8")


def _load_snapshot() -> ProviderSnapshot:
    return ProviderSnapshot(builtin_provider_manifests())


def _auth(manifest: ProviderManifest) -> str:
    required = ", ".join(f"`{item}`" for item in manifest.secrets.references)
    optional = ", ".join(f"`{item}`" for item in manifest.secrets.optional_references)
    if required and optional:
        return f"required: {required}; optional: {optional}"
    if required:
        return f"required: {required}"
    if optional:
        return f"optional: {optional}"
    return "none"


def _network(manifest: ProviderManifest) -> str:
    if manifest.network.target_egress != "none":
        return f"`{manifest.network.target_egress}`"
    if manifest.network.egress_hosts:
        return ", ".join(f"`{host}`" for host in manifest.network.egress_hosts)
    return "none"


def render() -> str:
    snapshot = _load_snapshot()
    lines = [
        "# SouWen Provider v2 数据源清单",
        "",
        "本页由每个内置 Provider package 的 `manifest.py` 经 "
        "`souwen.providers.catalog.builtin_provider_manifests()` 生成。Manifest Registry 与 "
        "Provider Manager 是唯一运行时事实来源；不存在并行的旧 source registry。",
        "",
        "公开能力严格只有 `search`、`llm_search`、`fetch`。同一 package 可以提供多个能力，"
        "每个能力对应一个明确 adapter；列表不包含已退休的 citation、detail、archive-save、"
        "recursive-crawl 或 browser-fetch 产品入口。",
        "",
        "## 摘要",
        "",
        "| 指标 | 数量 |",
        "|---|---:|",
        f"| Provider packages | **{snapshot.package_count}** |",
        f"| Provider adapters | **{snapshot.adapter_count}** |",
        f"| Search packages | **{snapshot.capability_count('search')}** |",
        f"| LLM Search packages | **{snapshot.capability_count('llm_search')}** |",
        f"| Fetch packages | **{snapshot.capability_count('fetch')}** |",
        "",
        "## 内置 Provider packages",
        "",
        "| Provider | Capabilities | Availability | Auth references | Network contract | Browser | Costed |",
        "|---|---|---|---|---|---:|---:|",
    ]
    for manifest in snapshot.manifests:
        capabilities = ", ".join(f"`{item}`" for item in manifest.capabilities)
        availability = ", ".join(
            f"`{adapter.capability}:{adapter.availability}`" for adapter in manifest.adapters
        )
        lines.append(
            f"| `{manifest.id}` | {capabilities} | {availability} | {_auth(manifest)} | "
            f"{_network(manifest)} | {'yes' if manifest.network.browser_required else 'no'} | "
            f"{'yes' if manifest.risk.costed else 'no'} |"
        )
    lines.extend(
        [
            "",
            "## 重新生成与校验",
            "",
            "```bash",
            "PYTHONPATH=src python3 tools/gen_docs.py --write",
            "PYTHONPATH=src python3 tools/gen_docs.py --check",
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def render_cli_content() -> str:
    return render()


def _readme_metrics(snapshot: ProviderSnapshot, *, english: bool) -> str:
    if english:
        return "\n".join(
            [
                f"- **{snapshot.package_count} built-in Provider v2 packages** and "
                f"**{snapshot.adapter_count} capability adapters**.",
                f"  - Search: **{snapshot.capability_count('search')}** packages · "
                f"LLM Search: **{snapshot.capability_count('llm_search')}** · "
                f"Fetch: **{snapshot.capability_count('fetch')}**.",
            ]
        )
    return "\n".join(
        [
            f"- **{snapshot.package_count} 个内置 Provider v2 package**，共 "
            f"**{snapshot.adapter_count} 个 capability adapter**。",
            f"  - Search：**{snapshot.capability_count('search')}** 个 package · "
            f"LLM Search：**{snapshot.capability_count('llm_search')}** 个 · "
            f"Fetch：**{snapshot.capability_count('fetch')}** 个。",
        ]
    )


def _architecture_metrics(snapshot: ProviderSnapshot) -> str:
    return "\n".join(
        [
            f"**Provider v2 摘要**：Manifest Registry 从内置 package 发现 "
            f"**{snapshot.package_count}** 份 manifest、**{snapshot.adapter_count}** 个 adapter。",
            "",
            "Provider Manager 对 manifest、configuration、secret reference 和显式 factory 做 "
            "preflight，并按需构造 provider；旧 source registry 不参与启动、路由或文档生成。",
        ]
    )


def _multi_capability_table(snapshot: ProviderSnapshot) -> str:
    lines = [
        "以下 package 通过独立 adapter 提供多个公开能力：",
        "",
        "| Provider package | Capabilities | Adapter IDs |",
        "|---|---|---|",
    ]
    for manifest in snapshot.multi_capability:
        capabilities = ", ".join(f"`{item}`" for item in manifest.capabilities)
        adapters = ", ".join(f"`{item.id}`" for item in manifest.adapters)
        lines.append(f"| `{manifest.id}` | {capabilities} | {adapters} |")
    return "\n".join(lines)


def _marker(marker: str, *, begin: bool) -> str:
    return f"<!-- {'BEGIN' if begin else 'END'} AUTO: {marker} -->"


def _replace_managed_region(text: str, marker: str, generated: str, *, path: Path) -> str:
    start, end = _marker(marker, begin=True), _marker(marker, begin=False)
    if text.count(start) != 1 or text.count(end) != 1:
        raise ValueError(f"{path}: expected exactly one {start!r} and one {end!r}")
    before, remainder = text.split(start, 1)
    _old, after = remainder.split(end, 1)
    return f"{before}{start}\n{generated.rstrip()}\n{end}{after}"


def render_managed_files() -> dict[Path, str]:
    snapshot = _load_snapshot()
    replacements: dict[Path, tuple[tuple[str, str], ...]] = {
        Path("README.md"): ((README_METRICS_MARKER, _readme_metrics(snapshot, english=False)),),
        Path("README.en.md"): ((README_METRICS_MARKER, _readme_metrics(snapshot, english=True)),),
        Path("docs/architecture.md"): (
            (ARCHITECTURE_METRICS_MARKER, _architecture_metrics(snapshot)),
            (ARCHITECTURE_CROSS_DOMAIN_MARKER, _multi_capability_table(snapshot)),
        ),
    }
    rendered: dict[Path, str] = {}
    for relative_path, regions in replacements.items():
        content = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
        for marker, generated in regions:
            content = _replace_managed_region(content, marker, generated, path=relative_path)
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
    sys.stderr.writelines(
        difflib.unified_diff(
            current.splitlines(keepends=True),
            expected.splitlines(keepends=True),
            fromfile=display,
            tofile=f"generated/{display}",
        )
    )
    return False


def main() -> int:
    _configure_cli_stdio()
    parser = argparse.ArgumentParser()
    parser.add_argument("-o", "--output", type=Path)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--write", action="store_true")
    args = parser.parse_args()
    if args.write and args.output:
        parser.error("--write cannot be combined with --output")

    content = render()
    if args.check:
        targets = [(args.output or REPO_ROOT / DEFAULT_DATA_SOURCES_PATH, content)]
        if args.output is None:
            targets.extend(
                (REPO_ROOT / relative_path, expected)
                for relative_path, expected in render_managed_files().items()
            )
        return 0 if all(_check_content(path, expected) for path, expected in targets) else 1
    if args.write:
        target = REPO_ROOT / DEFAULT_DATA_SOURCES_PATH
        target.write_text(content, encoding="utf-8")
        print(f"OK: wrote {_display_path(target)}")
        for relative_path, expected in render_managed_files().items():
            (REPO_ROOT / relative_path).write_text(expected, encoding="utf-8")
            print(f"OK: updated {relative_path}")
        return 0
    if args.output:
        args.output.write_text(content, encoding="utf-8")
        print(f"OK: wrote {args.output}")
    else:
        sys.stdout.write(content)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
