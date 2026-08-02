from pathlib import Path

from cilium_pack_images.extract import (
    extract_chart_images,
    extract_pack_images,
    get_by_path,
    load_mapping,
    load_yaml,
)
from cilium_pack_images.models import CompareFinding, CompareReport, ImageRef, MappingConfig


def normalize_tag(tag: str, *, enabled: bool) -> str:
    if enabled and tag.startswith("v") and len(tag) > 1 and tag[1].isdigit():
        return tag[1:]
    return tag


def tags_match(pack_tag: str, chart_tag: str, *, normalize: bool) -> bool:
    if pack_tag == chart_tag:
        return True
    if not normalize:
        return False
    return normalize_tag(pack_tag, enabled=True) == normalize_tag(chart_tag, enabled=True)


def compare(
    pack_images: list[ImageRef],
    chart_images: list[ImageRef],
    chart_values: dict,
    mapping: MappingConfig,
) -> CompareReport:
    findings: list[CompareFinding] = []
    chart_by_path = {img.source_path: img for img in chart_images}
    mapped_chart_paths: set[str] = set()
    pack_by_name = {img.name: img for img in pack_images}

    for pack_name, entry in mapping.images.items():
        pack_image = pack_by_name.get(pack_name)
        if pack_image is None:
            findings.append(
                CompareFinding(
                    kind="missing_pack_image",
                    message=f"mapping references pack image {pack_name!r} but it is absent from pack metadata",
                    pack_name=pack_name,
                )
            )

        for chart_path in entry.chart_paths:
            mapped_chart_paths.add(chart_path)
            chart_image = chart_by_path.get(chart_path)
            if chart_image is None:
                # Path may exist but not look like an image block, or values drifted.
                try:
                    get_by_path(chart_values, chart_path)
                except KeyError:
                    findings.append(
                        CompareFinding(
                            kind="missing_chart_path",
                            message=f"mapped chart path {chart_path!r} not found in chart values",
                            pack_name=pack_name,
                            chart_path=chart_path,
                        )
                    )
                    continue
                findings.append(
                    CompareFinding(
                        kind="invalid_chart_image",
                        message=f"mapped chart path {chart_path!r} is not an image block with repository/tag",
                        pack_name=pack_name,
                        chart_path=chart_path,
                    )
                )
                continue

            if not chart_image.repository:
                findings.append(
                    CompareFinding(
                        kind="empty_chart_image",
                        message=f"mapped chart path {chart_path!r} has an empty repository",
                        pack_name=pack_name,
                        chart_path=chart_path,
                    )
                )
                continue

            if pack_image is not None and not tags_match(
                pack_image.tag,
                chart_image.tag,
                normalize=mapping.normalize_tags,
            ):
                findings.append(
                    CompareFinding(
                        kind="tag_drift",
                        message=(
                            f"{pack_name}: pack tag {pack_image.tag!r} != chart tag "
                            f"{chart_image.tag!r} at {chart_path}"
                        ),
                        pack_name=pack_name,
                        pack_tag=pack_image.tag,
                        chart_path=chart_path,
                        chart_repository=chart_image.repository,
                        chart_tag=chart_image.tag,
                    )
                )

    for pack_image in pack_images:
        if pack_image.name not in mapping.images:
            findings.append(
                CompareFinding(
                    kind="unmapped_pack_image",
                    message=f"pack metadata image {pack_image.name!r} has no mapping entry",
                    pack_name=pack_image.name,
                    pack_tag=pack_image.tag,
                )
            )

    ignored = set(mapping.ignore_chart_paths)
    for chart_image in chart_images:
        path = chart_image.source_path
        if path in mapped_chart_paths or path in ignored:
            continue
        if not chart_image.repository:
            # Empty placeholder not listed in ignore — still surface it.
            findings.append(
                CompareFinding(
                    kind="unmapped_chart_image",
                    message=f"chart image path {path!r} is unmapped (empty repository)",
                    chart_path=path,
                    chart_repository=chart_image.repository,
                    chart_tag=chart_image.tag,
                )
            )
            continue
        findings.append(
            CompareFinding(
                kind="unmapped_chart_image",
                message=(
                    f"chart image path {path!r} ({chart_image.repository}:{chart_image.tag}) "
                    "is not covered by mapping — possible new upstream image"
                ),
                chart_path=path,
                chart_repository=chart_image.repository,
                chart_tag=chart_image.tag,
            )
        )

    findings.sort(key=lambda item: (item.kind, item.chart_path or "", item.pack_name or ""))
    return CompareReport(pack_images=pack_images, chart_images=chart_images, findings=findings)


def compare_files(pack_values_path: Path, chart_values_path: Path, mapping_path: Path) -> CompareReport:
    pack_values = load_yaml(pack_values_path)
    chart_values = load_yaml(chart_values_path)
    mapping = load_mapping(mapping_path)

    if not isinstance(pack_values, dict):
        msg = f"pack values must be a mapping document: {pack_values_path}"
        raise ValueError(msg)
    if not isinstance(chart_values, dict):
        msg = f"chart values must be a mapping document: {chart_values_path}"
        raise ValueError(msg)

    return compare(
        extract_pack_images(pack_values),
        extract_chart_images(chart_values),
        chart_values,
        mapping,
    )
