"""Print or check source ids derived from the registry.

Source ids are registry adapter names. This helper is intentionally a
development-time check only; runtime models accept plain strings so plugin
sources can be registered dynamically.

Usage:
    python tools/gen_source_ids.py
    python tools/gen_source_ids.py --check
"""

from __future__ import annotations

import argparse
import sys


def source_ids() -> list[str]:
    """Return all registered adapter names in stable order."""
    from souwen.registry import enum_values

    return enum_values()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify registry-derived source ids are valid adapter names",
    )
    args = parser.parse_args()

    from souwen.registry import all_adapters

    ids = source_ids()
    adapter_names = set(all_adapters())
    if args.check:
        invalid = [source_id for source_id in ids if source_id not in adapter_names]
        legacy = [
            source_id
            for source_id in ids
            if source_id
            in {
                "web_" + "duckduckgo",
                "web_" + "bing",
                "web_" + "tavily",
                "fetch_" + "builtin",
            }
        ]
        if invalid or legacy:
            if invalid:
                print("Invalid source ids:")
                for source_id in invalid:
                    print(f"  - {source_id}")
            if legacy:
                print("Legacy source ids:")
                for source_id in legacy:
                    print(f"  - {source_id}")
            return 1
        print(f"OK: {len(ids)} source ids match registry adapter names")
        return 0

    for source_id in ids:
        print(source_id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
