import json
from pathlib import Path

import click
import httpx
from rich.console import Console
from rich.table import Table

from cilium_pack_images.compare import compare_files
from cilium_pack_images.models import CompareReport, PrepareReport
from cilium_pack_images.prepare import (
    prepare_version,
    report_to_detailed_payload,
    report_to_names_payload,
    report_to_pack_images_yaml,
    write_history,
)

console = Console()
err_console = Console(stderr=True)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MAPPING = PROJECT_ROOT / "mapping.yaml"
DEFAULT_HISTORY = PROJECT_ROOT / "history.yaml"
DEFAULT_CACHE = PROJECT_ROOT / ".cache" / "charts"


@click.group()
@click.version_option(package_name="cilium-pack-images")
def main() -> None:
    """Audit / prepare Cilium pack images from upstream Helm charts."""


@main.command("compare")
@click.option(
    "--pack-values",
    "pack_values_path",
    type=click.Path(path_type=Path, exists=True, dir_okay=False),
    required=True,
    help="Pack values.yaml containing pack.content.images metadata",
)
@click.option(
    "--chart-values",
    "chart_values_path",
    type=click.Path(path_type=Path, exists=True, dir_okay=False),
    required=True,
    help="Upstream charts/cilium/values.yaml",
)
@click.option(
    "--mapping",
    "mapping_path",
    type=click.Path(path_type=Path, exists=True, dir_okay=False),
    default=DEFAULT_MAPPING,
    show_default=True,
    help="Pack name ↔ chart path mapping file",
)
@click.option(
    "--fail-on-drift/--no-fail-on-drift",
    default=True,
    show_default=True,
    help="Exit non-zero when findings are present",
)
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    help="Emit machine-readable JSON report",
)
def compare_cmd(
    pack_values_path: Path,
    chart_values_path: Path,
    mapping_path: Path,
    fail_on_drift: bool,
    as_json: bool,
) -> None:
    """Compare local pack metadata images to a chart values file."""
    try:
        report = compare_files(pack_values_path, chart_values_path, mapping_path)
    except (OSError, ValueError, KeyError) as exc:
        err_console.print(f"[red]error:[/red] {exc}")
        raise SystemExit(2) from exc

    if as_json:
        console.print_json(data=report.model_dump())
    else:
        _print_compare(report)

    if fail_on_drift and not report.ok:
        raise SystemExit(1)


@main.command("prepare")
@click.option(
    "--version",
    "pack_version",
    required=True,
    help="Cilium / pack version (e.g. 1.19.5). Only required input for a normal bump.",
)
@click.option(
    "--mapping",
    "mapping_path",
    type=click.Path(path_type=Path, exists=True, dir_okay=False),
    default=DEFAULT_MAPPING,
    show_default=True,
)
@click.option(
    "--history",
    "history_path",
    type=click.Path(path_type=Path, dir_okay=False),
    default=DEFAULT_HISTORY,
    show_default=True,
    help="Historical pack tags (used when pack_tag.source=history)",
)
@click.option(
    "--previous-pack-values",
    "previous_pack_values_path",
    type=click.Path(path_type=Path, exists=True, dir_okay=False),
    default=None,
    help="Optional previous pack values.yaml to seed history instead of --history",
)
@click.option(
    "--chart-values",
    "chart_values_path",
    type=click.Path(path_type=Path, exists=True, dir_okay=False),
    default=None,
    help="Use a local chart values.yaml instead of fetching upstream",
)
@click.option(
    "--cache-dir",
    type=click.Path(path_type=Path, file_okay=False),
    default=DEFAULT_CACHE,
    show_default=True,
    help="Directory to cache fetched upstream charts",
)
@click.option(
    "--output",
    "output_path",
    type=click.Path(path_type=Path, dir_okay=False),
    default=None,
    help="Write pack.content.images YAML fragment to this file",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["human", "names", "detailed"], case_sensitive=False),
    default="human",
    show_default=True,
    help="Stdout format: human table, names JSON, or detailed JSON with versions",
)
@click.option(
    "--names-output",
    "names_output_path",
    type=click.Path(path_type=Path, dir_okay=False),
    default=None,
    help="Write names-only JSON ({images: [...]}) to this file",
)
@click.option(
    "--detailed-output",
    "detailed_output_path",
    type=click.Path(path_type=Path, dir_okay=False),
    default=None,
    help="Write detailed JSON (names + version metadata) to this file",
)
@click.option(
    "--write-history/--no-write-history",
    "write_history_flag",
    default=True,
    show_default=True,
    help="On success, update history.yaml with resolved tags (skipped if new upstream images are found)",
)
@click.option(
    "--fail-on-new/--no-fail-on-new",
    default=True,
    show_default=True,
    help="Exit non-zero when upstream adds unmapped images",
)
def prepare_cmd(
    pack_version: str,
    mapping_path: Path,
    history_path: Path,
    previous_pack_values_path: Path | None,
    chart_values_path: Path | None,
    cache_dir: Path,
    output_path: Path | None,
    output_format: str,
    names_output_path: Path | None,
    detailed_output_path: Path | None,
    write_history_flag: bool,
    fail_on_new: bool,
) -> None:
    """Fetch upstream chart for VERSION and emit pack image list + new-image detection."""
    try:
        report, _history = prepare_version(
            pack_version,
            mapping_path=mapping_path,
            history_path=history_path,
            chart_values_path=chart_values_path,
            previous_pack_values_path=previous_pack_values_path,
            cache_dir=None if chart_values_path else cache_dir,
        )
    except (OSError, ValueError, KeyError, httpx.HTTPError) as exc:
        err_console.print(f"[red]error:[/red] {exc}")
        raise SystemExit(2) from exc

    names_payload = report_to_names_payload(report)
    detailed_payload = report_to_detailed_payload(report)

    if names_output_path is not None:
        _write_json(names_output_path, names_payload)
        err_console.print(f"Wrote names JSON: {names_output_path}")
    if detailed_output_path is not None:
        _write_json(detailed_output_path, detailed_payload)
        err_console.print(f"Wrote detailed JSON: {detailed_output_path}")

    fragment = report_to_pack_images_yaml(report)
    if output_path is not None:
        output_path.write_text(fragment, encoding="utf-8")
        err_console.print(f"Wrote pack images fragment: {output_path}")

    fmt = output_format.lower()
    if fmt == "names":
        console.print_json(data=names_payload)
    elif fmt == "detailed":
        console.print_json(data=detailed_payload)
    else:
        _print_prepare(report)
        console.print("\n# Suggested pack.content.images\n")
        console.print(fragment.rstrip())

    if not report.ok:
        if fail_on_new:
            raise SystemExit(1)
        return

    if write_history_flag:
        write_history(history_path, report)
        err_console.print(f"Updated history: {history_path}")


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _print_compare(report: CompareReport) -> None:
    console.print(
        f"Pack images: {len(report.pack_images)}  |  "
        f"Chart image blocks: {len(report.chart_images)}  |  "
        f"Findings: {len(report.findings)}"
    )

    if report.ok:
        console.print("[green]OK[/green] — no unmapped images or tag drift")
        return

    table = Table(title="Findings", show_lines=False)
    table.add_column("Kind", style="bold")
    table.add_column("Pack")
    table.add_column("Pack tag")
    table.add_column("Chart path")
    table.add_column("Chart tag")
    table.add_column("Message")

    for finding in report.findings:
        table.add_row(
            finding.kind,
            finding.pack_name or "",
            finding.pack_tag or "",
            finding.chart_path or "",
            finding.chart_tag or "",
            finding.message,
        )
    console.print(table)

    kinds = sorted({finding.kind for finding in report.findings})
    console.print(f"\nSummary kinds: {', '.join(kinds)}")
    if "unmapped_chart_image" in kinds:
        console.print(
            "[yellow]Hint:[/yellow] add new upstream image(s) to mapping.yaml "
            "and pack.content.images metadata"
        )


def _print_prepare(report: PrepareReport) -> None:
    console.print(f"Version: {report.pack_version}")
    console.print(f"Chart:   {report.chart_source}")

    table = Table(title="Resolved pack images", show_lines=False)
    table.add_column("Name", style="bold")
    table.add_column("Pack tag")
    table.add_column("Tag source")
    table.add_column("Chart path")
    table.add_column("Chart tag")
    for item in report.images:
        table.add_row(
            item.name,
            item.tag,
            item.tag_source,
            item.chart_path or "",
            item.chart_tag or "",
        )
    console.print(table)

    if report.new_chart_images:
        console.print("\n[red]New upstream image blocks (not in mapping):[/red]")
        for img in report.new_chart_images:
            console.print(f"  - {img.source_path}: {img.repository}:{img.tag}")
        console.print(
            "[yellow]Hint:[/yellow] add them to mapping.yaml (with pack_tag policy), "
            "then re-run prepare"
        )
    else:
        console.print("\n[green]OK[/green] — no new unmapped upstream images")

    if report.notes:
        console.print("\nNotes:")
        for note in report.notes:
            console.print(f"  - {note}")


if __name__ == "__main__":
    main()
