from __future__ import annotations

from pathlib import Path
import sys

from souwen.common_runtime.observability import (
    SOURCE_SHA_ENV,
    SOURCE_SHA_FILE_ENV,
    SOURCE_SHA_FILENAME,
    get_source_sha,
)
from souwen.common_runtime.observability import provenance as canonical_provenance
from souwen import provenance as legacy_provenance


def test_legacy_provenance_path_reexports_canonical_interface() -> None:
    assert legacy_provenance.SOURCE_SHA_ENV is SOURCE_SHA_ENV
    assert legacy_provenance.SOURCE_SHA_FILE_ENV is SOURCE_SHA_FILE_ENV
    assert legacy_provenance.SOURCE_SHA_FILENAME is SOURCE_SHA_FILENAME
    assert legacy_provenance.get_source_sha is get_source_sha


def test_canonical_provenance_has_no_domain_or_delivery_dependencies() -> None:
    source = Path(canonical_provenance.__file__).read_text(encoding="utf-8")

    for forbidden in (
        "souwen.core",
        "souwen.delivery",
        "souwen.modules",
        "souwen.providers",
        "souwen.registry",
        "souwen.server",
    ):
        assert forbidden not in source


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


def test_invalid_explicit_source_sha_file_does_not_fall_back(monkeypatch, tmp_path: Path) -> None:
    (tmp_path / "runtime.source.sha").write_text("f" * 40, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv(SOURCE_SHA_ENV, raising=False)
    monkeypatch.setenv(SOURCE_SHA_FILE_ENV, str(tmp_path / "missing.sha"))

    assert get_source_sha() is None


def test_default_source_sha_candidate_order_is_preserved(monkeypatch, tmp_path: Path) -> None:
    cwd = tmp_path / "cwd"
    bundle = tmp_path / "bundle"
    executable = tmp_path / "bin" / "python"
    cwd.mkdir()
    bundle.mkdir()
    monkeypatch.chdir(cwd)
    monkeypatch.setattr(sys, "_MEIPASS", str(bundle), raising=False)
    monkeypatch.setattr(sys, "executable", str(executable))

    module_path = Path(canonical_provenance.__file__).resolve()
    assert list(canonical_provenance._default_source_sha_files()) == [
        cwd / SOURCE_SHA_FILENAME,
        bundle / SOURCE_SHA_FILENAME,
        executable.parent / SOURCE_SHA_FILENAME,
        module_path.parents[3] / SOURCE_SHA_FILENAME,
        module_path.parents[4] / SOURCE_SHA_FILENAME,
    ]
