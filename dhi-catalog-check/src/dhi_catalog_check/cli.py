import json
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from dhi_catalog_check.models import VerifyReport
from dhi_catalog_check.pack_source import (
    DEFAULT_CACHE,
    DEFAULT_HISTORY,
    DEFAULT_MAPPING,
    fetch_pack_images,
    images_from_detailed_payload,
)
from dhi_catalog_check.verify import verify_images

console = Console()
err_console = Console(stderr=True)


@click.group()
@click.version_option(package_name="dhi-catalog-check")
def main() -> None:
    """Check Cilium pack images against the Docker Hardened Images (dhi.io) catalog.

    Requires an existing Docker Hub login (e.g. via Colima). This tool never
    reads or prints credentials.
    """


@main.command("verify")
@click.option(
    "--version",
    "pack_version",
    required=True,
    help="Cilium pack version to resolve via cilium-pack-images (e.g. 1.19.6)",
)
@click.option(
    "--registry",
    default="dhi.io",
    show_default=True,
    help="DHI registry hostname",
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
)
@click.option(
    "--chart-values",
    "chart_values_path",
    type=click.Path(path_type=Path, exists=True, dir_okay=False),
    default=None,
    help="Optional local upstream chart values.yaml (skip GitHub fetch)",
)
@click.option(
    "--cache-dir",
    type=click.Path(path_type=Path, file_okay=False),
    default=DEFAULT_CACHE,
    show_default=True,
)
@click.option(
    "--detailed-input",
    "detailed_input_path",
    type=click.Path(path_type=Path, exists=True, dir_okay=False),
    default=None,
    help="Skip pack fetch; use a cilium-pack-images --format detailed JSON file",
)
@click.option(
    "--docker-bin",
    default="docker",
    show_default=True,
    help="Docker CLI binary (Colima-compatible client)",
)
@click.option(
    "--max-workers",
    type=int,
    default=8,
    show_default=True,
    help="Parallel manifest inspect workers",
)
@click.option(
    "--output",
    "output_path",
    type=click.Path(path_type=Path, dir_okay=False),
    default=None,
    help="Write JSON report to this file",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["json", "human"], case_sensitive=False),
    default="json",
    show_default=True,
)
@click.option(
    "--fail-on-missing/--no-fail-on-missing",
    default=True,
    show_default=True,
    help="Exit 1 when any image/tag is missing from DHI",
)
def verify_cmd(
    pack_version: str,
    registry: str,
    mapping_path: Path,
    history_path: Path,
    chart_values_path: Path | None,
    cache_dir: Path,
    detailed_input_path: Path | None,
    docker_bin: str,
    max_workers: int,
    output_path: Path | None,
    output_format: str,
    fail_on_missing: bool,
) -> None:
    """Resolve pack images for VERSION, then verify each tag on dhi.io."""
    try:
        if detailed_input_path is not None:
            payload = json.loads(detailed_input_path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                msg = "detailed input must be a JSON object"
                raise ValueError(msg)
            images = images_from_detailed_payload(payload)
            version = str(payload.get("pack_version") or pack_version)
        else:
            images = fetch_pack_images(
                pack_version,
                mapping_path=mapping_path,
                history_path=history_path,
                chart_values_path=chart_values_path,
                cache_dir=None if chart_values_path else cache_dir,
            )
            version = pack_version

        report = verify_images(
            images,
            pack_version=version,
            registry=registry,
            docker_bin=docker_bin,
            max_workers=max_workers,
        )
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        # Never include exception args that might echo secrets from the environment.
        err_console.print(f"[red]error:[/red] {type(exc).__name__}: {exc}")
        raise SystemExit(2) from exc

    payload = report.model_dump()
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        err_console.print(f"Wrote report: {output_path}")

    if output_format.lower() == "human":
        _print_human(report)
    else:
        console.print_json(data=payload)

    if fail_on_missing and not report.all_present:
        raise SystemExit(1)


def _print_human(report: VerifyReport) -> None:
    console.print(f"Pack version: {report.pack_version}")
    console.print(f"Registry:     {report.registry}")
    console.print(f"Checked:      {report.checked}")
    console.print(f"All present:  {report.all_present}")

    table = Table(title="DHI catalog check")
    table.add_column("Status")
    table.add_column("Name")
    table.add_column("Tag")
    table.add_column("Ref")
    table.add_column("Reason")
    for item in report.present:
        table.add_row("present", item.name, item.tag, item.ref, "")
    for item in report.missing:
        table.add_row("missing", item.name, item.tag, item.ref, item.reason or "")
    console.print(table)


if __name__ == "__main__":
    main()
