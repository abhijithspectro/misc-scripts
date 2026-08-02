from dhi_registry_sync.gh_dispatch import DryRunDispatcher, run_plan
from dhi_registry_sync.models import SyncCandidate, SyncPlan


def test_dry_run_dispatcher_never_marks_dispatched() -> None:
    dispatcher = DryRunDispatcher()
    result = dispatcher.dispatch(
        repo="spectrocloud/hardened-images",
        workflow="self-service-registry-sync.yml",
        dhi_repository="cilium",
    )
    assert result.dry_run is True
    assert result.dispatched is False
    assert "gh workflow run" in result.detail
    assert "dhi_repository=cilium" in result.detail


def test_run_plan_uses_injected_dispatcher_only() -> None:
    calls: list[str] = []

    class RecordingDispatcher:
        def dispatch(self, *, repo: str, workflow: str, dhi_repository: str):
            calls.append(dhi_repository)
            return DryRunDispatcher().dispatch(
                repo=repo,
                workflow=workflow,
                dhi_repository=dhi_repository,
            )

    plan = SyncPlan(
        pack_version="1.19.6",
        repo="spectrocloud/hardened-images",
        workflow="self-service-registry-sync.yml",
        dry_run=True,
        delay_seconds=30.0,
        candidates=[
            SyncCandidate(dhi_repository="cilium", pack_tags=["1.19.6"], refs=[]),
            SyncCandidate(dhi_repository="busybox", pack_tags=["1.37"], refs=[]),
        ],
    )
    sleeps: list[float] = []
    updated = run_plan(plan, RecordingDispatcher(), sleep=sleeps.append)
    assert calls == ["cilium", "busybox"]
    assert sleeps == []  # dry-run must not delay
    assert all(not r.dispatched for r in updated.results)
    assert all(r.dry_run for r in updated.results)


def test_execute_plan_delays_between_dispatches() -> None:
    plan = SyncPlan(
        pack_version="1.19.6",
        repo="spectrocloud/hardened-images",
        workflow="self-service-registry-sync.yml",
        dry_run=False,
        delay_seconds=30.0,
        candidates=[
            SyncCandidate(dhi_repository="cilium", pack_tags=["1.19.6"], refs=[]),
            SyncCandidate(dhi_repository="busybox", pack_tags=["1.37"], refs=[]),
            SyncCandidate(dhi_repository="ztunnel", pack_tags=["1.30"], refs=[]),
        ],
    )
    sleeps: list[float] = []

    class FakeDispatcher:
        def dispatch(self, *, repo: str, workflow: str, dhi_repository: str):
            from dhi_registry_sync.models import DispatchResult

            return DispatchResult(
                dhi_repository=dhi_repository,
                dispatched=True,
                dry_run=False,
                detail="ok",
            )

    updated = run_plan(plan, FakeDispatcher(), sleep=sleeps.append)
    assert [r.dhi_repository for r in updated.results] == ["cilium", "busybox", "ztunnel"]
    assert sleeps == [30.0, 30.0]  # between 1→2 and 2→3, not after last
