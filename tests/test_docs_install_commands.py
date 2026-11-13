"""Public README install guidance must use the documented leaf extras."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_public_readmes_use_leaf_install_profiles() -> None:
    for name in ("README.md", "README.en.md"):
        text = (REPO_ROOT / name).read_text(encoding="utf-8")

        assert 'pip install "souwen[server,mcp]"' in text
        assert "edition-" not in text
