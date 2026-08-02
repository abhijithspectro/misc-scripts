"""Dispatch GitHub Actions workflow_dispatch via the `gh` CLI.

Tests must inject a fake dispatcher — never call this against a real repo in unit tests.
"""

from __future__ import annotations

import subprocess
import time
from collections.abc import Callable
from typing import Protocol

from dhi_registry_sync.models import DispatchResult, SyncCandidate, SyncPlan


class Dispatcher(Protocol):
    def dispatch(self, *, repo: str, workflow: str, dhi_repository: str) -> DispatchResult: ...


class DryRunDispatcher:
    """Records intended dispatches without calling GitHub."""

    def dispatch(self, *, repo: str, workflow: str, dhi_repository: str) -> DispatchResult:
        return DispatchResult(
            dhi_repository=dhi_repository,
            dispatched=False,
            dry_run=True,
            detail=f"would run: gh workflow run {workflow} --repo {repo} -f dhi_repository={dhi_repository}",
        )


class GhWorkflowDispatcher:
    """Real dispatcher using `gh workflow run`. Do not use in tests."""

    def __init__(self, *, gh_bin: str = "gh") -> None:
        self.gh_bin = gh_bin

    def dispatch(self, *, repo: str, workflow: str, dhi_repository: str) -> DispatchResult:
        cmd = [
            self.gh_bin,
            "workflow",
            "run",
            workflow,
            "--repo",
            repo,
            "-f",
            f"dhi_repository={dhi_repository}",
        ]
        try:
            completed = subprocess.run(
                cmd,
                check=False,
                capture_output=True,
                text=True,
                timeout=120,
                shell=False,
            )
        except FileNotFoundError:
            return DispatchResult(
                dhi_repository=dhi_repository,
                dispatched=False,
                dry_run=False,
                detail="gh CLI not found",
            )
        except subprocess.TimeoutExpired:
            return DispatchResult(
                dhi_repository=dhi_repository,
                dispatched=False,
                dry_run=False,
                detail="gh workflow run timed out",
            )

        if completed.returncode == 0:
            return DispatchResult(
                dhi_repository=dhi_repository,
                dispatched=True,
                dry_run=False,
                detail=(completed.stdout or "workflow_dispatch accepted").strip(),
            )

        err = (completed.stderr or completed.stdout or "workflow_dispatch failed").strip()
        if len(err) > 400:
            err = err[:400] + "…"
        return DispatchResult(
            dhi_repository=dhi_repository,
            dispatched=False,
            dry_run=False,
            detail=err,
        )


def run_plan(
    plan: SyncPlan,
    dispatcher: Dispatcher,
    *,
    sleep: Callable[[float], None] = time.sleep,
) -> SyncPlan:
    """Dispatch each candidate.

    When not dry-run, waits ``plan.delay_seconds`` between consecutive dispatches
    (not after the last one). Dry-run never sleeps.
    """
    results: list[DispatchResult] = []
    total = len(plan.candidates)
    for index, candidate in enumerate(plan.candidates):
        results.append(
            dispatcher.dispatch(
                repo=plan.repo,
                workflow=plan.workflow,
                dhi_repository=candidate.dhi_repository,
            )
        )
        if not plan.dry_run and plan.delay_seconds > 0 and index < total - 1:
            sleep(plan.delay_seconds)
    return plan.model_copy(update={"results": results})


def summarize_candidates(candidates: list[SyncCandidate]) -> list[str]:
    return [c.dhi_repository for c in candidates]
