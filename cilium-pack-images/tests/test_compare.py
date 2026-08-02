from pathlib import Path

import yaml

from cilium_pack_images.compare import compare, normalize_tag, tags_match
from cilium_pack_images.extract import extract_chart_images, extract_pack_images, parse_image_ref
from cilium_pack_images.models import MappingConfig, MappingEntry


def test_parse_image_ref() -> None:
    ref = parse_image_ref(
        "us-docker.pkg.dev/palette-images/hardened-images/packs/cilium/1.19.5/cilium:1.19.5"
    )
    assert ref.name == "cilium"
    assert ref.tag == "1.19.5"


def test_normalize_tag() -> None:
    assert normalize_tag("v1.19.5", enabled=True) == "1.19.5"
    assert normalize_tag("1.19.5", enabled=True) == "1.19.5"
    assert normalize_tag("vnext", enabled=True) == "vnext"
    assert tags_match("1.19.5", "v1.19.5", normalize=True)
    assert not tags_match("1.19.5", "v1.19.5", normalize=False)


def test_detects_new_upstream_image() -> None:
    pack_values = {
        "pack": {
            "content": {
                "images": [
                    {
                        "image": (
                            "us-docker.pkg.dev/palette-images/hardened-images/"
                            "packs/cilium/1.19.5/cilium:1.19.5"
                        )
                    }
                ]
            }
        }
    }
    chart_values = {
        "image": {"repository": "quay.io/cilium/cilium", "tag": "v1.19.5"},
        "newThing": {"image": {"repository": "quay.io/cilium/new-thing", "tag": "v1.0.0"}},
    }
    mapping = MappingConfig(
        images={
            "cilium": MappingEntry(chart_paths=["image"]),
        }
    )

    report = compare(
        extract_pack_images(pack_values),
        extract_chart_images(chart_values),
        chart_values,
        mapping,
    )

    kinds = {finding.kind for finding in report.findings}
    assert "unmapped_chart_image" in kinds
    assert any(finding.chart_path == "newThing.image" for finding in report.findings)


def test_detects_tag_drift() -> None:
    pack_values = {
        "pack": {
            "content": {
                "images": [
                    {
                        "image": (
                            "us-docker.pkg.dev/palette-images/hardened-images/"
                            "packs/cilium/1.19.5/cilium-envoy:1.19.5"
                        )
                    }
                ]
            }
        }
    }
    chart_values = {
        "envoy": {
            "image": {
                "repository": "quay.io/cilium/cilium-envoy",
                "tag": "v1.36.8-abc",
            }
        }
    }
    mapping = MappingConfig(
        images={
            "cilium-envoy": MappingEntry(chart_paths=["envoy.image"]),
        }
    )

    report = compare(
        extract_pack_images(pack_values),
        extract_chart_images(chart_values),
        chart_values,
        mapping,
    )

    assert any(finding.kind == "tag_drift" for finding in report.findings)


def test_unmapped_pack_and_missing_chart_path() -> None:
    pack_values = {
        "pack": {
            "content": {
                "images": [
                    {"image": "reg/cilium:1.0.0"},
                    {"image": "reg/orphan:1.0.0"},
                ]
            }
        }
    }
    chart_values = {"image": {"repository": "quay.io/cilium/cilium", "tag": "v1.0.0"}}
    mapping = MappingConfig(
        images={
            "cilium": MappingEntry(chart_paths=["image", "missing.path"]),
            "ghost": MappingEntry(chart_paths=["image"]),
        }
    )
    report = compare(
        extract_pack_images(pack_values),
        extract_chart_images(chart_values),
        chart_values,
        mapping,
    )
    kinds = {finding.kind for finding in report.findings}
    assert "unmapped_pack_image" in kinds
    assert "missing_chart_path" in kinds
    assert "missing_pack_image" in kinds


def test_fixture_roundtrip(tmp_path: Path) -> None:
    pack_path = tmp_path / "pack-values.yaml"
    chart_path = tmp_path / "chart-values.yaml"
    mapping_path = tmp_path / "mapping.yaml"

    pack_path.write_text(
        yaml.safe_dump(
            {
                "pack": {
                    "content": {
                        "images": [
                            {
                                "image": (
                                    "us-docker.pkg.dev/x/cilium:1.19.5"
                                )
                            }
                        ]
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    chart_path.write_text(
        yaml.safe_dump({"image": {"repository": "quay.io/cilium/cilium", "tag": "v1.19.5"}}),
        encoding="utf-8",
    )
    mapping_path.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "normalize_tags": True,
                "images": {"cilium": {"chart_paths": ["image"]}},
                "ignore_chart_paths": [],
            }
        ),
        encoding="utf-8",
    )

    from cilium_pack_images.compare import compare_files

    report = compare_files(pack_path, chart_path, mapping_path)
    assert report.ok
