"""tools/gen_docs.py — 从 registry 派生数据源清单文档

输出 `docs/data-sources.md` 的 Markdown 表格。未来在 CI 里做 diff 校验。

用法：
    python tools/gen_docs.py                   # 打印
    python tools/gen_docs.py -o docs/data-sources.md  # 写入文件
"""

from __future__ import annotations

import argparse
import os
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


def render(*, include_plugins: bool = False) -> str:
    if not include_plugins:
        # Checked-in docs should be reproducible even when local development
        # environments have third-party souwen.plugins entry points installed.
        os.environ.setdefault("SOUWEN_PLUGIN_AUTOLOAD", "0")

    from souwen.registry import all_adapters, all_domains, external_plugins
    from souwen.source_registry import (
        AUTH_REQUIREMENT_LABELS,
        DISTRIBUTION_LABELS,
        OPTIONAL_CREDENTIAL_EFFECT_LABELS,
        RISK_LEVEL_LABELS,
        STABILITY_LABELS,
    )

    loaded_adapters = all_adapters()
    external_names = set(external_plugins())
    adapters = {
        name: adapter
        for name, adapter in loaded_adapters.items()
        if include_plugins or name not in external_names
    }
    visible_external_count = len(external_names) if include_plugins else 0

    lines: list[str] = []
    lines.append("# SouWen 数据源清单")
    lines.append("")
    lines.append(
        f"**总计**：**{len(adapters)}** 个数据源（从 registry 自动生成；"
        f"其中外部插件 **{visible_external_count}** 个）。"
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
    lines.append("")
    lines.append("## 重新生成")
    lines.append("")
    lines.append("```bash")
    lines.append("python tools/gen_docs.py -o docs/data-sources.md")
    lines.append("```")
    lines.append("")
    lines.append("如需在本机 catalog 中展示已安装的外部插件，可追加 `--include-plugins`。")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("-o", "--output", type=Path, help="写入文件；缺省则打印到 stdout")
    parser.add_argument(
        "--include-plugins",
        action="store_true",
        help="包含当前环境已加载的外部 souwen.plugins entry point；默认只生成内置源",
    )
    args = parser.parse_args()

    content = render(include_plugins=args.include_plugins)
    if args.output:
        args.output.write_text(content, encoding="utf-8")
        print(f"✓ 写入 {args.output}")
    else:
        print(content)
    return 0


if __name__ == "__main__":
    sys.exit(main())
