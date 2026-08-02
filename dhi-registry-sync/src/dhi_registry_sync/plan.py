"""Build a sync plan from a DHI catalog verify report (present images only)."""

from __future__ import annotations

from collections import OrderedDict

from dhi_catalog_check.models import VerifyReport

from dhi_registry_sync.models import SyncCandidate, SyncPlan

DEFAULT_REPO = "spectrocloud/hardened-images"
DEFAULT_WORKFLOW = "self-service-registry-sync.yml"


def candidates_from_verify_report(report: VerifyReport) -> tuple[list[SyncCandidate], list[str]]:
    """Return (candidates from present images, names that were missing).

    The GitHub workflow takes a repository/image slug (`dhi_repository`), not a tag.
    Multiple tags for the same name collapse to one sync candidate.
    """
    by_name: OrderedDict[str, SyncCandidate] = OrderedDict()
    for item in report.present:
        existing = by_name.get(item.name)
        if existing is None:
            by_name[item.name] = SyncCandidate(
                dhi_repository=item.name,
                pack_tags=[item.tag],
                refs=[item.ref],
            )
        else:
            tags = list(existing.pack_tags)
            refs = list(existing.refs)
            if item.tag not in tags:
                tags.append(item.tag)
            if item.ref not in refs:
                refs.append(item.ref)
            by_name[item.name] = SyncCandidate(
                dhi_repository=item.name,
                pack_tags=tags,
                refs=refs,
            )

    skipped = sorted({item.name for item in report.missing})
    return list(by_name.values()), skipped


def build_plan(
    report: VerifyReport,
    *,
    dry_run: bool,
    repo: str = DEFAULT_REPO,
    workflow: str = DEFAULT_WORKFLOW,
    delay_seconds: float = 30.0,
) -> SyncPlan:
    candidates, skipped = candidates_from_verify_report(report)
    return SyncPlan(
        pack_version=report.pack_version,
        repo=repo,
        workflow=workflow,
        dry_run=dry_run,
        delay_seconds=delay_seconds,
        candidates=candidates,
        skipped_missing=skipped,
        results=[],
    )
