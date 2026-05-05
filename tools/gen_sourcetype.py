"""tools/gen_sourcetype.py — 从 registry 派生 SourceType 枚举

当前用途（v0.9-v1.x）：
    `SourceType` 仍是手写枚举（`souwen.models.SourceType`），
    CI 校验生成结果 ≈ 手写枚举（通过 adapter.name ↔ SourceType.value 规范化映射）。

未来（v2.0+）：
    直接把生成结果替换手写枚举；同时引入 `SourceName = Literal[...]`。

用法：
    python tools/gen_sourcetype.py            # 打印 v2 的 SourceType 候选
    python tools/gen_sourcetype.py --check    # CI 校验（比对手写 SourceType 与 registry）
"""

from __future__ import annotations

import argparse
import sys


# SourceType.value → adapter.name 规范化映射（与 web/search.py 的 _source_type_for 反向一致）
# SourceType 用简写（WEB_DDG_NEWS），registry 用全名（duckduckgo_news）。
_DDG_ALIASES: dict[str, str] = {
    "ddg_news": "duckduckgo_news",
    "ddg_images": "duckduckgo_images",
    "ddg_videos": "duckduckgo_videos",
}


def _normalize_source_type_value(v: str) -> str:
    """SourceType.value → adapter.name。"""
    for prefix in ("web_", "fetch_"):
        if v.startswith(prefix):
            v = v[len(prefix) :]
            break
    return _DDG_ALIASES.get(v, v)


def render() -> str:
    """渲染 SourceType 枚举代码（v2 未来用的"去前缀"纯名字形式）。"""
    from souwen.registry import enum_values

    names = enum_values()
    lines = ["class SourceType(str, Enum):", '    """数据源类型枚举（从 registry 自动生成）"""', ""]
    for name in names:
        key = name.upper()
        lines.append(f'    {key} = "{name}"')
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check",
        action="store_true",
        help="校验手写 SourceType 每个值规范化后都能在 registry 找到对应 adapter",
    )
    args = parser.parse_args()

    from souwen.models import SourceType
    from souwen.registry import enum_values

    registry_names = set(enum_values())

    if args.check:
        bad: list[tuple[str, str]] = []
        for member in SourceType:
            normalized = _normalize_source_type_value(member.value)
            if normalized not in registry_names:
                bad.append((member.name, member.value))
        if bad:
            print("❌ 下列 SourceType 规范化后在 registry 找不到对应 adapter：")
            for name, val in bad:
                print(f"  - SourceType.{name} = {val!r}")
            print()
            print("修复方法：(1) 把这些源登记到 registry/sources/；或 (2) 从 SourceType 里删除")
            return 1
        print(f"✓ SourceType ({len(list(SourceType))}) 与 registry ({len(registry_names)}) 一致")
        return 0

    print(render())
    return 0


if __name__ == "__main__":
    sys.exit(main())
