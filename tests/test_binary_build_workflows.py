from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = {
    ".github/workflows/build-pyinstaller.yml": "souwen",
    ".github/workflows/build-nuitka.yml": "souwen-nuitka",
}
EXPECTED_PROFILES = {
    "basic-cli": ("basic", "edition-basic"),
    "pro-cli": ("pro", "edition-pro"),
    "full-cli": ("full", "edition-full"),
}
LEGACY_ALIASES = {
    "cli": "basic-cli",
    "server": "pro-cli",
    "full": "full-cli",
}


def _workflow_text(relative: str) -> str:
    return (REPO_ROOT / relative).read_text(encoding="utf-8")


def _unescaped_workflow_text(relative: str) -> str:
    return _workflow_text(relative).replace('\\"', '"')


def test_binary_build_workflows_use_edition_cli_profiles() -> None:
    for relative, artifact_prefix in WORKFLOWS.items():
        text = _unescaped_workflow_text(relative)

        for profile, (edition, install_extra) in EXPECTED_PROFILES.items():
            assert f"- {profile}" in text
            assert (
                f'"build_type":"{profile}","edition":"{edition}","install_extra":"{install_extra}"'
            ) in text
            assert f"{artifact_prefix}-${{ARCH}}-{profile}${{EXT}}" in text

        assert 'pip install -e ".[${{ matrix.install_extra }}]"' in text
        assert "SOUWEN_EDITION: ${{ matrix.edition }}" in text
        assert "doctor edition --json" in text
        assert "need_panel: ${{ steps.set-matrix.outputs.need_panel }}" in text
        assert "needs.prepare.outputs.need_panel == 'true'" in text
        assert "actions/download-artifact@v8" in text


def test_binary_build_workflows_keep_legacy_profile_aliases_only_at_input_boundary() -> None:
    for relative in WORKFLOWS:
        text = _workflow_text(relative)

        for legacy, profile in LEGACY_ALIASES.items():
            assert f'{legacy}) TIER="{profile}" ;;' in text

        for old_condition in (
            "matrix.build_type == 'cli'",
            "matrix.build_type == 'server'",
            "matrix.build_type == 'full'",
        ):
            assert old_condition not in text


def test_binary_build_workflows_do_not_use_old_manual_runtime_extras() -> None:
    for relative in WORKFLOWS:
        text = _workflow_text(relative)

        assert "server,tls,web" not in text
        assert "server,tls,web,scraper,newspaper,readability,pdf,mcp" not in text


def test_binary_build_workflows_are_reusable_artifact_builders_only() -> None:
    for relative in WORKFLOWS:
        text = _workflow_text(relative)

        assert "workflow_call:" in text
        assert "candidate_sha:" in text
        assert "ref: ${{ inputs.candidate_sha || github.sha }}" in text
        assert "permissions:\n  contents: read" in text
        assert "- '[0-9]*'" not in text
        assert "softprops/action-gh-release" not in text
        assert "Create Release" not in text
        assert "contents: write" not in text


def test_pyinstaller_windows_binaries_force_embedded_utf8_mode() -> None:
    text = _workflow_text(".github/workflows/build-pyinstaller.yml")
    windows = text.split("- name: Build with PyInstaller (Windows - Full CLI)", maxsplit=1)[1]
    windows = windows.split("- name: Run target-native tier-aware binary smoke", maxsplit=1)[0]
    assert windows.count('--python-option "X utf8=1"') == 3


def test_binary_builders_use_distinct_panel_artifacts_when_called_together() -> None:
    pyinstaller = _workflow_text(".github/workflows/build-pyinstaller.yml")
    nuitka = _workflow_text(".github/workflows/build-nuitka.yml")

    assert "name: pyinstaller-panel-html" in pyinstaller
    assert "name: nuitka-panel-html" in nuitka
    assert "name: panel-html\n" not in pyinstaller
    assert "name: panel-html\n" not in nuitka


def test_basic_binary_keeps_mcp_but_excludes_api_llm_and_full_runtimes() -> None:
    pyinstaller = _workflow_text(".github/workflows/build-pyinstaller.yml")
    nuitka = _workflow_text(".github/workflows/build-nuitka.yml")

    for text in (pyinstaller, nuitka):
        assert "Install MCP runtime required by basic CLI" in text
        assert 'pip install -e ".[mcp]"' in text
        assert "souwen.integrations.mcp_server" in text or "--include-package=mcp" in text

    for forbidden in (
        "--exclude-module=souwen.integrations",
        "--exclude-module=mcp",
        "--exclude-module=uvicorn",
        "--nofollow-import-to=souwen.integrations",
        "--nofollow-import-to=mcp",
        "--nofollow-import-to=uvicorn",
    ):
        assert forbidden not in pyinstaller
        assert forbidden not in nuitka

    assert "--exclude-module=souwen.server" in pyinstaller
    assert "--exclude-module=souwen.llm" in pyinstaller
    assert "--nofollow-import-to=souwen.server" in nuitka
    assert "--nofollow-import-to=souwen.llm" in nuitka


def test_full_binary_explicitly_bundles_superweb2pdf_and_metadata() -> None:
    pyinstaller = _workflow_text(".github/workflows/build-pyinstaller.yml")
    nuitka = _workflow_text(".github/workflows/build-nuitka.yml")

    assert "--hidden-import=superweb2pdf" in pyinstaller
    assert "--collect-submodules=superweb2pdf" in pyinstaller
    assert "--copy-metadata=superweb2pdf" in pyinstaller
    assert "--include-package=superweb2pdf" in nuitka
    assert "--include-package-data=superweb2pdf" in nuitka
    assert "--include-distribution-metadata=superweb2pdf" in nuitka


def test_binaries_embed_and_verify_immutable_source_provenance() -> None:
    pyinstaller = _workflow_text(".github/workflows/build-pyinstaller.yml")
    nuitka = _workflow_text(".github/workflows/build-nuitka.yml")
    smoke = (REPO_ROOT / ".github/actions/binary-smoke/action.yml").read_text(encoding="utf-8")

    assert "runtime.source.sha:." in pyinstaller
    assert "runtime.source.sha;." in pyinstaller
    assert "--include-data-files=runtime.source.sha=runtime.source.sha" in nuitka
    assert 'doctor.get("source_sha") != candidate_sha' in smoke
    assert '"SOUWEN_SOURCE_SHA": candidate_sha' not in smoke


def test_binary_smoke_covers_tier_aware_target_runner_contracts() -> None:
    text = (REPO_ROOT / ".github/actions/binary-smoke/action.yml").read_text(encoding="utf-8")

    for check in (
        "cli/help",
        "cli/version",
        "cli/sources",
        "cli/config-show",
        "cli/doctor-edition",
        "basic/mcp-stdio-config",
        "basic/server-negative",
        "server/health",
        "server/readiness",
        "server/panel",
        "server/admin-locked",
        "server/mcp-loopback",
        "full/article-pdf-plugin-imports",
    ):
        assert check in text

    assert 'socket.create_connection(("127.0.0.1", port), timeout=0.25)' in text
    assert "deadline = time.monotonic() + 60" in text
    assert 'f"serve exit={returncode}, port closed"' in text
    assert '"49651"' not in text
