#!/usr/bin/env python3
"""Render docs/sources.md from a census sources.json report (P4, SPEC 8).

Usage: python3 tools/gen_sources_doc.py --census reports/warp-on/sources.json \
           [--census-fallback reports-fallback/.../sources.json] --write docs/sources.md

The census only probes sources the running instance reports as available.
Sources that need a free API key stay unavailable with zero keys configured,
so they produce no probe result — but PRD success criterion 4 requires every
retained source to appear with a status. This generator cross-checks the
report against the retained source modules and lists the missing ones as
NOT PROBED with the secret reference that would enable them.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path

RANK = {"PASS": 2, "WARN": 1, "FAIL": 0, "SKIP": 0}

_PROVIDERS = Path(__file__).resolve().parents[1] / "src/souwen/providers"
_NAMESPACES = ("information_sources", "fetch_sources")


def load(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def merge_best(*reports: dict) -> dict[str, dict]:
    best: dict[str, dict] = {}
    for report in reports:
        for verdict in report["verdicts"]:
            label = verdict["label"]
            cur = best.get(label)
            if cur is None or RANK[verdict["outcome"]] > RANK[cur["outcome"]]:
                entry = dict(verdict)
                entry["leg"] = report.get("label", "")
                best[label] = entry
    return best


def declared_sources() -> dict[str, tuple[str, ...]]:
    """Map every retained source id to its declared secret references.

    Parsed statically so the generator stays offline and does not import the
    runtime (a source module may require optional extras). The id comes from
    the manifest literal, not the directory name — `builtin/` declares
    `builtin-fetch`.
    """
    declared: dict[str, tuple[str, ...]] = {}
    for namespace in _NAMESPACES:
        for module in sorted((_PROVIDERS / namespace).glob("*/source.py")):
            refs: tuple[str, ...] = ()
            manifest_id: str | None = None
            for node in ast.walk(ast.parse(module.read_text(encoding="utf-8"))):
                if not isinstance(node, ast.Dict):
                    continue
                keys = [
                    key.value
                    if isinstance(key, ast.Constant) and isinstance(key.value, str)
                    else None
                    for key in node.keys
                ]
                # Only the manifest literal carries schema_version; adapter
                # declarations also have an "id" (e.g. "arxiv-search").
                if "schema_version" in keys and "id" in keys:
                    value = node.values[keys.index("id")]
                    if isinstance(value, ast.Constant) and isinstance(value.value, str):
                        manifest_id = value.value
                if "secrets" not in keys:
                    continue
                value = node.values[keys.index("secrets")]
                if not isinstance(value, ast.Dict):
                    continue
                names = [
                    key.value
                    if isinstance(key, ast.Constant) and isinstance(key.value, str)
                    else None
                    for key in value.keys
                ]
                if "references" not in names:
                    continue
                entries = value.values[names.index("references")]
                if isinstance(entries, ast.List):
                    refs = tuple(
                        entry.value
                        for entry in entries.elts
                        if isinstance(entry, ast.Constant) and isinstance(entry.value, str)
                    )
            declared[manifest_id or module.parent.name] = refs
    return declared


def render(
    best: dict[str, dict],
    declared: dict[str, tuple[str, ...]],
    provenance: list[str] | None = None,
) -> str:
    unprobed = {sid: refs for sid, refs in declared.items() if sid not in best}
    lines = [
        "# Source census",
        "",
        "> 由 `tools/gen_sources_doc.py` 从最近的 census 报告生成；不要手改本文件。",
        "> 判定口径：PASS = 3 查询 ≥2 有效；WARN = 1；FAIL = 0。取两次 leg 中较好的一次。",
        "> NOT PROBED = 零 Key 镜像里不可用（需免费 Key 且未配置或自建实例未配），不是失败。",
    ]
    if provenance:
        lines.extend(f"> {line}" for line in provenance)
    lines.extend(
        [
            "",
            "| 源 | 结果 | 有效/总数 | 备注 |",
            "|---|---|---|---|",
        ]
    )
    order = {"PASS": 0, "WARN": 1, "FAIL": 2, "SKIP": 3}
    for label, verdict in sorted(best.items(), key=lambda kv: (order[kv[1]["outcome"]], kv[0])):
        note = verdict.get("detail", "") or ""
        if verdict.get("leg"):
            note = f"[{verdict['leg']}] {note}".strip()
        lines.append(
            f"| `{label}` | {verdict['outcome']} | "
            f"{verdict['valid_count']}/{verdict['total']} | {note} |"
        )
    for label, refs in sorted(unprobed.items()):
        needed = ", ".join(refs) if refs else "deployment configuration"
        lines.append(f"| `{label}` | NOT PROBED | – | needs free key: {needed} |")
    counts: dict[str, int] = {}
    for verdict in best.values():
        counts[verdict["outcome"]] = counts.get(verdict["outcome"], 0) + 1
    summary = " · ".join(f"{k} {v}" for k, v in sorted(counts.items()))
    if unprobed:
        summary = f"{summary} · NOT PROBED {len(unprobed)}"
    total = len(best) + len(unprobed)
    # 汇总行紧跟注释块，位于表格前。
    table_at = lines.index("| 源 | 结果 | 有效/总数 | 备注 |")
    lines.insert(table_at, f"汇总：{summary}，共 {total} 源（其中 {len(best)} 源有体检结果）。")
    lines.insert(table_at + 1, "")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--census",
        action="append",
        required=True,
        help="census sources.json（可传多次，取各 leg 较优）",
    )
    parser.add_argument("--write", default=None, help="输出路径（默认 stdout）")
    parser.add_argument("--run-id", default=None, help="Actions run id（写入来源信息）")
    parser.add_argument("--source-sha", default=None, help="被测源码 SHA（写入来源信息）")
    parser.add_argument(
        "--warp-status",
        default=None,
        help="WARP 状态文件内容（如 'warp=on verified after 1 attempts'）",
    )
    args = parser.parse_args()
    best = merge_best(*(load(path) for path in args.census))
    provenance: list[str] = []
    compared = [load(path).get("label", "") for path in args.census]
    compared = [label for label in dict.fromkeys(compared) if label]
    if compared:
        provenance.append(
            f"来源报告 leg：{', '.join(compared)}（逐源取较优者，备注里保留该源实际来自哪条 leg）。"
        )
    if args.run_id:
        provenance.append(
            f"run：[{args.run_id}](https://github.com/BlueSkyXN/SouWen/actions/runs/{args.run_id})"
        )
    if args.source_sha:
        provenance.append(f"源码 SHA：`{args.source_sha}`")
    if args.warp_status:
        provenance.append(f"WARP：`{args.warp_status}`")
    text = render(best, declared_sources(), provenance)
    if args.write:
        Path(args.write).write_text(text, encoding="utf-8")
        print(f"written {args.write}")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
