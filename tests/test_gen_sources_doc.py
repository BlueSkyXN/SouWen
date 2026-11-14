"""`tools/gen_sources_doc.py` 的确定性回归。

PRD 成功标准第 4 条要求仓库里每个保留源在最近一次体检里都有结果，
`docs/sources.md` 由体检生成。零 Key 镜像里需免费 Key 的源没有探测
结果，必须显式列为 NOT PROBED，而不是从分母里消失。
"""

from __future__ import annotations

from tools import gen_sources_doc


def _report(label: str, verdicts: list[dict]) -> dict:
    return {"label": label, "verdicts": verdicts}


def _verdict(label: str, outcome: str, valid: int, total: int, detail: str = "") -> dict:
    return {
        "label": label,
        "outcome": outcome,
        "valid_count": valid,
        "total": total,
        "detail": detail,
    }


def test_declared_sources_covers_every_retained_module_with_manifest_ids():
    declared = gen_sources_doc.declared_sources()
    assert len(declared) == 36
    # 目录名与 manifest id 不一致的那个源必须用 manifest id
    assert "builtin-fetch" in declared
    assert "builtin" not in declared
    # 四个免费 Key 源各自声明了密钥引用
    assert declared["patentsview"] == ("PATENTSVIEW_API_KEY",)
    assert declared["uspto_odp"] == ("USPTO_API_KEY",)
    assert declared["youtube"] == ("YOUTUBE_API_KEY",)
    assert declared["epo_ops"] == ("EPO_CONSUMER_KEY", "EPO_CONSUMER_SECRET")
    # 零 Key 源不声明任何引用
    assert declared["arxiv"] == ()


def test_merge_best_keeps_the_stronger_leg_and_records_it():
    on = _report(
        "warp-on", [_verdict("arxiv", "PASS", 3, 3, "ok"), _verdict("yahoo", "FAIL", 0, 3)]
    )
    off = _report(
        "warp-off",
        [_verdict("arxiv", "WARN", 1, 3), _verdict("yahoo", "PASS", 3, 3, "ok")],
    )
    best = gen_sources_doc.merge_best(on, off)
    assert best["arxiv"]["outcome"] == "PASS"
    assert best["arxiv"]["leg"] == "warp-on"
    assert best["yahoo"]["outcome"] == "PASS"
    assert best["yahoo"]["leg"] == "warp-off"


def test_render_lists_unprobed_sources_instead_of_dropping_them():
    on = _report("warp-on", [_verdict("arxiv", "PASS", 3, 3, "ok")])
    declared = {
        "arxiv": (),
        "patentsview": ("PATENTSVIEW_API_KEY",),
        "searxng": (),
    }
    text = gen_sources_doc.render(gen_sources_doc.merge_best(on), declared)
    assert "共 3 源" in text
    assert "NOT PROBED 2" in text
    assert "| `patentsview` | NOT PROBED | – | needs free key: PATENTSVIEW_API_KEY |" in text
    assert "| `searxng` | NOT PROBED | – | needs free key: deployment configuration |" in text


def test_render_records_run_sha_and_environment():
    on = _report("warp-on", [_verdict("arxiv", "PASS", 3, 3, "ok")])
    text = gen_sources_doc.render(
        gen_sources_doc.merge_best(on),
        {"arxiv": ()},
        [
            "来源报告 leg：warp-on, warp-off（逐源取较优者，备注里保留该源实际来自哪条 leg）。",
            "run：[1](https://github.com/BlueSkyXN/SouWen/actions/runs/1)",
            "源码 SHA：`abc`",
            "WARP：`warp=on verified after 1 attempts`",
        ],
    )
    assert "来源报告 leg：warp-on, warp-off" in text
    assert "源码 SHA：`abc`" in text
    assert "WARP：`warp=on verified after 1 attempts`" in text
    # 汇总行在表格之前
    assert text.index("汇总：") < text.index("| 源 | 结果 |")


def test_checked_in_sources_doc_covers_all_retained_sources():
    from pathlib import Path

    text = Path("docs/sources.md").read_text(encoding="utf-8")
    declared = gen_sources_doc.declared_sources()
    for source_id in declared:
        assert f"`{source_id}`" in text, f"{source_id} missing from docs/sources.md"
    assert "共 36 源" in text
