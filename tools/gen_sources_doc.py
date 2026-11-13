#!/usr/bin/env python3
"""Render docs/sources.md from a census sources.json report (P4, SPEC 8).

Usage: python3 tools/gen_sources_doc.py --census reports/warp-on/sources.json \
           [--census-fallback reports-fallback/.../sources.json] [--write]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

RANK = {"PASS": 2, "WARN": 1, "FAIL": 0, "SKIP": 0}


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


def render(best: dict[str, dict]) -> str:
    lines = [
        "# Source census",
        "",
        "> 由 `tools/gen_sources_doc.py` 从最近的 census 报告生成；不要手改本文件。",
        "> 判定口径：PASS = 3 查询 ≥2 有效；WARN = 1；FAIL = 0。取两次 leg 中较好的一次。",
        "",
        "| 源 | 结果 | 有效/总数 | 备注 |",
        "|---|---|---|---|",
    ]
    order = {"PASS": 0, "WARN": 1, "FAIL": 2, "SKIP": 3}
    for label, v in sorted(best.items(), key=lambda kv: (order[kv[1]["outcome"]], kv[0])):
        note = v.get("detail", "") or ""
        if v.get("leg"):
            note = f"[{v['leg']}] {note}".strip()
        lines.append(f"| `{label}` | {v['outcome']} | {v['valid_count']}/{v['total']} | {note} |")
    counts: dict[str, int] = {}
    for v in best.values():
        counts[v["outcome"]] = counts.get(v["outcome"], 0) + 1
    summary = " · ".join(f"{k} {v}" for k, v in sorted(counts.items()))
    lines.insert(4, "")
    lines.insert(5, f"汇总：{summary}，共 {len(best)} 源。")
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
    args = parser.parse_args()
    best = merge_best(*(load(path) for path in args.census))
    text = render(best)
    if args.write:
        Path(args.write).write_text(text, encoding="utf-8")
        print(f"written {args.write}")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
