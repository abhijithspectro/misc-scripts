from dhi_catalog_check.models import ImageCheck, VerifyReport

from dhi_registry_sync.plan import build_plan, candidates_from_verify_report


def _report() -> VerifyReport:
    return VerifyReport(
        pack_version="1.19.6",
        registry="dhi.io",
        all_present=False,
        present=[
            ImageCheck(
                name="cilium",
                tag="1.19.6",
                ref="dhi.io/cilium:1.19.6",
                present=True,
            ),
            ImageCheck(
                name="busybox",
                tag="1.37",
                ref="dhi.io/busybox:1.37",
                present=True,
            ),
        ],
        missing=[
            ImageCheck(
                name="ghost",
                tag="0.0.1",
                ref="dhi.io/ghost:0.0.1",
                present=False,
                reason="not_found",
            )
        ],
        checked=3,
    )


def test_candidates_dedupe_and_skip_missing() -> None:
    candidates, skipped = candidates_from_verify_report(_report())
    assert [c.dhi_repository for c in candidates] == ["cilium", "busybox"]
    assert skipped == ["ghost"]


def test_build_plan_dry_run_default_fields() -> None:
    plan = build_plan(_report(), dry_run=True)
    assert plan.dry_run is True
    assert plan.workflow == "self-service-registry-sync.yml"
    assert plan.repo == "spectrocloud/hardened-images"
    assert len(plan.candidates) == 2
    assert plan.results == []
