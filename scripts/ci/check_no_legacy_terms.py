#!/usr/bin/env python3
"""Fail when retired source-catalog terms re-enter active files."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

DENIED_TERMS = (
    "ALL_SOURCES",
    "as_all_sources_dict",
    "_v0_category_for",
    "v0_category",
    "v0_all_sources",
)

ALLOWED_PATHS = {
    "CHANGELOG.md",
    "scripts/ci/check_no_legacy_terms.py",
    "tests/test_import_surface.py",
}

ALLOWED_PREFIXES = ("docs/internal/",)

TEXT_SUFFIXES = {
    ".cfg",
    ".css",
    ".html",
    ".ini",
    ".js",
    ".json",
    ".md",
    ".py",
    ".rst",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".yaml",
    ".yml",
}


def _repo_root() -> Path:
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        check=True,
        stdout=subprocess.PIPE,
        text=True,
    )
    return Path(result.stdout.strip())


def _tracked_files(root: Path) -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=root,
        check=True,
        stdout=subprocess.PIPE,
        text=True,
    )
    return [root / line for line in result.stdout.splitlines() if line]


def _is_allowed(relative_path: str) -> bool:
    if relative_path in ALLOWED_PATHS:
        return True
    return any(relative_path.startswith(prefix) for prefix in ALLOWED_PREFIXES)


def main() -> int:
    root = _repo_root()
    findings: list[str] = []
    for path in _tracked_files(root):
        relative_path = path.relative_to(root).as_posix()
        if _is_allowed(relative_path) or path.suffix not in TEXT_SUFFIXES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for line_number, line in enumerate(text.splitlines(), start=1):
            for term in DENIED_TERMS:
                if term in line:
                    findings.append(f"{relative_path}:{line_number}: {term}")

    if findings:
        print("Retired source-catalog terms found:")
        for finding in findings:
            print(f"  {finding}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
