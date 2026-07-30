"""Pure fail-closed contracts shared by the HFS recovery workflows and tests."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import re
from typing import Any


RELEASE_WORKFLOW_PATH = ".github/workflows/release-candidate.yml"
RECOVERY_WORKFLOW_PATH = ".github/workflows/recover-hf-space.yml"
_LEGACY_RELEASE_RECEIPTS = {
    "30545216223": {
        "candidate_sha": "13d42552283146a8d18a6c9c64ba16124dc20908",
        "paused_space_sha": "04f02981aa8d3b7fe16c3ace9a5787fa700d7b20",
        "paused_source_sha": "13d42552283146a8d18a6c9c64ba16124dc20908",
        "prior_space_sha": "95c479db55a31fe7b9dde93afc9183c8ec9c47c4",
        "prior_source_sha": "8f65556df8593dee67662e95be3e29c6a2aec044",
    }
}


class RecoveryContractError(RuntimeError):
    """The supplied transaction evidence does not identify one recoverable state."""


@dataclass(frozen=True, slots=True)
class RecoveryTopology:
    mode: str
    sync_parent_sha: str


def validate_recovery_topology(
    *,
    paused_space_sha: str,
    paused_source_sha: str,
    expected_paused_space_sha: str,
    expected_paused_source_sha: str,
    failed_candidate_sha: str,
    prior_space_sha: str,
    prior_source_sha: str,
    direct_parent_sha: str | None,
) -> RecoveryTopology:
    """Accept only settings-only or one-direct-wrapper-advance paused states."""
    if paused_space_sha != expected_paused_space_sha:
        raise RecoveryContractError("paused recovery Space SHA mismatch")
    if paused_source_sha != expected_paused_source_sha:
        raise RecoveryContractError("paused recovery source pin mismatch")

    if paused_space_sha == prior_space_sha:
        if paused_source_sha != prior_source_sha:
            raise RecoveryContractError(
                "settings-only recovery must retain the exact prior source pin"
            )
        return RecoveryTopology(mode="settings-only", sync_parent_sha=paused_space_sha)

    if paused_source_sha != failed_candidate_sha:
        raise RecoveryContractError(
            "wrapper-advanced recovery must pin the failed transaction candidate"
        )
    if direct_parent_sha != prior_space_sha:
        raise RecoveryContractError(
            "wrapper-advanced recovery must descend directly from the expected prior wrapper"
        )
    return RecoveryTopology(mode="wrapper-advanced", sync_parent_sha=paused_space_sha)


def _unique_job_conclusion(
    jobs: Sequence[Mapping[str, Any]],
    suffix: str,
    *,
    required: bool = True,
) -> str | None:
    matches = [
        job.get("conclusion")
        for job in jobs
        if isinstance(job.get("name"), str) and job["name"].endswith(suffix)
    ]
    if len(matches) != 1:
        if not required and not matches:
            return None
        raise RecoveryContractError("failed transaction job inventory mismatch")
    conclusion = matches[0]
    return conclusion if isinstance(conclusion, str) else None


def validate_source_run_provenance(
    *,
    run_id: str,
    run: Mapping[str, Any],
    jobs: Sequence[Mapping[str, Any]],
    owner: str,
    failed_candidate_sha: str,
    paused_space_sha: str,
    paused_source_sha: str,
    prior_space_sha: str,
    prior_source_sha: str,
    intent: Mapping[str, Any] | None,
) -> str:
    """Validate a failed release or a validated, contained recovery retry receipt."""
    expected = {
        "status": "completed",
        "conclusion": "failure",
        "event": "workflow_dispatch",
        "head_sha": failed_candidate_sha,
        "run_attempt": 1,
    }
    if any(run.get(name) != value for name, value in expected.items()):
        raise RecoveryContractError("failed transaction run provenance mismatch")
    if any(
        not isinstance(run.get(name), Mapping)
        or str(run[name].get("login", "")).casefold() != owner.casefold()
        for name in ("actor", "triggering_actor")
    ):
        raise RecoveryContractError("failed transaction actor provenance mismatch")

    path = run.get("path")
    containment = _unique_job_conclusion(jobs, "Pause Space after failed settings-aware promotion")
    retry_containment = _unique_job_conclusion(
        jobs,
        "Retry containment when the first pause cannot be proven",
    )
    containment_proven = (containment == "success" and retry_containment == "skipped") or (
        containment in {"failure", "cancelled"} and retry_containment == "success"
    )
    if not containment_proven:
        raise RecoveryContractError("failed transaction containment mismatch")

    if path == RELEASE_WORKFLOW_PATH:
        publication = _unique_job_conclusion(jobs, "Publish GitHub Release")
        if publication != "skipped":
            raise RecoveryContractError("failed release publication state mismatch")
        legacy = _LEGACY_RELEASE_RECEIPTS.get(run_id)
        if legacy is not None:
            supplied = {
                "candidate_sha": failed_candidate_sha,
                "paused_space_sha": paused_space_sha,
                "paused_source_sha": paused_source_sha,
                "prior_space_sha": prior_space_sha,
                "prior_source_sha": prior_source_sha,
            }
            if supplied != legacy:
                raise RecoveryContractError("legacy failed release receipt mismatch")
            return "legacy-release"
        _validate_machine_intent(
            intent=intent,
            run_id=run_id,
            kind="release",
            failed_candidate_sha=failed_candidate_sha,
            paused_space_sha=paused_space_sha,
            paused_source_sha=paused_source_sha,
            prior_space_sha=prior_space_sha,
            prior_source_sha=prior_source_sha,
        )
        return "release"

    if path == RECOVERY_WORKFLOW_PATH:
        validation = _unique_job_conclusion(jobs, "Validate paused recovery provenance")
        verification = _unique_job_conclusion(jobs, "Verify recovery outputs")
        publication = _unique_job_conclusion(
            jobs,
            "Publish GitHub Release",
            required=False,
        )
        expected_title = re.compile(
            rf"^Recover HFS parent={re.escape(prior_space_sha)} "
            rf"source={re.escape(prior_source_sha)} from=[0-9]+$"
        )
        if (
            validation != "success"
            or verification != "skipped"
            or publication is not None
            or expected_title.fullmatch(str(run.get("display_title", ""))) is None
        ):
            raise RecoveryContractError("failed recovery transaction receipt mismatch")
        _validate_machine_intent(
            intent=intent,
            run_id=run_id,
            kind="recovery",
            failed_candidate_sha=failed_candidate_sha,
            paused_space_sha=paused_space_sha,
            paused_source_sha=paused_source_sha,
            prior_space_sha=prior_space_sha,
            prior_source_sha=prior_source_sha,
        )
        return "recovery"

    raise RecoveryContractError("unsupported recovery source workflow")


def _validate_machine_intent(
    *,
    intent: Mapping[str, Any] | None,
    run_id: str,
    kind: str,
    failed_candidate_sha: str,
    paused_space_sha: str,
    paused_source_sha: str,
    prior_space_sha: str,
    prior_source_sha: str,
) -> None:
    if intent is None:
        raise RecoveryContractError("failed transaction machine intent is required")
    expected = {
        "schema": "souwen-hfs-transaction-intent-v1",
        "run_id": run_id,
        "run_attempt": 1,
        "workflow_sha": failed_candidate_sha,
        "candidate_sha": failed_candidate_sha,
        "version": "2.0.0rc5",
        "transaction_kind": kind,
    }
    if any(intent.get(name) != value for name, value in expected.items()):
        raise RecoveryContractError("failed transaction machine intent mismatch")

    if kind == "release":
        if (
            intent.get("prior_space_sha") != prior_space_sha
            or intent.get("prior_source_sha") != prior_source_sha
            or intent.get("sync_parent_sha") != prior_space_sha
            or intent.get("recovery_from_run_id") != ""
        ):
            raise RecoveryContractError("failed release machine intent mismatch")
    elif (
        intent.get("expected_paused_space_sha") != prior_space_sha
        or intent.get("expected_paused_source_sha") != prior_source_sha
        or intent.get("sync_parent_sha") != prior_space_sha
        or not str(intent.get("recovery_from_run_id", "")).isdigit()
    ):
        raise RecoveryContractError("failed recovery machine intent mismatch")

    if paused_space_sha == prior_space_sha:
        if paused_source_sha != prior_source_sha:
            raise RecoveryContractError("settings-only machine intent mismatch")
    elif paused_source_sha != failed_candidate_sha:
        raise RecoveryContractError("wrapper-advanced machine intent mismatch")
