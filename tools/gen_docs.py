"""tools/gen_docs.py — 从 registry 派生数据源清单文档

输出 `docs/data-sources.md` 的 Markdown 表格。未来在 CI 里做 diff 校验。

用法：
    python tools/gen_docs.py                   # 打印
    python tools/gen_docs.py -o docs/data-sources.md  # 写入文件
"""

from __future__ import annotations

import argparse
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


def render() -> str:
    from souwen.registry import all_adapters, all_domains

    adapters = all_adapters()

    lines: list[str] = []
    lines.append("# SouWen 数据源清单")
    lines.append("")
    lines.append(f"**总计**：**{len(adapters)}** 个数据源（从 registry 自动生成）。")
    lines.append("")
    lines.append("<!-- BEGIN AUTO -->")
    lines.append("")

    for dom in all_domains():
        dom_adapters = sorted(
            [a for a in adapters.values() if dom in a.domains],
            key=lambda a: a.name,
        )
        title = DOMAIN_TITLES.get(dom, dom)
        lines.append(f"## {title} · `{dom}`（{len(dom_adapters)} 源）")
        lines.append("")
        lines.append("| Name | Integration | Capabilities | Config Field |")
        lines.append("|---|---|---|---|")
        for a in dom_adapters:
            caps = ", ".join(sorted(a.capabilities))
            cf = f"`{a.config_field}`" if a.config_field else "—"
            high_risk = " ⚠️" if "high_risk" in a.tags else ""
            lines.append(f"| `{a.name}`{high_risk} | {a.integration} | {caps} | {cf} |")
        lines.append("")

    lines.append("<!-- END AUTO -->")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 图例")
    lines.append("")
    lines.append("- ⚠️ high_risk：源易被反爬/限流，默认不启用")
    lines.append("- Integration 类型：")
    lines.append("  - `open_api` — 公开接口，免 Key")
    lines.append("  - `scraper` — 爬虫抓取，需 TLS 伪装")
    lines.append("  - `official_api` — 授权接口，需 API Key")
    lines.append("  - `self_hosted` — 自托管实例")
    lines.append("")
    lines.append("## 重新生成")
    lines.append("")
    lines.append("```bash")
    lines.append("python tools/gen_docs.py -o docs/data-sources.md")
    lines.append("```")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("-o", "--output", type=Path, help="写入文件；缺省则打印到 stdout")
    args = parser.parse_args()

    content = render()
    if args.output:
        args.output.write_text(content, encoding="utf-8")
        print(f"✓ 写入 {args.output}")
    else:
        print(content)
    return 0


if __name__ == "__main__":
    sys.exit(main())
