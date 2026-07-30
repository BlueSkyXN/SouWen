"""Deterministic transition tests for Action-only HFS paused recovery."""

from __future__ import annotations

import pytest

from scripts.hf_space_recovery_contract import (
    RECOVERY_WORKFLOW_PATH,
    RELEASE_WORKFLOW_PATH,
    RecoveryContractError,
    validate_recovery_topology,
    validate_source_run_provenance,
)


FAILED = "1" * 40
PAUSED = "2" * 40
PRIOR = "3" * 40
PRIOR_SOURCE = "4" * 40


def test_recovery_topology_accepts_settings_only_pause_before_wrapper_sync() -> None:
    topology = validate_recovery_topology(
        paused_space_sha=PRIOR,
        paused_source_sha=PRIOR_SOURCE,
        expected_paused_space_sha=PRIOR,
        expected_paused_source_sha=PRIOR_SOURCE,
        failed_candidate_sha=FAILED,
        prior_space_sha=PRIOR,
        prior_source_sha=PRIOR_SOURCE,
        direct_parent_sha=None,
    )

    assert topology.mode == "settings-only"
    assert topology.sync_parent_sha == PRIOR


def test_recovery_topology_accepts_one_direct_wrapper_advance_and_retry() -> None:
    topology = validate_recovery_topology(
        paused_space_sha=PAUSED,
        paused_source_sha=FAILED,
        expected_paused_space_sha=PAUSED,
        expected_paused_source_sha=FAILED,
        failed_candidate_sha=FAILED,
        prior_space_sha=PRIOR,
        prior_source_sha=PRIOR_SOURCE,
        direct_parent_sha=PRIOR,
    )

    assert topology.mode == "wrapper-advanced"
    assert topology.sync_parent_sha == PAUSED


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        (
            {
                "paused_source_sha": PRIOR_SOURCE,
                "expected_paused_source_sha": PRIOR_SOURCE,
            },
            "failed transaction candidate",
        ),
        ({"direct_parent_sha": "5" * 40}, "descend directly"),
        ({"expected_paused_source_sha": "6" * 40}, "source pin mismatch"),
    ],
)
def test_recovery_topology_rejects_ambiguous_or_unbound_wrapper_state(
    changes: dict[str, str], message: str
) -> None:
    values = {
        "paused_space_sha": PAUSED,
        "paused_source_sha": FAILED,
        "expected_paused_space_sha": PAUSED,
        "expected_paused_source_sha": FAILED,
        "failed_candidate_sha": FAILED,
        "prior_space_sha": PRIOR,
        "prior_source_sha": PRIOR_SOURCE,
        "direct_parent_sha": PRIOR,
    }
    values.update(changes)

    with pytest.raises(RecoveryContractError, match=message):
        validate_recovery_topology(**values)


def _run(path: str, *, display_title: str = "", head_sha: str = FAILED) -> dict:
    return {
        "status": "completed",
        "conclusion": "failure",
        "event": "workflow_dispatch",
        "path": path,
        "head_sha": head_sha,
        "run_attempt": 1,
        "actor": {"login": "BlueSkyXN"},
        "triggering_actor": {"login": "BlueSkyXN"},
        "display_title": display_title,
    }


def _job(name: str, conclusion: str) -> dict[str, str]:
    return {"name": name, "conclusion": conclusion}


def _containment_jobs(*, primary: str = "success", retry: str = "skipped") -> list[dict[str, str]]:
    return [
        _job("Pause Space after failed settings-aware promotion", primary),
        _job("Retry containment when the first pause cannot be proven", retry),
    ]


def _intent(kind: str, run_id: str) -> dict:
    return {
        "schema": "souwen-hfs-transaction-intent-v1",
        "run_id": run_id,
        "run_attempt": 1,
        "workflow_sha": FAILED,
        "candidate_sha": FAILED,
        "version": "2.0.0rc5",
        "transaction_kind": kind,
        "recovery_from_run_id": "123" if kind == "recovery" else "",
        "expected_paused_space_sha": PRIOR if kind == "recovery" else "",
        "expected_paused_source_sha": PRIOR_SOURCE if kind == "recovery" else "",
        "prior_space_sha": PRIOR,
        "prior_source_sha": PRIOR_SOURCE,
        "sync_parent_sha": PRIOR,
    }


def test_release_failure_is_a_valid_contained_recovery_source() -> None:
    run_id = "40000000000"
    kind = validate_source_run_provenance(
        run_id=run_id,
        run=_run(RELEASE_WORKFLOW_PATH),
        jobs=[*_containment_jobs(), _job("Publish GitHub Release", "skipped")],
        owner="BlueSkyXN",
        failed_candidate_sha=FAILED,
        paused_space_sha=PAUSED,
        paused_source_sha=FAILED,
        prior_space_sha=PRIOR,
        prior_source_sha=PRIOR_SOURCE,
        intent=_intent("release", run_id),
    )

    assert kind == "release"


def test_failed_recovery_receipt_is_a_valid_retry_source() -> None:
    run_id = "40000000001"
    title = f"Recover HFS parent={PRIOR} source={PRIOR_SOURCE} from=123456"
    kind = validate_source_run_provenance(
        run_id=run_id,
        run=_run(RECOVERY_WORKFLOW_PATH, display_title=title),
        jobs=[
            _job("Validate paused recovery provenance", "success"),
            *_containment_jobs(),
            _job("Verify recovery outputs", "skipped"),
        ],
        owner="blueskyxn",
        failed_candidate_sha=FAILED,
        paused_space_sha=PAUSED,
        paused_source_sha=FAILED,
        prior_space_sha=PRIOR,
        prior_source_sha=PRIOR_SOURCE,
        intent=_intent("recovery", run_id),
    )

    assert kind == "recovery"


def test_retry_containment_is_an_equivalent_action_verified_pause() -> None:
    run_id = "40000000002"
    kind = validate_source_run_provenance(
        run_id=run_id,
        run=_run(RELEASE_WORKFLOW_PATH),
        jobs=[
            *_containment_jobs(primary="failure", retry="success"),
            _job("Publish GitHub Release", "skipped"),
        ],
        owner="BlueSkyXN",
        failed_candidate_sha=FAILED,
        paused_space_sha=PAUSED,
        paused_source_sha=FAILED,
        prior_space_sha=PRIOR,
        prior_source_sha=PRIOR_SOURCE,
        intent=_intent("release", run_id),
    )

    assert kind == "release"


def test_known_rc5_failure_uses_one_exact_legacy_receipt() -> None:
    candidate = "13d42552283146a8d18a6c9c64ba16124dc20908"
    kind = validate_source_run_provenance(
        run_id="30545216223",
        run=_run(RELEASE_WORKFLOW_PATH, head_sha=candidate),
        jobs=[*_containment_jobs(), _job("Publish GitHub Release", "skipped")],
        owner="BlueSkyXN",
        failed_candidate_sha=candidate,
        paused_space_sha="04f02981aa8d3b7fe16c3ace9a5787fa700d7b20",
        paused_source_sha=candidate,
        prior_space_sha="95c479db55a31fe7b9dde93afc9183c8ec9c47c4",
        prior_source_sha="8f65556df8593dee67662e95be3e29c6a2aec044",
        intent=None,
    )

    assert kind == "legacy-release"


def test_source_run_rerun_attempt_is_rejected() -> None:
    run = _run(RELEASE_WORKFLOW_PATH)
    run["run_attempt"] = 2

    with pytest.raises(RecoveryContractError, match="run provenance"):
        validate_source_run_provenance(
            run_id="40000000004",
            run=run,
            jobs=[*_containment_jobs(), _job("Publish GitHub Release", "skipped")],
            owner="BlueSkyXN",
            failed_candidate_sha=FAILED,
            paused_space_sha=PAUSED,
            paused_source_sha=FAILED,
            prior_space_sha=PRIOR,
            prior_source_sha=PRIOR_SOURCE,
            intent=_intent("release", "40000000004"),
        )


@pytest.mark.parametrize(
    ("path", "title"),
    [
        (RECOVERY_WORKFLOW_PATH, "Recover HFS parent=wrong source=wrong from=1"),
        (".github/workflows/other.yml", ""),
    ],
)
def test_recovery_source_rejects_unbound_or_unsupported_transaction(path: str, title: str) -> None:
    with pytest.raises(RecoveryContractError):
        validate_source_run_provenance(
            run_id="40000000003",
            run=_run(path, display_title=title),
            jobs=[
                _job("Validate paused recovery provenance", "success"),
                *_containment_jobs(),
                _job("Verify recovery outputs", "skipped"),
            ],
            owner="BlueSkyXN",
            failed_candidate_sha=FAILED,
            paused_space_sha=PAUSED,
            paused_source_sha=FAILED,
            prior_space_sha=PRIOR,
            prior_source_sha=PRIOR_SOURCE,
            intent=_intent("recovery", "40000000003"),
        )
