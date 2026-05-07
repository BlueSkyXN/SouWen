#!/usr/bin/env python3
"""Fail when retired v2 terms re-enter active code or public docs.

The gate has two levels:

* hard deny terms fail CI when they appear in active source files or public docs;
* soft terms only emit review warnings because words such as "兼容" can be valid
  in contexts like browser compatibility or protocol compatibility.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

HARD_DENIED_TERMS = (
    "ALL_SOURCES",
    "as_all_sources_dict",
    "source_registry",
    "souwen.facade",
    "souwen.fetch",
    "souwen.web.engines",
    "souwen.web.api",
    "souwen.web.self_hosted",
    "_v0_category_for",
    "v0_category",
    "v0_all_sources",
)

SOFT_WARN_PATTERNS = (
    ("兼容", re.compile("兼容")),
    ("旧版", re.compile("旧版")),
    ("v1", re.compile(r"(?<!api/)v1\b", re.IGNORECASE)),
    ("shim", re.compile(r"\bshim\b", re.IGNORECASE)),
    ("migration", re.compile(r"\bmigration\b", re.IGNORECASE)),
)

ALLOWED_PATHS = {
    "CHANGELOG.md",
    ".github/workflows/v2-ci.yml",
    "scripts/ci/check_no_legacy_terms.py",
    "tests/test_import_surface.py",
}

ALLOWED_PREFIXES = ("docs/internal/",)
SOFT_WARN_PATHS = {
    "README.md",
    "README.en.md",
    "docs/concepts.md",
    "docs/deployment.md",
    "docs/getting-started.md",
    "docs/python-api.md",
    "docs/README.md",
    "docs/architecture.md",
    "docs/adding-a-source.md",
    "docs/api-reference.md",
    "docs/configuration.md",
    "docs/data-sources.md",
    "docs/plugin-integration-spec.md",
    "docs/source-catalog.md",
}

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


def _compile_hard_pattern(term: str) -> re.Pattern[str]:
    escaped = re.escape(term)
    if "." in term:
        return re.compile(rf"(?<![\w.]){escaped}(?![\w.])")
    return re.compile(rf"(?<![\w]){escaped}(?![\w])")


HARD_DENY_PATTERNS = tuple((term, _compile_hard_pattern(term)) for term in HARD_DENIED_TERMS)


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


def _is_soft_warn_path(relative_path: str) -> bool:
    return relative_path in SOFT_WARN_PATHS


def main() -> int:
    root = _repo_root()
    findings: list[str] = []
    warnings: list[str] = []
    for path in _tracked_files(root):
        relative_path = path.relative_to(root).as_posix()
        if _is_allowed(relative_path) or path.suffix not in TEXT_SUFFIXES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for line_number, line in enumerate(text.splitlines(), start=1):
            for term, pattern in HARD_DENY_PATTERNS:
                if pattern.search(line):
                    findings.append(f"{relative_path}:{line_number}: {term}")
            if _is_soft_warn_path(relative_path):
                for term, pattern in SOFT_WARN_PATTERNS:
                    if pattern.search(line):
                        warnings.append(f"{relative_path}:{line_number}: {term}")

    if findings:
        print("Retired v2 hard-deny terms found:")
        for finding in findings:
            print(f"  {finding}")
        return 1
    if warnings:
        print("Legacy wording review warnings:")
        for warning in warnings:
            print(f"  {warning}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
