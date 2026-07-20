from __future__ import annotations

from pathlib import Path
import sys

from souwen.provenance import get_source_sha


def test_source_sha_prefers_validated_environment(monkeypatch) -> None:
    monkeypatch.setenv("SOUWEN_SOURCE_SHA", "A" * 40)
    monkeypatch.delenv("SOUWEN_SOURCE_SHA_FILE", raising=False)

    assert get_source_sha() == "a" * 40


def test_invalid_explicit_source_sha_does_not_fall_back(monkeypatch, tmp_path: Path) -> None:
    (tmp_path / "runtime.source.sha").write_text("b" * 40, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SOUWEN_SOURCE_SHA", "main")

    assert get_source_sha() is None


def test_source_sha_reads_explicit_file(monkeypatch, tmp_path: Path) -> None:
    source_file = tmp_path / "candidate.sha"
    source_file.write_text(f"{'c' * 40}\n", encoding="utf-8")
    monkeypatch.delenv("SOUWEN_SOURCE_SHA", raising=False)
    monkeypatch.setenv("SOUWEN_SOURCE_SHA_FILE", str(source_file))

    assert get_source_sha() == "c" * 40


def test_source_sha_reads_frozen_bundle_root(monkeypatch, tmp_path: Path) -> None:
    (tmp_path / "runtime.source.sha").write_text("e" * 40, encoding="utf-8")
    monkeypatch.delenv("SOUWEN_SOURCE_SHA", raising=False)
    monkeypatch.delenv("SOUWEN_SOURCE_SHA_FILE", raising=False)
    monkeypatch.chdir(tmp_path.parent)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)

    assert get_source_sha() == "e" * 40
