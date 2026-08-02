import re
from pathlib import Path

import yaml

from cilium_pack_images.compare import normalize_tag
from cilium_pack_images.extract import (
    dump_yaml,
    extract_chart_images,
    extract_pack_images,
    history_from_pack_images,
    load_history,
    load_mapping,
    load_yaml,
)
from cilium_pack_images.fetch import fetch_chart_values, load_chart_values_file
from cilium_pack_images.models import (
    HistoryConfig,
    MappingConfig,
    PreparedImage,
    PrepareReport,
)


def infer_pack_version(path: Path) -> str:
    for candidate in (path.parent.name, path.stem):
        match = re.search(r"(\d+\.\d+\.\d+)", candidate)
        if match:
            return match.group(1)
    return "unknown"


def resolve_pack_tag(
    *,
    pack_name: str,
    pack_version: str,
    chart_tag: str | None,
    mapping: MappingConfig,
    history: HistoryConfig,
) -> tuple[str, str]:
    """Return (tag, tag_source)."""
    entry = mapping.images[pack_name]
    policy = entry.pack_tag

    if policy.source == "pack_version":
        return pack_version, "pack_version"
    if policy.source == "pinned":
        if policy.value is None:
            msg = f"pinned pack_tag for {pack_name!r} has no value"
            raise ValueError(msg)
        return policy.value, "pinned"
    if policy.source == "history":
        if pack_name not in history.images:
            msg = f"history missing tag for {pack_name!r}; seed history.yaml or pass --previous-pack-values"
            raise KeyError(msg)
        return history.images[pack_name], "history"
    # chart
    if not chart_tag:
        msg = f"no chart tag available for {pack_name!r}"
        raise ValueError(msg)
    return normalize_tag(chart_tag, enabled=mapping.normalize_tags), "chart"


def prepare(
    *,
    pack_version: str,
    chart_values: dict,
    chart_source: str,
    mapping: MappingConfig,
    history: HistoryConfig,
) -> PrepareReport:
    chart_images = extract_chart_images(chart_values)
    chart_by_path = {img.source_path: img for img in chart_images}
    mapped_paths = {path for entry in mapping.images.values() for path in entry.chart_paths}
    ignored = set(mapping.ignore_chart_paths)

    new_chart_images = [
        img
        for img in chart_images
        if img.source_path not in mapped_paths
        and img.source_path not in ignored
        and img.repository
    ]

    notes: list[str] = []
    prepared: list[PreparedImage] = []

    # Stable order: mapping file order
    for pack_name, entry in mapping.images.items():
        primary_path = entry.chart_paths[0]
        chart_image = chart_by_path.get(primary_path)
        chart_tag = chart_image.tag if chart_image and chart_image.tag else None

        if chart_image is None or not chart_image.repository:
            notes.append(f"{pack_name}: mapped path {primary_path!r} missing or empty in chart")

        tag, tag_source = resolve_pack_tag(
            pack_name=pack_name,
            pack_version=pack_version,
            chart_tag=chart_tag,
            mapping=mapping,
            history=history,
        )
        image = mapping.registry.template.format(version=pack_version, name=pack_name, tag=tag)
        prepared.append(
            PreparedImage(
                name=pack_name,
                tag=tag,
                tag_source=tag_source,
                chart_path=primary_path,
                chart_tag=chart_tag,
                image=image,
            )
        )

        if tag_source == "history" and chart_tag:
            notes.append(
                f"{pack_name}: keeping historical pack tag {tag!r} "
                f"(chart has {chart_tag!r} at {primary_path})"
            )

    return PrepareReport(
        pack_version=pack_version,
        chart_source=chart_source,
        images=prepared,
        new_chart_images=new_chart_images,
        notes=notes,
    )


def prepare_version(
    pack_version: str,
    *,
    mapping_path: Path,
    history_path: Path,
    chart_values_path: Path | None = None,
    previous_pack_values_path: Path | None = None,
    cache_dir: Path | None = None,
) -> tuple[PrepareReport, HistoryConfig]:
    mapping = load_mapping(mapping_path)

    if previous_pack_values_path is not None:
        pack_values = load_yaml(previous_pack_values_path)
        if not isinstance(pack_values, dict):
            msg = f"previous pack values must be a mapping: {previous_pack_values_path}"
            raise ValueError(msg)
        history = history_from_pack_images(
            extract_pack_images(pack_values),
            pack_version=infer_pack_version(previous_pack_values_path),
        )
    else:
        history = load_history(history_path)

    if chart_values_path is not None:
        chart_values, chart_source = load_chart_values_file(chart_values_path)
    else:
        chart_values, chart_source = fetch_chart_values(
            mapping,
            pack_version,
            cache_dir=cache_dir,
        )

    report = prepare(
        pack_version=pack_version,
        chart_values=chart_values,
        chart_source=chart_source,
        mapping=mapping,
        history=history,
    )
    return report, history


def report_to_pack_images_yaml(report: PrepareReport) -> str:
    payload = {"pack": {"content": {"images": [{"image": item.image} for item in report.images]}}}
    return yaml.safe_dump(payload, sort_keys=False, default_flow_style=False)


def report_to_names_payload(report: PrepareReport) -> dict[str, object]:
    """Minimal JSON: list of pack image names only."""
    return {"images": [item.name for item in report.images]}


def report_to_detailed_payload(report: PrepareReport) -> dict[str, object]:
    """Detailed JSON: names plus pack/chart version metadata."""
    return {
        "pack_version": report.pack_version,
        "chart_source": report.chart_source,
        "images": [
            {
                "name": item.name,
                "tag": item.tag,
                "tag_source": item.tag_source,
                "chart_path": item.chart_path,
                "chart_tag": item.chart_tag,
                "image": item.image,
            }
            for item in report.images
        ],
        "new_images": [
            {
                "name": img.name,
                "path": img.source_path,
                "repository": img.repository,
                "tag": img.tag,
            }
            for img in report.new_chart_images
        ],
        "notes": list(report.notes),
    }


def history_from_report(report: PrepareReport) -> HistoryConfig:
    return HistoryConfig(
        last_pack_version=report.pack_version,
        images={item.name: item.tag for item in report.images},
    )


def write_history(path: Path, report: PrepareReport) -> None:
    dump_yaml(path, history_from_report(report).model_dump())


def seed_history_from_pack(pack_values_path: Path, history_path: Path, *, pack_version: str) -> HistoryConfig:
    pack_values = load_yaml(pack_values_path)
    if not isinstance(pack_values, dict):
        msg = f"pack values must be a mapping: {pack_values_path}"
        raise ValueError(msg)
    history = history_from_pack_images(extract_pack_images(pack_values), pack_version=pack_version)
    dump_yaml(history_path, history.model_dump())
    return history
