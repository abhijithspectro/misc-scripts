import json
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from dhi_registry_sync.gh_dispatch import DryRunDispatcher, GhWorkflowDispatcher, run_plan
from dhi_registry_sync.models import SyncPlan
from dhi_registry_sync.plan import DEFAULT_REPO, DEFAULT_WORKFLOW, build_plan
from dhi_registry_sync.source import load_verify_report, run_dhi_lookup

console = Console()
err_console = Console(stderr=True)


@click.group()
@click.version_option(package_name="dhi-registry-sync")
def main() -> None:
    """Plan / dispatch hardened-images self-service registry sync for Cilium DHI images.

    Default mode is dry-run: it never triggers GitHub Actions runners.
    Pass --execute only after review to dispatch the real workflow.
    """


@main.command("sync")
@click.option(
    "--version",
    "pack_version",
    required=True,
    help="Cilium pack version (e.g. 1.19.6)",
)
@click.option(
    "--verify-report",
    "verify_report_path",
    type=click.Path(path_type=Path, exists=True, dir_okay=False),
    default=None,
    help="Reuse a prior dhi-catalog-check JSON report (skips live DHI lookup)",
)
@click.option(
    "--repo",
    default=DEFAULT_REPO,
    show_default=True,
    help="GitHub repo that owns the workflow",
)
@click.option(
    "--workflow",
    default=DEFAULT_WORKFLOW,
    show_default=True,
    help="Workflow file name or ID",
)
@click.option(
    "--execute/--dry-run",
    "execute",
    default=False,
    show_default=True,
    help="Actually dispatch workflow_dispatch (default: dry-run, no runners used)",
)
@click.option(
    "--delay-seconds",
    type=float,
    default=30.0,
    show_default=True,
    help="Seconds to wait between consecutive workflow dispatches (execute mode only)",
)
@click.option(
    "--require-all-present/--allow-partial",
    default=True,
    show_default=True,
    help="Refuse to plan/dispatch if any pack image failed DHI lookup",
)
@click.option(
    "--docker-bin",
    default="docker",
    show_default=True,
)
@click.option(
    "--max-workers",
    type=int,
    default=8,
    show_default=True,
)
@click.option(
    "--output",
    "output_path",
    type=click.Path(path_type=Path, dir_okay=False),
    default=None,
    help="Write plan/results JSON to this file",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["json", "human"], case_sensitive=False),
    default="human",
    show_default=True,
)
def sync_cmd(
    pack_version: str,
    verify_report_path: Path | None,
    repo: str,
    workflow: str,
    execute: bool,
    delay_seconds: float,
    require_all_present: bool,
    docker_bin: str,
    max_workers: int,
    output_path: Path | None,
    output_format: str,
) -> None:
    """Build a sync plan from DHI lookup; dry-run by default."""
    if delay_seconds < 0:
        err_console.print("[red]error:[/red] --delay-seconds must be >= 0")
        raise SystemExit(2)

    if execute:
        err_console.print(
            "[yellow]EXECUTE mode:[/yellow] will dispatch "
            f"{workflow} on {repo} for each present image "
            f"(delay {delay_seconds:g}s between runs)"
        )

    try:
        if verify_report_path is not None:
            report = load_verify_report(verify_report_path)
            if report.pack_version and report.pack_version != pack_version:
                err_console.print(
                    f"[yellow]warning:[/yellow] report pack_version "
                    f"{report.pack_version!r} != --version {pack_version!r}; "
                    "using report version"
                )
                pack_version = report.pack_version
        else:
            report = run_dhi_lookup(
                pack_version,
                docker_bin=docker_bin,
                max_workers=max_workers,
            )
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        err_console.print(f"[red]error:[/red] {type(exc).__name__}: {exc}")
        raise SystemExit(2) from exc

    if require_all_present and not report.all_present:
        missing = ", ".join(f"{m.name}:{m.tag}" for m in report.missing)
        err_console.print(
            f"[red]error:[/red] DHI lookup incomplete; missing: {missing}. "
            "Fix lookups or pass --allow-partial."
        )
        raise SystemExit(2)

    plan = build_plan(
        report,
        dry_run=not execute,
        repo=repo,
        workflow=workflow,
        delay_seconds=delay_seconds,
    )
    if not plan.candidates:
        err_console.print("[red]error:[/red] no present images to sync")
        raise SystemExit(2)

    dispatcher: DryRunDispatcher | GhWorkflowDispatcher
    if execute:
        dispatcher = GhWorkflowDispatcher()
    else:
        dispatcher = DryRunDispatcher()

    plan = run_plan(plan, dispatcher)
    _emit(plan, output_format=output_format, output_path=output_path)

    if execute and any(not item.dispatched for item in plan.results):
        raise SystemExit(1)


def _emit(plan: SyncPlan, *, output_format: str, output_path: Path | None) -> None:
    payload = plan.model_dump()
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        err_console.print(f"Wrote plan: {output_path}")

    if output_format.lower() == "json":
        console.print_json(data=payload)
        return

    mode = "DRY-RUN (no workflow dispatched)" if plan.dry_run else "EXECUTE"
    console.print(f"Mode:         {mode}")
    console.print(f"Pack version: {plan.pack_version}")
    console.print(f"Repo:         {plan.repo}")
    console.print(f"Workflow:     {plan.workflow}")
    console.print(f"Delay:        {plan.delay_seconds:g}s between dispatches (execute only)")
    console.print(f"Candidates:   {len(plan.candidates)}")
    if plan.skipped_missing:
        console.print(f"Skipped (missing from DHI): {', '.join(plan.skipped_missing)}")

    table = Table(title="Sync plan")
    table.add_column("dhi_repository")
    table.add_column("pack tags")
    table.add_column("status")
    table.add_column("detail")
    result_by_name = {r.dhi_repository: r for r in plan.results}
    for candidate in plan.candidates:
        result = result_by_name.get(candidate.dhi_repository)
        if result is None:
            status = "?"
            detail = ""
        elif result.dry_run:
            status = "dry-run"
            detail = result.detail
        elif result.dispatched:
            status = "dispatched"
            detail = result.detail
        else:
            status = "failed"
            detail = result.detail
        table.add_row(
            candidate.dhi_repository,
            ", ".join(candidate.pack_tags),
            status,
            detail,
        )
    console.print(table)

    if plan.dry_run:
        console.print(
            "\n[green]No GitHub Actions runners were used.[/green] "
            "Re-run with [bold]--execute[/bold] after review to dispatch."
        )


if __name__ == "__main__":
    main()
