from __future__ import annotations

import textwrap
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIR = REPO_ROOT / ".github" / "workflows"


def _workflow(name: str) -> str:
    return (WORKFLOW_DIR / name).read_text(encoding="utf-8")


def test_workflow_embedded_python_blocks_compile() -> None:
    paths = list(WORKFLOW_DIR.glob("*.yml"))
    paths.extend((REPO_ROOT / ".github" / "actions").glob("*/action.yml"))
    compiled = 0

    for path in paths:
        lines = path.read_text(encoding="utf-8").splitlines()
        index = 0
        while index < len(lines):
            if "<<'PY'" not in lines[index] or "python" not in lines[index]:
                index += 1
                continue
            end = index + 1
            while end < len(lines) and lines[end].strip() != "PY":
                end += 1
            assert end < len(lines), f"unclosed Python heredoc: {path}:{index + 1}"
            source = textwrap.dedent("\n".join(lines[index + 1 : end])) + "\n"
            compile(source, f"{path}:{index + 2}", "exec")
            compiled += 1
            index = end + 1

    assert compiled >= 19


def test_release_candidate_is_the_only_release_publisher() -> None:
    candidate = _workflow("release-candidate.yml")
    assert "workflow_dispatch:" in candidate
    assert "push:" not in candidate.split("jobs:", maxsplit=1)[0]
    assert "environment:\n      name: release" in candidate
    assert "gh release create" in candidate
    assert 'git tag -a "$TAG" "$CANDIDATE_SHA"' in candidate
    assert 'git push origin "refs/tags/$TAG"' in candidate
    assert "--draft" in candidate
    assert 'gh release edit "$TAG" --draft=false' in candidate
    assert "report_partial_release" in candidate
    assert "Do not move or overwrite this tag" in candidate
    assert "remote_tag_state=unknown" in candidate
    assert "release_state=unknown" in candidate
    assert 'git ls-remote --tags origin "refs/tags/$TAG" || true' not in candidate

    for path in WORKFLOW_DIR.glob("*.yml"):
        if path.name == "release-candidate.yml":
            continue
        text = path.read_text(encoding="utf-8")
        assert "softprops/action-gh-release" not in text
        assert "gh release create" not in text


def test_release_candidate_strictly_validates_promotion_inputs() -> None:
    text = _workflow("release-candidate.yml")
    trust_step = text.split(
        "- name: Validate candidate trust, SHA, version, and promotion controls",
        maxsplit=1,
    )[1].split("- uses: actions/setup-python@v6", maxsplit=1)[0]
    assert "python3 -I - <<'PY'" in trust_step
    assert "python3 - <<'PY'" not in trust_step
    assert "re.fullmatch(r'[0-9a-f]{40}', candidate)" in text
    assert "project_version != version" in text
    assert "publish == 'true' and deploy_hfs != 'true'" in text
    assert "publish and deploy_hfs must be typed booleans" in text
    assert "refusing to overwrite existing tag" in text
    assert "runtime_version != version" in text
    assert "openapi_version != version" in text
    assert "panel_lock['version'] != panel['version']" in text
    assert "for readme_name in ('README.md', 'README.en.md')" in text
    assert "r'(?:a|b|rc)[0-9]+'" in text
    assert "accepted prerelease candidate" in text
    assert text.index("git', 'merge-base', '--is-ancestor'") < text.index(
        'pip install -e ".[edition-pro]"'
    )
    assert "release-candidate must run from the current origin/main control plane" in text
    assert "candidate_sha to equal the current origin/main" in text
    assert "verifier_sha" in text
    assert text.count("secrets: inherit") == 1
    hfs_call = text.split("  hfs:", maxsplit=1)[1].split("  assemble:", maxsplit=1)[0]
    assert "uses: ./.github/workflows/deploy-hf-space.yml" in hfs_call
    assert "secrets: inherit" in hfs_call


def test_only_hfs_reusable_call_inherits_secrets() -> None:
    inherited = {
        path.name: path.read_text(encoding="utf-8").count("secrets: inherit")
        for path in WORKFLOW_DIR.glob("*.yml")
        if "secrets: inherit" in path.read_text(encoding="utf-8")
    }
    assert inherited == {"release-candidate.yml": 1}


def test_release_candidate_aggregates_all_release_gates() -> None:
    text = _workflow("release-candidate.yml")
    for call in (
        "uses: ./.github/workflows/v2-ci.yml",
        "uses: ./.github/workflows/external-smoke-gate.yml",
        "uses: ./.github/workflows/build-pyinstaller.yml",
        "uses: ./.github/workflows/build-nuitka.yml",
        "uses: ./.github/workflows/deploy-hf-space.yml",
    ):
        assert call in text

    for gate in ("source", "external", "pyinstaller", "nuitka", "clean-install", "container"):
        assert f"  {gate}:" in text
    assert "name: V2 source and Panel gates" in text
    assert "name: Broad CI, coverage, performance, audit, and container gates" in text
    assert "suite: release" in text

    external = text.split("  external:", maxsplit=1)[1].split("  pyinstaller:", maxsplit=1)[0]
    assert "permissions:\n      contents: read\n      issues: write" in external

    container = text.split("  container:", maxsplit=1)[1].split("  hfs:", maxsplit=1)[0]
    assert "ref: ${{ needs.validate.outputs.candidate_sha }}\n          fetch-depth: 0" in container


def test_release_bundle_has_24_binaries_supply_chain_assets_and_attestation() -> None:
    text = _workflow("release-candidate.yml")
    assert "if len(actual) != 24:" in text
    assert "python-sbom.cdx.json" in text
    assert "panel-sbom.cdx.json" in text
    assert "release-manifest.json" in text
    assert "SHA256SUMS" in text
    assert "actions/attest-build-provenance@v4" in text
    assert "attestations: write" in text
    assert "id-token: write" in text
    assert "name: release-candidate-${{ needs.validate.outputs.version }}" in text
    assert "'bundle_envelope'" in text
    assert "SHA256SUMS must cover every asset except itself" in text
    assert "sha256sum -c SHA256SUMS" in text
    for manifest_field in (
        "'candidate_ref'",
        "'verifier_sha'",
        "'created_at'",
        "'remote_runs'",
        "'containers'",
        "'hfs'",
        "'exceptions'",
    ):
        assert manifest_field in text
    for hfs_evidence_field in (
        "'prior_repo_sha'",
        "'prior_runtime_sha'",
        "'prior_source_sha'",
        "'prior_runtime_stage'",
        "'promotion_changed'",
    ):
        assert hfs_evidence_field in text


def test_binary_smoke_preserves_help_tracebacks_for_cross_platform_diagnostics() -> None:
    text = (REPO_ROOT / ".github/actions/binary-smoke/action.yml").read_text(encoding="utf-8")
    assert 'if name == "cli/help" and len(detail) > 4000:' in text
    assert "... traceback middle omitted ..." in text
    assert 'detail = f"{detail[:750]}\\n' in text
    assert '{detail[-3200:]}"' in text


def test_ci_has_stable_aggregate_and_required_readiness_gates() -> None:
    text = _workflow("ci.yml")
    assert "name: CI / aggregate" in text
    assert "name: V2 CI / v2 release readiness summary" in _workflow("v2-ci.yml")
    assert "--cov-fail-under=67" in text
    assert "--cov-fail-under=90" in text
    assert "name: Clean wheel (${{ matrix.extra }})" in text
    for extra in (
        "edition-basic",
        "edition-pro",
        "edition-full",
        "edition-full-crawl4ai",
        "edition-full-scrapling",
    ):
        assert f"extra: {extra}" in text
    assert "samples = []" in text
    assert "for _ in range(7):" in text
    assert "pip-audit --local" in text
    assert '"setuptools>=83"' in text
    assert "npm audit --omit=dev --audit-level=high --json" in text
    assert "pip-audit.json" in text
    assert "npm-audit.json" in text
    assert "--mode fixture" in text
    for threshold in ("1.50", "2.00", "2.50"):
        assert threshold in text
    for dockerfile in ("Dockerfile", "cloud/hfs/Dockerfile", "cloud/modelscope/Dockerfile"):
        assert f"dockerfile: {dockerfile}" in text

    container = text.split("  container-surface:", maxsplit=1)[1].split("  aggregate:", maxsplit=1)[
        0
    ]
    candidate_expression = (
        "${{ inputs.candidate_sha || github.event.pull_request.head.sha || github.sha }}"
    )
    assert f"SOURCE_SHA: {candidate_expression}" in container
    assert f"ref: {candidate_expression}" in container
    assert "fetch-depth: 0" in container
    assert 'git push "$bare" HEAD:refs/heads/ci-candidate' in container


def test_hfs_reusable_promotion_is_candidate_pinned_and_live_verified() -> None:
    text = _workflow("deploy-hf-space.yml")
    candidate_expression = (
        "${{ inputs.candidate_sha || github.event.pull_request.head.sha || github.sha }}"
    )
    contract_step = text.split("- name: Validate reusable candidate contract", maxsplit=1)[1].split(
        "- name: Detect deploy-related path changes", maxsplit=1
    )[0]
    assert "python3 -I - <<'PY'" in contract_step
    assert "python3 - <<'PY'" not in contract_step
    assert "workflow_call:" in text
    assert "candidate_sha:" in text
    assert "verifier_sha:" in text
    workflow_call = text.split("  workflow_call:", maxsplit=1)[1].split(
        "  pull_request:", maxsplit=1
    )[0]
    for secret_name in (
        "HF_TOKEN",
        "HF_SPACE_READ_TOKEN",
        "SOUWEN_SMOKE_BEARER_TOKEN",
    ):
        assert f"      {secret_name}:" not in workflow_call
    assert "    secrets:" not in workflow_call
    assert workflow_call.count("required: true") == 4
    assert text.count(candidate_expression) >= 10
    assert "${{ inputs.candidate_sha || github.sha }}" not in text
    assert 'expected_pin = f"ARG SOUWEN_REF={candidate_sha}"' in text
    assert 'last_runtime_sha = str(runtime.raw.get("sha") or "unknown")' in text
    assert "last_runtime_sha == expected_sha" in text
    assert "SOUWEN_SMOKE_BEARER_TOKEN is required for candidate promotion" in text
    assert "EXPECTED_SOUWEN_SOURCE_SHA" in text
    assert "'.role == \"admin\" and .admin_open == false'" in text
    assert "name: hf" in text
    assert "  push:" not in text.split("jobs:", maxsplit=1)[0]
    assert "target_info.private is not True" in text
    assert "unauth_status" in text
    assert "github.event_name == 'workflow_call'" not in text
    assert "if: ${{ inputs.deploy_hfs }}" in text
    assert 'write_output(True, "release-candidate")' in text
    assert "inputs.deploy_hfs && 'promotion'" in text
    assert "cancel-in-progress: ${{ !inputs.deploy_hfs }}" in text
    assert "prior_space_commit_sha" in text
    assert "prior_runtime_commit_sha" in text
    assert "prior_souwen_ref" in text
    assert "prior_runtime_stage" in text
    assert "parent_commit=prior_space_sha" in text
    assert "revision=prior_space_sha" in text
    assert "  rollback-space:" in text
    assert "needs.post-deploy-smoke.result != 'success'" in text
    assert "CommitOperationDelete" in text
    assert "rollback_space_commit_sha" in text
    assert "  pause-space:" in text
    assert "api.pause_space" in text
    assert "needs.rollback-space.result == 'cancelled'" in text
    assert "HF_SPACE_READ_TOKEN" in text
    assert '"X-SouWen-Token: $SOUWEN_SMOKE_BEARER_TOKEN"' in text

    secret_gate = text.split("- name: Require HFS deployment secrets", maxsplit=1)[1].split(
        "- uses: actions/checkout@v6", maxsplit=1
    )[0]
    for secret_name in (
        "HF_TOKEN",
        "HF_SPACE_READ_TOKEN",
        "SOUWEN_SMOKE_BEARER_TOKEN",
    ):
        assert f"{secret_name}: ${{{{ secrets.{secret_name} }}}}" in secret_gate
    assert "Required HFS environment secret is not configured: $name" in secret_gate
    assert "${!name}" in secret_gate

    prior = text.split("- name: Capture immutable rollback point", maxsplit=1)[1].split(
        "- name: Sync changed HFS wrapper files", maxsplit=1
    )[0]
    assert 'stage_upper.endswith("SLEEPING")' in prior
    assert '"PAUSED"' in prior
    assert "api.restart_space" not in prior

    rollback = text.split("  rollback-space:", maxsplit=1)[1].split("  pause-space:", maxsplit=1)[0]
    assert "rollback_sha = prior_sha" in rollback
    assert "Space head still matches the rollback point" in rollback
    assert "no distinct forward rollback commit" not in rollback

    post_deploy = text.split("  post-deploy-smoke:", maxsplit=1)[1].split(
        "  rollback-space:", maxsplit=1
    )[0]
    assert "ref: ${{ inputs.verifier_sha }}" in post_deploy
    assert "cd trusted-verifier" in post_deploy
    assert "ref: ${{ inputs.candidate_sha || github.sha }}" not in post_deploy


def test_hfs_rebuild_job_avoids_checkout_and_dependency_cache() -> None:
    text = _workflow("deploy-hf-space.yml")
    rebuild = text.split("  rebuild-space:", maxsplit=1)[1].split(
        "  post-deploy-smoke:", maxsplit=1
    )[0]

    assert "actions/setup-python@v6" in rebuild
    assert "actions/checkout@" not in rebuild
    assert "cache: pip" not in rebuild


def test_external_release_gate_requires_superweb2pdf_runtime_fixture() -> None:
    text = _workflow("external-smoke-gate.yml")
    assert "Plugin and SuperWeb2PDF release/nightly gate" in text
    assert 'pip install -e ".[dev,edition-full]"' in text
    assert "python -m playwright install --with-deps chromium" in text
    assert "--require-web2pdf-runtime" in text
    assert "--timeout 45" in text
    assert "external-gate-plugin-report" in text


def test_superweb2pdf_workflow_install_is_commit_and_hash_pinned() -> None:
    text = _workflow("ci.yml")
    assert (
        "d1e1da59d739ad46222b5e726bd6f28b0d0453fa.zip"
        "#sha256=f56a380aa3f06d169d3fcc723d5525779519afaff159b37e8a789e50b797c76b"
    ) in text
    assert 'd1e1da59d739ad46222b5e726bd6f28b0d0453fa.zip"' not in text


def test_clean_wheel_composite_enforces_edition_and_package_boundaries() -> None:
    text = (REPO_ROOT / ".github/actions/clean-wheel-smoke/action.yml").read_text(encoding="utf-8")
    for contract in (
        "package/panel",
        "package/no-retired-imports",
        "runtime/mcp-stdio-server",
        "basic/no-fastapi",
        "basic/three-fetch-providers",
        "basic/llm-gated",
        "pro/server-import",
        "full/import-pymupdf4llm",
        "full/import-superweb2pdf",
        "variant/crawl4ai-only",
        "variant/scrapling-only",
        "expected_missing_fetch_providers",
    ):
        assert contract in text
